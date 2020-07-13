#!/usr/bin/python3

import prometheus_client
import praw
import logging.handlers
import sys
import configparser
import time
import traceback
import requests
import math
import re
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.orm import sessionmaker
import discord_logging
from collections import defaultdict
from datetime import datetime
from datetime import timedelta

log = discord_logging.init_logging()
start_time = datetime.utcnow()


def parse_modmail_datetime(datetime_string):
	return datetime.strptime(datetime_string, "%Y-%m-%dT%H:%M:%S.%f+00:00")


def conversation_is_unread(conversation):
	return conversation.last_unread is not None and parse_modmail_datetime(conversation.last_unread) > \
				parse_modmail_datetime(conversation.last_updated)


def conversation_processed(conversation, processed_modmails):
	last_replied = parse_modmail_datetime(conversation.last_updated)
	return last_replied > start_time and (conversation.id not in processed_modmails or last_replied > processed_modmails[conversation.id])


class Queue:
	def __init__(self, max_size):
		self.list = []
		self.max_size = max_size
		self.set = set()

	def put(self, item):
		if len(self.list) >= self.max_size:
			self.list.pop(0)
		self.list.append(item)
		self.set.add(item)

	def contains(self, item):
		return item in self.set


Base = declarative_base()


class LogItem(Base):
	__tablename__ = 'log'

	id = Column(String(60), primary_key=True)
	created = Column(DateTime, nullable=False)
	mod = Column(String(60), nullable=False)
	action = Column(String(80), nullable=False)
	details = Column(String(80))
	target_author = Column(String(80))
	target_fullname = Column(String(20))
	target_permalink = Column(String(160))
	target_title = Column(String(300))
	target_body = Column(String(300))
	description = Column(String(300))

	def __init__(self, log_item):
		self.id = log_item.id
		self.created = datetime.utcfromtimestamp(log_item.created_utc)
		self.mod = log_item.mod.name
		self.action = log_item.action
		self.details = log_item.details
		self.target_author = log_item.target_author if log_item.target_author else None
		self.target_fullname = log_item.target_fullname
		self.target_permalink = log_item.target_permalink
		self.target_title = log_item.target_title
		self.target_body = log_item.target_body
		self.description = log_item.description


engine = create_engine(f'sqlite:///database.db')
Session = sessionmaker(bind=engine)
session = Session()
Base.metadata.create_all(engine)
session.commit()


SUBREDDIT = "CompetitiveOverwatch"
USER_AGENT = "ModQueueNotifier (by /u/Watchful1)"
LOOP_TIME = 1 * 60
REDDIT_OWNER = "Watchful1"
WEBHOOK = "https://discordapp.com/api/webhooks/{}/{}"


THRESHOLDS = {
	'unmod': {'post': 15, 'ping': 20},
	'unmod_hours': {'post': 4, 'ping': 6},
	'modqueue': {'post': 8, 'ping': 12},
	'modmail': {'post': 5, 'ping': 8},
	'modmail_hours': {'post': 12, 'ping': 24},
}

MODERATORS = {
	"merger3": "143730443777343488",
	"DerWaechter_": "193382989718093833",
	"connlocks": "139462031894904832",
	"Sorglos": "166045025153581056",
	"Watchful1": "95296130761371648",
	"blankepitaph": "262708160790396928",
	"Quantum027": "368589871092334612",
	"imKaku": "120207112646164480",
	"Unforgettable_": "177931363180085250",
	"KarmaCollect": "196018859889786880",
	"damnfinecoffee_": "308323435468029954",
	"MagnarHD": "209762662681149440",
	"wotugondo": "385460099138715650",
	"timberflynn": "195955430734823424",
	"Kralz": "172415421561962496",
	"ModWilliam": "321107093773877257",
	"Blaiidds": "204445334255042560",
	"DatGameGuy": "132969627050311680",

	"ExcitablePancake": "123149791864684545",
	"Jawoll": "122438001572839425",
	"Juicysteak117": "112685077707665408",
	"shomman": "166037812070580225",
	"venom_11": "174059362334146560",
	"ABCdropbear": "140284504702058497",
	"Puck83821": "280862474914365440",
}


def signal_handler(signal, frame):
	log.info("Handling interrupt")
	session.commit()
	engine.dispose()
	sys.exit(0)


def check_threshold(bldr, level, key, string):
	if level >= THRESHOLDS[key]['post']:
		bldr.append(string)
	if level >= THRESHOLDS[key]['ping']:
		return True
	return False


once = False
debug = False
user = None
if len(sys.argv) >= 2:
	user = sys.argv[1]
	for arg in sys.argv:
		if arg == 'once':
			once = True
		elif arg == 'debug':
			debug = True
			log.setLevel(logging.DEBUG)
else:
	log.error("No user specified, aborting")
	sys.exit(0)


discord_logging.init_discord_logging(user, logging.WARNING, 1)


