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
from datetime import datetime, timedelta

log = discord_logging.init_logging()

import counters
import static
import utils
import shared
import bayarea
import compow
from classes import Subreddit
from database import Database

database = None
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

	praw_file = discord_logging.get_config()
	discord_logging.init_discord_logging("QueueBot", logging.WARNING, 1, logging_webhook=discord_logging.get_config_var(praw_file, "global", 'queue_webhook'))
	database = Database()

	instances = {}
	for username in ['OWMatchThreads', 'CustomModBot', 'Watchful1']:
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
		1,
		instances['OWMatchThreads'],
		static.COMPOW_MODERATORS,
		known_log_types=static.COMPOW_KNOWN_LOG_TYPES,
		warning_log_types=static.COMPOW_WARNING_LOG_TYPES,
		report_reasons=static.COMPOW_REPORT_REASONS,
		comment_report_reasons=static.COMPOW_COMMENT_REPORT_REASONS,
		rules=static.COMPOW_RULES,
		reapprove_reasons=['#2 No Low-Value Content', 'This is spam'],
		thresholds={
			'unmod': {'track': True, 'post': 15, 'ping': 20},
			'unmod_hours': {'post': 4, 'ping': 6},
			'modqueue': {'track': True, 'post': 8, 'ping': 12},
			'modmail': {'track': True, 'post': 5, 'ping': 8},
			'modmail_hours': {'post': 12, 'ping': 24},
		},
		webhook=discord_logging.get_config_var(praw_file, "OWMatchThreads", 'webhook_redditmodtalk'),
		discord_link="https://discord.gg/competitiveow"
	)
	bay_area = Subreddit(
		"bayarea",
		2,
		instances['CustomModBot'],
		static.BAYAREA_MODERATORS,
		known_log_types=static.BAYAREA_KNOWN_LOG_TYPES,
		warning_log_types=static.BAYAREA_WARNING_LOG_TYPES,
		comment_report_reasons=static.BAYAREA_COMMENT_REPORT_REASONS,
		rules=static.BAYAREA_RULES,
		thresholds={
			'unmod': {'track': False},
			'modqueue': {'track': True},
			'modmail': {'track': True},
		},
		restricted={
			'flairs': {"Politics", "COVID19", "Local Crime"},
			'comment_days': 30,
			'comments': 20,
			'karma': 20,
			'action': "remove"
		},
		backup_reddit=instances['Watchful1'],
		name_in_modmails=False,
		webhook=discord_logging.get_config_var(praw_file, "CustomModBot", 'webhook_moderatoronly'),
		discord_link="https://discord.gg/35z3AA9xp3",
		days_between_restricted_submissions=7
	)

	last_backup = None
	while True:
		loop_time = time.perf_counter()
		try:
			log.debug("Starting run")

			for subreddit in [comp_ow, bay_area]:
				subreddit.clear_cache()

			for subreddit in [comp_ow, bay_area]:
				shared.ingest_log(subreddit, database)
				shared.process_modqueue_comments(subreddit)
				#shared.process_modqueue_comments_v2(subreddit)
				shared.process_modqueue_submissions(subreddit)
				#shared.process_modqueue_submissions_v2(subreddit)
				shared.process_modqueue_old(subreddit)
				shared.post_overlapping_actions(subreddit, database)

			for subreddit in [comp_ow]:
				shared.process_modqueue_reapprove(subreddit)
				shared.log_highlighted_modmail(subreddit, start_time)
				shared.log_archived_modmail_no_response(subreddit, start_time)

				compow.process_submissions(subreddit)
				compow.parse_modmail(subreddit)

			for subreddit in [bay_area]:
				bayarea.ingest_submissions(subreddit, database)
				bayarea.ingest_comments(subreddit, database)
				bayarea.check_flair_changes(subreddit, database)
				bayarea.backfill_karma(subreddit, database)

			for subreddit in [comp_ow, bay_area]:
				shared.count_queues(subreddit)

			for subreddit in [comp_ow]:
				shared.ping_queues(subreddit, database)

			database.update_object_counts()
			# database.cleanup()
			if last_backup is None or last_backup < datetime.utcnow() - timedelta(hours=24):
				try:
					database.purge()
				except Exception as err:
					utils.process_error(f"Error purging database", err, traceback.format_exc())

				try:
					log.info("Backing up database")
					database.backup()
					last_backup = datetime.utcnow()
				except Exception as err:
					utils.process_error(f"Error backing up database", err, traceback.format_exc())

		except Exception as err:
			utils.process_error(f"Hit an error in main loop", err, traceback.format_exc())

		delta_time = time.perf_counter() - loop_time
		counters.loop_time.observe(round(delta_time, 2))

		log.debug("Run complete after: %d", int(delta_time))

		database.session.commit()
		discord_logging.flush_discord()
		if args.once:
			break

		time.sleep(1 * 60)

# message to check user history according to bot
# check for double ban

# turn on:
# rescan submissions too
# remove posts from authors with recent crime posts
# ban users who use the wrong flair
# update link in comment/ban message, enhanced moderation is on
# remove posts from authors with insufficient history
# database purge
# warning on flair change during rescan
# new comment/submission report processing


