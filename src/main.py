#!/usr/bin/python3

import prometheus_client
import praw
import logging.handlers
import sys
import signal
import configparser
import time
import traceback
import requests
import math
import re
import discord_logging
import argparse
from collections import defaultdict
from datetime import datetime
from datetime import timedelta

log = discord_logging.init_logging()

import database
from database import LogItem
import static
import utils

start_time = datetime.utcnow()


def signal_handler(signal, frame):
	log.info("Handling interrupt")
	database.session.commit()
	database.engine.dispose()
	discord_logging.flush_discord()
	sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="r/competitiveoverwatch modqueue bot")
	parser.add_argument("user", help="The reddit user account to use")
	parser.add_argument("--once", help="Only run the loop once", action='store_const', const=True, default=False)
	parser.add_argument("--debug", help="Set the log level to debug", action='store_const', const=True, default=False)
	args = parser.parse_args()

	if args.debug:
		discord_logging.set_level(logging.DEBUG)

	discord_logging.init_discord_logging(args.user, logging.WARNING, 1)
	database.init()

	try:
		r = praw.Reddit(args.user, user_agent=static.USER_AGENT)
	except configparser.NoSectionError:
		log.error("User "+args.user+" not in praw.ini, aborting")
		sys.exit(0)

	static.WEBHOOK = discord_logging.get_config_var(discord_logging.get_config(), args.user, 'webhook_redditmodtalk')

	log.info(f"Logged into reddit as /u/{r.user.me().name}")

	prometheus_client.start_http_server(8003)
	prom_mod_actions = prometheus_client.Counter("bot_mod_actions", "Mod actions by moderator", ['moderator'])
	prom_queue_size = prometheus_client.Gauge("bot_queue_size", "Queue size", ['type'])

	last_posted = None
	post_checked = datetime.utcnow()
	posts_notified = utils.Queue(50)
	has_posted = False
	modmails = {}

	sub = r.subreddit(static.SUBREDDIT)

	while True:
		try:
			startTime = time.perf_counter()
			log.debug("Starting run")

			for log_item in sub.mod.log(limit=None):
				if database.session.query(LogItem).filter_by(id=log_item.id).count() > 0:
					break

				prom_mod_actions.labels(moderator=log_item.mod.name).inc()

				warning_type = None
				warning_items = []
				if log_item.mod.name not in static.MODERATORS:
					warning_type = "1"
				elif log_item.action in static.WARNING_LOG_TYPES:
					sub_filters = static.WARNING_LOG_TYPES[log_item.action]
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
						elif log_item_value == value:
							warning_type = "3"
						else:
							warning_type = None
							break
				elif log_item.action not in static.KNOWN_LOG_TYPES:
					warning_type = "2"

				if warning_type is not None:
					log.warning(
						f"{warning_type}:Mod action by u/{log_item.mod.name}: {log_item.action}{' '.join(warning_items)}")

				database.session.merge(LogItem(log_item))

			allowed_reasons = ['#2 No Off-Topic or Low-Value Content', 'This is spam']
			for item in sub.mod.modqueue():
				if item.approved:
					approve = True
					for report in item.user_reports:
						if report[0] not in allowed_reasons:
							approve = False
							break

					if approve:
						log.info(f"Reapproving item: {item.id}")
						item.mod.approve()

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

							utils.warn_ban_user(item.author, mod_name, sub, days, item.permalink)
							count_removed = utils.recursive_remove_comments(item)
							if count_removed > 1:
								log.info(f"Recursively removed {count_removed} comments")
							# archive modmail

			for submission in sub.new(limit=25):
				processed = False
				if datetime.utcfromtimestamp(submission.created_utc) <= post_checked:
					post_checked = datetime.utcnow()
					processed = True

				if not processed:
					if submission.author.name == "AutoModerator" and "Weekly Short Questions Megathread" in submission.title:
						log.info(f"Found new short questions thread, updating sidebar: {submission.id}")
						submission.mod.approve()
						wiki_page = sub.wiki['config/sidebar']
						edited_sidebar = re.sub(
							r'(\[Short Questions Megathread\]\(https://redd.it/)(\w{4,8})',
							f"\\1{submission.id}",
							wiki_page.content_md
						)
						wiki_page.edit(edited_sidebar)

					if submission.discussion_type == 'CHAT' and submission.author.name not in ("Watchful1", "OWMatchThreads"):
						log.info(f"Removing live chat post: {submission.id} by u/{submission.author.name}")
						comment = submission.reply("Don't post live chat threads")
						comment.mod.distinguish(how="yes", sticky=True)
						submission.mod.remove()
						submission.mod.lock()

				if submission.approved and submission.link_flair_text is None and not posts_notified.contains(submission.id):
					if submission.approved_by in static.MODERATORS:
						user = f"<@{static.MODERATORS[submission.approved_by]}>"
					else:
						user = f"u/{submission.approved_by}"
					blame_string = f"{user} approved without adding a flair: <https://www.reddit.com{submission.permalink}>"
					log.info(f"Posting: {blame_string}")
					posts_notified.put(submission.id)
					requests.post(static.WEBHOOK, data={"content": blame_string})

			unmod_count = 0
			oldest_unmod = datetime.utcnow()
			reported_count = 0
			mail_count = 0
			oldest_modmail = datetime.utcnow()
			for submission in sub.mod.unmoderated():
				unmod_count += 1
				oldest_unmod = datetime.utcfromtimestamp(submission.created_utc)
			for thing in sub.mod.modqueue():
				reported_count += 1

			# log when there's a reply to a highlighted modmail
			for conversation in sub.modmail.conversations(limit=10, state='all'):
				if utils.conversation_is_unread(conversation) and conversation.is_highlighted:
					if utils.conversation_not_processed(conversation, modmails, start_time):
						log.warning(
							f"Highlighted modmail has a new reply: https://mod.reddit.com/mail/all/{conversation.id}")
						modmails[conversation.id] = utils.parse_modmail_datetime(conversation.last_updated)

			# log when a modmail is archived without a response
			for conversation in sub.modmail.conversations(limit=10, state='archived'):
				if conversation.last_user_update is not None and \
						(conversation.last_mod_update is None or utils.parse_modmail_datetime(conversation.last_mod_update) < utils.parse_modmail_datetime(conversation.last_user_update)) and \
						utils.conversation_not_processed(conversation, modmails, start_time):
					log.warning(
						f"Modmail archived without reply: https://mod.reddit.com/mail/arvhiced/{conversation.id}")
					modmails[conversation.id] = utils.parse_modmail_datetime(conversation.last_updated)

			conversations = list(sub.modmail.conversations(state='all'))
			conversations.extend(list(sub.modmail.conversations(state='appeals')))
			for conversation in conversations:
				archive = None
				if len(conversation.authors) == 1 and \
						conversation.authors[0].name == "AutoModerator" and \
						len(conversation.messages) == 1:
					links = re.findall(r'(?:reddit.com/r/\w*/comments/)(\w*)', conversation.messages[0].body_markdown)
					if len(links) == 1:
						submission = r.submission(links[0])
						if submission.selftext == "[deleted]" or submission.author == "[deleted]":
							archive = "Deleted by user"
						elif submission.locked or submission.removed:
							if len(submission.comments) and submission.comments[0].stickied:
								archive = f"Removed by u/{submission.comments[0].author.name}"
						elif submission.approved:
							archive = f"Approved by u/{submission.approved_by}"

				if archive is not None:
					log.info(f"Archiving automod notification: {conversation.id}")
					conversation.reply(archive)
					conversation.archive()
				elif not conversation.is_highlighted:
					mail_count += 1
					modmail_age = datetime.strptime(conversation.last_updated, "%Y-%m-%dT%H:%M:%S.%f+00:00")
					if modmail_age < oldest_modmail:
						oldest_modmail = modmail_age

			oldest_unmod_hours = datetime.utcnow() - oldest_unmod
			oldest_unmod_hours = math.trunc(oldest_unmod_hours.seconds / (60 * 60))

			oldest_modmail_hours = datetime.utcnow() - oldest_modmail
			oldest_modmail_hours = math.trunc(oldest_modmail_hours.seconds / (60 * 60))

			log.debug(
				f"Unmod: {unmod_count}, age: {oldest_unmod_hours}, modqueue: {reported_count}, modmail: {mail_count}"
				f", modmail hours: {oldest_modmail_hours}")
			prom_queue_size.labels(type='unmod').set(unmod_count)
			prom_queue_size.labels(type='unmod_hours').set(oldest_unmod_hours)
			prom_queue_size.labels(type='modqueue').set(reported_count)
			prom_queue_size.labels(type='modmail').set(mail_count)
			prom_queue_size.labels(type='modmail_hours').set(oldest_modmail_hours)

			results = []
			ping_here = False
			ping_here = utils.check_threshold(results, unmod_count, 'unmod', f"Unmod: {unmod_count}") or ping_here
			ping_here = utils.check_threshold(results, oldest_unmod_hours, 'unmod_hours', f"Oldest unmod in hours: {oldest_unmod_hours}") or ping_here
			ping_here = utils.check_threshold(results, reported_count, 'modqueue', f"Modqueue: {reported_count}") or ping_here
			ping_here = utils.check_threshold(results, mail_count, 'modmail', f"Modmail: {mail_count}") or ping_here
			ping_here = utils.check_threshold(results, oldest_modmail_hours, 'modmail_hours', f"Oldest modmail in hours: {oldest_modmail_hours}") or ping_here
			count_string = ', '.join(results)
			if ping_here:
				count_string = "@here " + count_string

			if last_posted is None or datetime.utcnow() - timedelta(hours=1) > last_posted:
				if len(results) > 0:
					log.info(f"Posting: {count_string}")
					requests.post(static.WEBHOOK, data={"content": count_string})
					last_posted = datetime.utcnow()
					has_posted = True
				else:
					has_posted = False
			else:
				if has_posted and (unmod_count == 0 and reported_count == 0 and mail_count == 0):
					log.info("Queue clear, figuring out who cleared it")
					mods = defaultdict(int)
					for item in sub.mod.log(limit=100):
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
						requests.post(static.WEBHOOK, data={"content": clear_string})
					else:
						log.info("Couldn't figure out who cleared the queue")

					has_posted = False

			log.debug("Run complete after: %d", int(time.perf_counter() - startTime))
		except Exception as err:
			log.warning("Hit an error in main loop")
			log.warning(traceback.format_exc())

		database.session.commit()
		discord_logging.flush_discord()
		if args.once:
			break

		time.sleep(static.LOOP_TIME)
