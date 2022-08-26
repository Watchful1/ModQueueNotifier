import discord_logging
import praw
import prawcore
from datetime import datetime

log = discord_logging.init_logging()

from database import Comment, User, Submission, Database


database = Database()
reddit = praw.Reddit("Watchful1")

users = database.session.query(User).filter_by(created=None).all()
log.info(f"Processing {len(users)} users")
processed = 0
deleted = 0
for user in users:
	processed += 1
	try:
		r_user = reddit.redditor(user.name)
		user_created = datetime.utcfromtimestamp(r_user.created_utc)
		user.created = user_created
	except prawcore.exceptions.NotFound:
		user.is_deleted = True
		deleted += 1
	except AttributeError:
		user.is_deleted = True
		deleted += 1

	if processed % 100 == 0:
		log.info(f"{processed}/{len(users)} : {deleted}")
		database.session.commit()

log.info(f"Done {len(users)}")
database.session.commit()
database.engine.dispose()
