import discord_logging
from sqlalchemy.sql import func
import sys
from datetime import datetime, timedelta

log = discord_logging.init_logging()

from database import Comment, User, Submission, Database


database = Database()

username = "USDeptofLabor"
subreddit_id = 2
log.info(f"Looking up u/{username}")
db_author = database.session.query(User).filter_by(name=username).first()
if db_author is None:
	log.info("User doesn't exist")
	sys.exit()

min_comment_date = datetime.utcnow() - timedelta(days=30)
count_comments = database.session.query(Comment)\
	.filter(Comment.subreddit_id == subreddit_id)\
	.filter(Comment.author == db_author)\
	.count()
log.info(f"Total: {count_comments}")
count_comments = database.session.query(Comment)\
	.filter(Comment.subreddit_id == subreddit_id)\
	.filter(Comment.author == db_author)\
	.filter(Comment.is_removed == True)\
	.count()
log.info(f"Removed: {count_comments}")
count_comments = database.session.query(Comment)\
	.filter(Comment.subreddit_id == subreddit_id)\
	.filter(Comment.author == db_author)\
	.filter(Comment.is_deleted == True)\
	.count()
log.info(f"Deleted: {count_comments}")
count_comments = database.session.query(Comment)\
	.filter(Comment.subreddit_id == subreddit_id)\
	.filter(Comment.author == db_author)\
	.filter(Comment.is_removed == False)\
	.filter(Comment.created < min_comment_date)\
	.count()
log.info(f"Before threshold: {count_comments}")
count_comments = database.session.query(Comment)\
	.filter(Comment.subreddit_id == subreddit_id)\
	.filter(Comment.author == db_author)\
	.filter(Comment.is_removed == False)\
	.filter(Comment.created < datetime.utcnow() - timedelta(days=30-7))\
	.count()
log.info(f"Before threshold, plus one week: {count_comments}")
count_comments = database.session.query(Comment)\
	.filter(Comment.subreddit_id == subreddit_id)\
	.filter(Comment.author == db_author)\
	.filter(Comment.is_removed == False)\
	.filter(Comment.created < datetime.utcnow() - timedelta(days=30-7-7))\
	.count()
log.info(f"Before threshold, plus two weeks: {count_comments}")

count_karma = database.session.query(func.sum(Comment.karma).label('karma'))\
	.filter(Comment.subreddit_id == subreddit_id)\
	.filter(Comment.author == db_author)\
	.filter(Comment.created < min_comment_date)\
	.scalar()
count_karma_total = database.session.query(func.sum(Comment.karma).label('karma'))\
	.filter(Comment.subreddit_id == subreddit_id)\
	.filter(Comment.author == db_author)\
	.filter(Comment.created < min_comment_date)\
	.scalar()
log.info(f"Total karma: {count_karma_total}")
log.info(f"Before threshold karma: {count_karma}")
