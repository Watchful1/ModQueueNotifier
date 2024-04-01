import sys

import discord_logging
from sqlalchemy.sql import func
from datetime import datetime, timedelta

log = discord_logging.init_logging()

from database import Comment, User, Submission, Database


if __name__ == "__main__":
	database = Database()
	username = "alicantetocomo"

	db_user = database.session.query(User).filter_by(name=username).first()
	if db_user is None:
		log.info(f"User {username} not found")
		sys.exit()

	recent_removed_submission = database.session.query(Submission) \
		.filter(Submission.author == db_user) \
		.filter(Submission.is_restricted == True) \
		.filter(Submission.is_removed == True) \
		.filter(Submission.created > datetime.utcnow() - timedelta(days=1)) \
		.order_by(Submission.created.desc()) \
		.first()
	log.info(f"{len(recent_removed_submission)}")
