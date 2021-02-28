import discord_logging
import math
import requests
from collections import defaultdict
from datetime import datetime, timedelta

log = discord_logging.get_logger()

import counters
import utils
import static
from database import LogItem


def ingest_log(subreddit, database):
	for log_item in subreddit.sub_object.mod.log(limit=None):
		if database.session.query(LogItem).filter_by(id=log_item.id).count() > 0:
			break

		counters.mod_actions.labels(moderator=log_item.mod.name, subreddit=subreddit.name).inc()

		warning_type = None
		warning_items = []
		if log_item.mod.name not in subreddit.moderators:
			warning_type = "1"
		elif log_item.action in subreddit.warning_log_types:
			sub_filters = subreddit.warning_log_types[log_item.action]
			for item, value in sub_filters.items():
				if item == "print":
					for field_name in value:
						warning_items.append(getattr(log_item, field_name))
					continue
				log_item_value = getattr(log_item, item)
				if value.startswith("!"):
					if value == "!":
						if log_item_value is None:
							warning_type = "5"
						else:
							warning_type = None
							break
					elif log_item_value != value[1:]:
						warning_type = "4"
					else:
						warning_type = None
						break
				elif value.startswith("~"):
					if value[1:] in log_item_value:
						warning_type = "6"
					else:
						warning_type = None
						break
				elif log_item_value == value:
					warning_type = "3"
				else:
					warning_type = None
					break
		elif log_item.action not in static.KNOWN_LOG_TYPES:
			warning_type = "2"

		if warning_type is not None:
			log.warning(
				f"r/{subreddit.name}: {warning_type}:Mod action by u/{log_item.mod.name}: {log_item.action} {' '.join(warning_items)}")

		database.session.merge(LogItem(log_item))


def process_modqueue(subreddit):
	for item in list(subreddit.modqueue()):
		if item.approved:
			approve = True
			if len(subreddit.reapprove_reasons):
				for report in item.user_reports:
					if report[0] not in subreddit.reapprove_reasons:
						approve = False
						break

			if approve:
				log.info(f"Reapproving item: {item.id}")
				item.mod.approve()
				subreddit.modqueue().remove(item)

		if item.fullname.startswith("t1_") and len(item.mod_reports):
			for report_reason, mod_name in item.mod_reports:
				items = report_reason.split(" ")
				if items[0].lower() == "r1":
					days = None
					if len(items) > 1:
						try:
							days = int(items[1])
						except ValueError:
							pass

					utils.warn_ban_user(item.author, mod_name, subreddit, days, item.permalink)
					count_removed = utils.recursive_remove_comments(item)
					if count_removed > 1:
						log.info(f"Recursively removed {count_removed} comments")
					subreddit.modqueue().remove(item)
					break

		if len(subreddit.report_reasons) and item.fullname.startswith("t3_") and len(item.mod_reports):
			for report_reason, mod_name in item.mod_reports:
				if report_reason in subreddit.report_reasons:
					removal_dict = subreddit.report_reasons[report_reason]
					log.info(f"Removing post {item.id} for rule {removal_dict['rule']} from u/{mod_name}")
					item.mod.remove()
					item.mod.lock()
					item.mod.flair("Removed")
					subreddit.modqueue().remove(item)

					comment = item.reply(
						f"{static.REMOVAL_REASON_HEADER.format(subreddit.name)}\n\n{removal_dict['reason']}\n\n"
						f"{static.REMOVAL_REASON_FOOTER.format(subreddit.name)}\n\nTriggered by mod {mod_name}")
					comment.mod.distinguish(how="yes", sticky=True)

					break


def log_highlighted_modmail(subreddit, start_time):
	for conversation in subreddit.all_modmail():
		if utils.conversation_is_unread(conversation):
			conversation_type = None
			if len([author for author in conversation.authors if author.is_admin]) > 0:
				conversation_type = "Admin"
			elif conversation.is_highlighted:
				conversation_type = "Highlighted"
			if conversation_type is not None and utils.conversation_not_processed(
					conversation, subreddit.processed_modmails, start_time):
				log.warning(
					f"r/{subreddit.name}: {conversation_type} modmail has a new reply: https://mod.reddit.com/mail/all/{conversation.id}")
				subreddit.processed_modmails[conversation.id] = utils.parse_modmail_datetime(conversation.last_updated)


