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
from classes import UserNotes, Note


def ingest_log(subreddit, database):
	subreddit.mod_log = []
	for log_item in subreddit.sub_object.mod.log(limit=None):
		if database.session.query(LogItem).filter_by(id=log_item.id).count() > 0:
			break

		subreddit.mod_log.append(log_item)

		counters.mod_actions.labels(moderator=log_item.mod.name, subreddit=subreddit.name).inc()

		warning_type = None
		warning_items = []
		if log_item.mod.name not in subreddit.moderators:
			warning_type = "1"
		elif subreddit.warning_log_types is not None and log_item.action in subreddit.warning_log_types:
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
		elif log_item.action not in subreddit.known_log_types:
			warning_type = "2"

		if warning_type is not None:
			log.warning(
				f"r/{subreddit.name}: {warning_type}:Mod action by u/{log_item.mod.name}: {log_item.action} {' '.join(warning_items)}")

		database.session.merge(LogItem(log_item))


def process_modqueue_reapprove(subreddit):
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


def process_modqueue_old(subreddit):
	for item in list(subreddit.modqueue()):
		item_date = datetime.utcfromtimestamp(item.created_utc)
		if item_date < datetime.utcnow() - timedelta(days=180):
			log.warning(f"[Old item in modqueue](https://www.reddit.com/{item.permalink}), automatically removing")
			item.mod.remove()


def process_modqueue_comments(subreddit):
	for item in list(subreddit.modqueue()):
		if item.fullname.startswith("t1_") and len(item.mod_reports):
			for report_reason, mod_name in item.mod_reports:
				items = report_reason.split(" ")
				if items[0].lower() in subreddit.comment_report_reasons:
					report_object = subreddit.comment_report_reasons[items[0].lower()]
					days = None
					action_string = "error, invalid action"
					additional_note = None
					if len(items) > 1:
						if items[1] == 'w':
							log.info(f"Processing new warning comment report: {report_reason}")
							days = 0
							action_string = "warned"
						elif items[1] == 'p':
							log.info(f"Processing new permaban comment report: {report_reason}")
							days = -1
							action_string = "permabanned"
						else:
							try:
								days = int(items[1])
								log.info(f"Processing new {days} day ban comment report: {report_reason}")
								action_string = f"banned for {days} days"
							except ValueError:
								additional_note = ' '.join(items[1:])
								pass

					if additional_note is None and len(items) > 2:
						additional_note = ' '.join(items[2:])

					sub_notes = utils.get_usernotes(subreddit)
					username = item.author.name
					user_note = sub_notes.get_user_note(username)
					if days is None:
						if user_note is not None:
							days_ban, note_is_old = user_note.get_recent_warn_ban()
							log.info(f"Processing new comment report: {report_reason}. Got {days_ban} days ban from notes")
						else:
							days_ban, note_is_old = None, False
							log.info(f"Processing new comment report: {report_reason}. No usernotes")
						days = subreddit.get_next_ban_tier(days_ban, note_is_old)
						if days == -1:
							action_string = "permabanned based on usernotes"
						elif days == 0:
							action_string = "warned based on usernotes"
						else:
							action_string = f"banned for {days} days based on usernotes"

					item_link = f"https://www.reddit.com{item.permalink}"
					reason_text = report_object['reason']
					if additional_note is not None:
						reason_text = reason_text + "\n\n" + additional_note
					warn_ban_message = f"{reason_text}\n\n{item_link}"
					if subreddit.name_in_modmails:
						warn_ban_message += f"\n\nFrom u/{mod_name}"
					if days == 0:
						log.info(f"Warning u/{username}, rule {report_object['rule']} from u/{mod_name}")
						item.author.message(
							f"Rule {report_object['rule']} warning",
							warn_ban_message,
							from_subreddit=subreddit.name)
						for conversation in list(subreddit.all_modmail()):
							if len(conversation.authors) == 1 and \
									conversation.authors[0].name in {"CustomModBot", "OWMatchThreads"} and \
									len(conversation.messages) == 1:
								log.info(f"Archiving {conversation.authors[0].name} message: {conversation.id}")
								conversation.archive()
								subreddit.all_modmail().remove(conversation)
								break

						note = Note.build_note(sub_notes, mod_name, "abusewarn", report_object['short_reason'], datetime.utcnow(), item_link)
					else:
						if days == -1:
							log.warning(f"Banning u/{username} permanently, rule {report_object['rule']} from u/{mod_name}")
							subreddit.sub_object.banned.add(
								item.author,
								ban_reason=f"{report_object['short_reason']} u/{mod_name}",
								ban_message=warn_ban_message)
							note = Note.build_note(sub_notes, mod_name, "permban", report_object['short_reason'], datetime.utcnow(), item_link)
						else:
							log.info(f"Banning u/{username} for {days} days, rule {report_object['rule']} from u/{mod_name}")
							subreddit.sub_object.banned.add(
								item.author,
								duration=days,
								ban_reason=f"{report_object['short_reason']} u/{mod_name}",
								ban_message=warn_ban_message)
							note = Note.build_note(sub_notes, mod_name, "ban", f"{days}d - {report_object['short_reason']}", datetime.utcnow(), item_link)

					if user_note is not None:
						user_note.add_new_note(note)
					else:
						user_note = UserNotes(username)
						user_note.add_new_note(note)
						sub_notes.add_update_user_note(user_note)
					utils.save_usernotes(subreddit, sub_notes, f"\"create new note on user {username}\" via OWMatchThreads")

					count_removed = utils.recursive_remove_comments(item)
					if count_removed > 1:
						log.info(f"Recursively removed {count_removed} comments")

					log.warning(f"r/{subreddit.name}:u/{mod_name}: u/{username} {action_string}")

					subreddit.modqueue().remove(item)
					break


