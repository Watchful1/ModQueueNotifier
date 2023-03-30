import discord_logging
import prawcore.exceptions
import requests
from sqlalchemy.sql import func
from datetime import datetime, timedelta

log = discord_logging.get_logger()

import counters
from database import Comment, User, Submission


def filter_recent_posts(subreddit):
	for submission in subreddit.sub_object.new(limit=100):
		if submission.author is None or submission.author.name not in subreddit.filtered_users:
			continue
		if submission.approved and len(submission.user_reports):
			log.info(f"Post {submission.id} by filtered user u/{submission.author.name} that was approved has been reported again, approving")
			submission.mod.approve()
		submission_datetime = datetime.utcfromtimestamp(submission.created_utc)
		if submission_datetime > datetime.utcnow() - timedelta(hours=1):
			continue  # not an hour old yet
		if submission_datetime < datetime.utcnow() - timedelta(hours=2):
			break  # more than two hours old, stop looking

		if submission.score <= 0:
			log.warning(
				f"Post {submission.id} by filtered user u/{submission.author.name} is {(datetime.utcnow() - submission_datetime).total_seconds() / 60} "
				f"minutes old and has no upvotes, removing : <https://www.reddit.com{submission.permalink}>")
			submission.mod.remove()
