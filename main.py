#!/usr/bin/python3

import praw
import os
import logging.handlers
import sys
import configparser
import time
import traceback
import requests
import math
import re
import sqlite3
import discord_logging
from collections import defaultdict
from datetime import datetime
from datetime import timedelta

log = discord_logging.init_logging()

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
}

MODERATORS = {
	"ExcitablePancake": "123149791864684545",
	"Jawoll": "122438001572839425",
	"Juicysteak117": "112685077707665408",
	"merger3": "143730443777343488",
	"shomman": "166037812070580225",
	"DerWaechter_": "193382989718093833",
	"connlocks": "139462031894904832",
	"venom_11": "174059362334146560",
	"Sorglos": "166045025153581056",
	"wotugondo": "385460099138715650",
	"Watchful1": "95296130761371648",
	"blankepitaph": "262708160790396928",
	"Quantum027": "368589871092334612",
	"imKaku": "120207112646164480",
	"Unforgettable_": "177931363180085250",
	"KarmaCollect": "196018859889786880",
	"damnfinecoffee_": "308323435468029954",
	"MagnarHD": "209762662681149440",
	"ABCdropbear": "140284504702058497",
	"Puck83821": "280862474914365440",
}

dbConn = sqlite3.connect("database.db")
c = dbConn.cursor()
c.execute('''
	CREATE TABLE IF NOT EXISTS stats (
		CreationDate TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
		Unmod INTEGER NOT NULL,
		Modqueue INTEGER NOT NULL,
		Modmail INTEGER NOT NULL
	)
''')


def add_stat(unmod, modqueue, modmail):
	c = dbConn.cursor()
	try:
		c.execute('''
			INSERT INTO stats
			(Unmod, Modqueue, Modmail)
			VALUES (?, ?, ?)
		''', (unmod, modqueue, modmail))
	except sqlite3.IntegrityError:
		return False

	dbConn.commit()
	return True


def signal_handler(signal, frame):
	log.info("Handling interrupt")
	dbConn.commit()
	dbConn.close()
	sys.exit(0)


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


try:
	r = praw.Reddit(
		user
		,user_agent=USER_AGENT)
except configparser.NoSectionError:
	log.error("User "+user+" not in praw.ini, aborting")
	sys.exit(0)

if r.config.CONFIG.has_option(user, 'webhookid'):
	WEBHOOK_ID = r.config.CONFIG[user]['webhookid']
else:
	log.error("Webhookid not in config, aborting")
	sys.exit(0)

if r.config.CONFIG.has_option(user, 'tokenid'):
	TOKEN_ID = r.config.CONFIG[user]['tokenid']
else:
	log.error("Tokenid not in config, aborting")
	sys.exit(0)

WEBHOOK = WEBHOOK.format(WEBHOOK_ID, TOKEN_ID)

log.info("Logged into reddit as /u/{}".format(str(r.user.me())))

last_posted = None
post_checked = datetime.utcnow()
posts_notified = Queue(50)
has_posted = False


while True:
	try:
		startTime = time.perf_counter()
		log.debug("Starting run")

		sub = r.subreddit(SUBREDDIT)

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
		for submission in sub.mod.unmoderated():
			unmod_count += 1
			oldest_unmod = datetime.utcfromtimestamp(submission.created_utc)
		for thing in sub.mod.modqueue():
			reported_count += 1
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
			else:
				mail_count += 1

		oldest_age = datetime.utcnow() - oldest_unmod
		oldest_age = math.trunc(oldest_age.seconds / (60 * 60))

		log.debug(f"Unmod: {unmod_count}, age: {oldest_age}, modqueue: {reported_count}, modmail: {mail_count}")
		add_stat(unmod_count, reported_count, mail_count)

		results = []
		ping_here = False
		ping_here = check_threshold(results, unmod_count, 'unmod', f"Unmod: {unmod_count}") or ping_here
		ping_here = check_threshold(results, oldest_age, 'unmod_hours', f"Oldest unmod in hours: {oldest_age}") or ping_here
		ping_here = check_threshold(results, reported_count, 'modqueue', f"Modqueue: {reported_count}") or ping_here
		ping_here = check_threshold(results, mail_count, 'modmail', f"Modmail: {mail_count}") or ping_here
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
			if has_posted and (unmod_count == 0 and reported_count == 0 and mail_count <= 1):
				log.info("Queue clear, figuring out who cleared it")
				mods = defaultdict(int)
				for item in sub.mod.log(limit=40):
					minutes_old = (datetime.utcnow() - datetime.utcfromtimestamp(item.created_utc)).seconds / 60
					if minutes_old < 120:
						mods[item.mod] += 1
				mod_clear = None
				for mod in mods:
					if mods[mod] > 20:
						mod_clear = mod

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

	if once:
		break

	time.sleep(LOOP_TIME)