def log_archived_modmail_no_response(subreddit, start_time):
	for conversation in subreddit.archived_modmail():
		if conversation.last_user_update is not None and \
				(conversation.last_mod_update is None or utils.parse_modmail_datetime(
					conversation.last_mod_update) < utils.parse_modmail_datetime(
					conversation.last_user_update)) and \
				utils.conversation_not_processed(conversation, subreddit.processed_modmails, start_time):
			log.warning(
				f"Modmail archived without reply: https://mod.reddit.com/mail/arvhiced/{conversation.id}")
			subreddit.processed_modmails[conversation.id] = utils.parse_modmail_datetime(conversation.last_updated)


def count_queues(subreddit):
	oldest_modmail = datetime.utcnow()
	for conversation in subreddit.combined_modmail():
		if not conversation.is_highlighted:
			subreddit.mail_count += 1
			modmail_age = datetime.strptime(conversation.last_updated, "%Y-%m-%dT%H:%M:%S.%f+00:00")
			if modmail_age < oldest_modmail:
				oldest_modmail = modmail_age

	subreddit.oldest_modmail_hours = math.trunc((datetime.utcnow() - oldest_modmail).seconds / (60 * 60))

	oldest_unmod = datetime.utcnow()
	for submission in subreddit.sub_object.mod.unmoderated():
		subreddit.unmod_count += 1
		oldest_unmod = datetime.utcfromtimestamp(submission.created_utc)

	subreddit.oldest_unmod_hours = math.trunc((datetime.utcnow() - oldest_unmod).seconds / (60 * 60))

	subreddit.reported_count = len(list(subreddit.modqueue(limit=None)))

	log.debug(
		f"Unmod: {subreddit.unmod_count}, age: {subreddit.oldest_unmod_hours}, modqueue: {subreddit.reported_count}, "
		f"modmail: {subreddit.mail_count}, modmail hours: {subreddit.oldest_modmail_hours}")

	counters.queue_size.labels(type='unmod', subreddit=subreddit.name).set(subreddit.unmod_count)
	counters.queue_size.labels(type='unmod_hours', subreddit=subreddit.name).set(subreddit.oldest_unmod_hours)
	counters.queue_size.labels(type='modqueue', subreddit=subreddit.name).set(subreddit.reported_count)
	counters.queue_size.labels(type='modmail', subreddit=subreddit.name).set(subreddit.mail_count)
	counters.queue_size.labels(type='modmail_hours', subreddit=subreddit.name).set(subreddit.oldest_modmail_hours)


def ping_queues(subreddit, database):
	count_string = subreddit.ping_string()

	if subreddit.last_posted is None or datetime.utcnow() - timedelta(hours=1) > subreddit.last_posted:
		if count_string is not None:
			log.info(f"Posting: {count_string}")
			requests.post(subreddit.WEBHOOK, data={"content": count_string})
			subreddit.last_posted = datetime.utcnow()
			subreddit.has_posted = True
		else:
			subreddit.has_posted = False
	else:
		if subreddit.has_posted and (subreddit.unmod_count == 0 and subreddit.reported_count == 0 and subreddit.mail_count == 0):
			log.info("Queue clear, figuring out who cleared it")
			mods = defaultdict(int)
			for item in database.session.query(LogItem).filter_by(subreddit=subreddit.name).order_by(LogItem.created.desc()).limit(100).all():
				minutes_old = (datetime.utcnow() - datetime.utcfromtimestamp(item.created_utc)).seconds / 60
				if item.mod not in ("OWMatchThreads", "AutoModerator"):
					mods[item.mod] += 1
				if minutes_old > 40:
					break
			mod_clear = None
			mod_count = 2
			for mod in mods:
				if mods[mod] > mod_count:
					mod_clear = mod
					mod_count = mods[mod]

			if mod_clear is not None:
				clear_string = f"{mod_clear} cleared the queues!"
				log.info(clear_string)
				requests.post(subreddit.WEBHOOK, data={"content": clear_string})
			else:
				log.info("Couldn't figure out who cleared the queue")

			subreddit.has_posted = False
