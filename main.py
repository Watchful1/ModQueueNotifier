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
from datetime import datetime
from datetime import timedelta

SUBREDDIT = "CompetitiveOverwatch"
USER_AGENT = "ModQueueNotifier (by /u/Watchful1)"
LOOP_TIME = 5 * 60
REDDIT_OWNER = "Watchful1"
WEBHOOK = "https://discordapp.com/api/webhooks/{}/{}"
LOG_LEVEL = logging.DEBUG


LOG_FOLDER_NAME = "logs"
if not os.path.exists(LOG_FOLDER_NAME):
	os.makedirs(LOG_FOLDER_NAME)
LOG_FILENAME = LOG_FOLDER_NAME+"/"+"bot.log"
LOG_FILE_BACKUPCOUNT = 5
LOG_FILE_MAXSIZE = 1024 * 1024 * 16

log = logging.getLogger("bot")
log.setLevel(LOG_LEVEL)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
log_stderrHandler = logging.StreamHandler()
log_stderrHandler.setFormatter(log_formatter)
log.addHandler(log_stderrHandler)
if LOG_FILENAME is not None:
	log_fileHandler = logging.handlers.RotatingFileHandler(LOG_FILENAME,
	                                                       maxBytes=LOG_FILE_MAXSIZE,
	                                                       backupCount=LOG_FILE_BACKUPCOUNT)
	log_fileHandler.setFormatter(log_formatter)
	log.addHandler(log_fileHandler)


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

while True:
	try:
		startTime = time.perf_counter()
		log.debug("Starting run")

		sub = r.subreddit(SUBREDDIT)
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
			mail_count += 1

		oldest_age = datetime.utcnow() - oldest_unmod
		oldest_age = math.trunc(oldest_age.seconds / (60 * 60))

		log.debug(f"Unmod: {unmod_count}, age: {oldest_age}, modqueue: {reported_count}, modmail: {mail_count}")

		results = []
		if unmod_count >= 20:
			results.append(f"Unmod: {unmod_count}")
		if oldest_age >= 6:
			results.append(f"Oldest unmod in hours: {oldest_age}")
		if reported_count >= 10:
			results.append(f"Modqueue: {reported_count}")
		if mail_count >= 5:
			results.append(f"Modmail: {mail_count}")
		count_string = ', '.join(results)

		if len(results) > 0 and (last_posted is None or datetime.utcnow() - timedelta(hours=1) > last_posted):
			log.info(f"Posting: {count_string}")
			if not debug:
				requests.post(WEBHOOK, data={"content": count_string})
			last_posted = datetime.utcnow()

		log.debug("Run complete after: %d", int(time.perf_counter() - startTime))
	except Exception as err:
		log.warning("Hit an error in main loop")
		log.warning(traceback.format_exc())

	if once:
		break

	time.sleep(LOOP_TIME)