#!/usr/bin/python3

import praw
import logging.handlers
import sys
import signal
import configparser
import time
import traceback
import discord_logging
import argparse
from datetime import datetime

log = discord_logging.init_logging()

import database
import counters
import static
import utils
import shared
import compow
from classes import Subreddit

start_time = datetime.utcnow()


def signal_handler(signal, frame):
	log.info("Handling interrupt")
	database.session.commit()
	database.engine.dispose()
	discord_logging.flush_discord()
	sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="modqueue bot")
	parser.add_argument("--once", help="Only run the loop once", action='store_const', const=True, default=False)
	parser.add_argument("--debug", help="Set the log level to debug", action='store_const', const=True, default=False)
	args = parser.parse_args()

	if args.debug:
		discord_logging.set_level(logging.DEBUG)

	discord_logging.init_discord_logging("OWMatchThreads", logging.WARNING, 1)
	database.init()

	instances = {}
	for username in ['OWMatchThreads', 'Watchful1']:
		try:
			instances[username] = praw.Reddit(username, user_agent=static.USER_AGENT)
			log.info(f"Logged into reddit as /u/{instances[username].user.me().name}")
		except configparser.NoSectionError:
			log.error("User "+args.user+" not in praw.ini, aborting")
			sys.exit(0)

	log.info(f"Python version {sys.version}")

	counters.init(8003)

	comp_ow = Subreddit(
		"CompetitiveOverwatch",
		instances['OWMatchThreads'],
		static.COMPOW_MODERATORS,
		warning_log_types=static.COMPOW_WARNING_LOG_TYPES,
		report_reasons=static.COMPOW_REPORT_REASONS,
		reapprove_reasons=['#2 No Off-Topic or Low-Value Content', 'This is spam'],
		thresholds={
			'unmod': {'track': True, 'post': 15, 'ping': 20},
			'unmod_hours': {'post': 4, 'ping': 6},
			'modqueue': {'track': True, 'post': 8, 'ping': 12},
			'modmail': {'track': True, 'post': 5, 'ping': 8},
			'modmail_hours': {'post': 12, 'ping': 24},
		},
		webhook=discord_logging.get_config_var(discord_logging.get_config(), "OWMatchThreads", 'webhook_redditmodtalk')
	)
	bay_area = Subreddit(
		"bayarea",
		instances['Watchful1'],
		static.BAYAREA_MODERATORS,
		thresholds={
			'unmod': {'track': False},
			'modqueue': {'track': True},
			'modmail': {'track': True},
		},
	)

	while True:
		try:
			startTime = time.perf_counter()
			log.debug("Starting run")

			for subreddit in [comp_ow, bay_area]:
				subreddit.clear_cache()
				shared.ingest_log(subreddit, database)

			for subreddit in [comp_ow]:
				shared.process_modqueue(subreddit)
				shared.log_highlighted_modmail(subreddit, start_time)
				shared.log_archived_modmail_no_response(subreddit, start_time)

				compow.process_submissions(subreddit)
				compow.parse_modmail(subreddit)

			for subreddit in [comp_ow, bay_area]:
				shared.count_queues(subreddit)

			for subreddit in [comp_ow]:
				shared.ping_queues(subreddit, database)

			log.debug("Run complete after: %d", int(time.perf_counter() - startTime))
		except Exception as err:
			utils.process_error(f"Hit an error in main loop", err, traceback.format_exc())

		database.session.commit()
		discord_logging.flush_discord()
		if args.once:
			break

		time.sleep(1 * 60)