def process_modqueue_submissions(subreddit):
	for item in list(subreddit.modqueue()):
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
			archived_by = conversation.mod_actions[-1].author.name
			if archived_by != "Watchful1":
				log.warning(
					f"Modmail archived without reply: https://mod.reddit.com/mail/arvhiced/{conversation.id} by u/{archived_by}")
			subreddit.processed_modmails[conversation.id] = utils.parse_modmail_datetime(conversation.last_updated)


def count_queues(subreddit):
	if subreddit.thresholds['modmail']['track']:
		oldest_modmail = datetime.utcnow()
		for conversation in subreddit.combined_modmail():
			if not conversation.is_highlighted:
				subreddit.mail_count += 1
				modmail_age = datetime.strptime(conversation.last_updated, "%Y-%m-%dT%H:%M:%S.%f+00:00")
				if modmail_age < oldest_modmail:
					oldest_modmail = modmail_age

		subreddit.oldest_modmail_hours = math.trunc((datetime.utcnow() - oldest_modmail).seconds / (60 * 60))

		counters.queue_size.labels(type='modmail', subreddit=subreddit.name).set(subreddit.mail_count)
		counters.queue_size.labels(type='modmail_hours', subreddit=subreddit.name).set(subreddit.oldest_modmail_hours)

	if subreddit.thresholds['unmod']['track']:
		oldest_unmod = datetime.utcnow()
		for submission in subreddit.sub_object.mod.unmoderated():
			subreddit.unmod_count += 1
			oldest_unmod = datetime.utcfromtimestamp(submission.created_utc)

		subreddit.oldest_unmod_hours = math.trunc((datetime.utcnow() - oldest_unmod).seconds / (60 * 60))

		counters.queue_size.labels(type='unmod', subreddit=subreddit.name).set(subreddit.unmod_count)
		counters.queue_size.labels(type='unmod_hours', subreddit=subreddit.name).set(subreddit.oldest_unmod_hours)

	if subreddit.thresholds['modqueue']['track']:
		subreddit.reported_count = len(list(subreddit.sub_object.mod.modqueue(limit=None)))

		counters.queue_size.labels(type='modqueue', subreddit=subreddit.name).set(subreddit.reported_count)

	log.debug(
		f"r/{subreddit.name}: Unmod: {subreddit.unmod_count}, age: {subreddit.oldest_unmod_hours}, "
		f"modqueue: {subreddit.reported_count}, modmail: {subreddit.mail_count}, "
		f"modmail hours: {subreddit.oldest_modmail_hours}")


def ping_queues(subreddit, database):
	count_string = subreddit.ping_string()

	if subreddit.last_posted is None or datetime.utcnow() - timedelta(hours=1) > subreddit.last_posted:
		if count_string is not None:
			log.info(f"Posting: {count_string}")
			requests.post(subreddit.webhook, data={"content": count_string})
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
				requests.post(subreddit.webhook, data={"content": clear_string})
			else:
				log.info("Couldn't figure out who cleared the queue")

			subreddit.has_posted = False