try:
	r = praw.Reddit(
		user
		,user_agent=USER_AGENT)
except configparser.NoSectionError:
	log.error("User "+user+" not in praw.ini, aborting")
	sys.exit(0)

if r.config.CONFIG.has_option(user, 'webhook_redditmodtalk'):
	WEBHOOK = r.config.CONFIG[user]['webhook_redditmodtalk']
else:
	log.error("webhook_redditmodtalk not in config, aborting")
	sys.exit(0)

log.info("Logged into reddit as /u/{}".format(str(r.user.me())))

prometheus_client.start_http_server(8003)
prom_mod_actions = prometheus_client.Counter("bot_mod_actions", "Mod actions by moderator", ['moderator'])
prom_queue_size = prometheus_client.Gauge("bot_queue_size", "Queue size", ['type'])

last_posted = None
post_checked = datetime.utcnow()
posts_notified = Queue(50)
has_posted = False
modmails = {}

sub = r.subreddit(SUBREDDIT)

while True:
	try:
		startTime = time.perf_counter()
		log.debug("Starting run")

		for log_item in sub.mod.log(limit=None):
			if session.query(LogItem).filter_by(id=log_item.id).count() > 0:
				break

			prom_mod_actions.labels(moderator=log_item.mod).inc()

			if log_item.action == "banuser" and log_item.details == "permanent":
				log.warning(
					f"User permabanned by u/{log_item.mod}: https://www.reddit.com/user/{log_item.target_author}")

			session.merge(LogItem(log_item))

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
					if not debug:
						wiki_page.edit(edited_sidebar)

				if submission.discussion_type == 'CHAT' and submission.author.name not in ("Watchful1", "OWMatchThreads"):
					log.info(f"Removing live chat post: {submission.id} by u/{submission.author.name}")
					comment = submission.reply("Don't post live chat threads")
					comment.mod.distinguish(how="yes", sticky=True)
					submission.mod.remove()
					submission.mod.lock()

			if submission.approved and submission.link_flair_text is None and not posts_notified.contains(submission.id):
				if submission.approved_by in MODERATORS:
					user = f"<@{MODERATORS[submission.approved_by]}>"
				else:
					user = f"u/{submission.approved_by}"
				blame_string = f"{user} approved without adding a flair: <https://www.reddit.com{submission.permalink}>"
				log.info(f"Posting: {blame_string}")
				posts_notified.put(submission.id)
				if not debug:
					requests.post(WEBHOOK, data={"content": blame_string})

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
			if conversation_is_unread(conversation) and conversation.is_highlighted:
				if conversation_processed(conversation, modmails):
					log.warning(
						f"Highlighted modmail has a new reply: https://mod.reddit.com/mail/all/{conversation.id}")
					modmails[conversation.id] = parse_modmail_datetime(conversation.last_updated)

		# log when a modmail is archived without a response
		for conversation in sub.modmail.conversations(limit=10, state='archived'):
			if conversation.last_user_update is not None and parse_modmail_datetime(
					conversation.last_updated) > start_time and \
					parse_modmail_datetime(conversation.last_mod_update) < parse_modmail_datetime(
				conversation.last_user_update) and \
					conversation_processed(conversation, modmails):
				log.warning(
					f"Modmail archived without reply: https://mod.reddit.com/mail/arvhiced/{conversation.id}")
				modmails[conversation.id] = parse_modmail_datetime(conversation.last_updated)

		for conversation in sub.modmail.conversations(state='all'):
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
				if not debug:
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
		ping_here = check_threshold(results, unmod_count, 'unmod', f"Unmod: {unmod_count}") or ping_here
		ping_here = check_threshold(results, oldest_unmod_hours, 'unmod_hours', f"Oldest unmod in hours: {oldest_unmod_hours}") or ping_here
		ping_here = check_threshold(results, reported_count, 'modqueue', f"Modqueue: {reported_count}") or ping_here
		ping_here = check_threshold(results, mail_count, 'modmail', f"Modmail: {mail_count}") or ping_here
		ping_here = check_threshold(results, oldest_modmail_hours, 'modmail_hours', f"Oldest modmail in hours: {oldest_modmail_hours}") or ping_here
		count_string = ', '.join(results)
		if ping_here:
			count_string = "@here " + count_string

		if last_posted is None or datetime.utcnow() - timedelta(hours=1) > last_posted:
			if len(results) > 0:
				log.info(f"Posting: {count_string}")
				if not debug:
					requests.post(WEBHOOK, data={"content": count_string})
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
					if not debug:
						requests.post(WEBHOOK, data={"content": clear_string})
				else:
					log.info("Couldn't figure out who cleared the queue")

				has_posted = False

		log.debug("Run complete after: %d", int(time.perf_counter() - startTime))
	except Exception as err:
		log.warning("Hit an error in main loop")
		log.warning(traceback.format_exc())

	session.commit()
	if once:
		break

	time.sleep(LOOP_TIME)
