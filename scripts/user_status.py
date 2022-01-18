import discord_logging
from sqlalchemy.sql import func
import sys
from datetime import datetime, timedelta

import database

log = discord_logging.init_logging()

from database import Comment, User, Submission


database.init()

username = "Talx_abt_politix"
log.info(f"Looking up u/{username}")
db_author = database.session.query(User).filter_by(name=username).first()
if db_author is None:
	log.info("User doesn't exist")
	sys.exit()

min_comment_date = datetime.utcnow() - timedelta(days=30)
count_comments = database.session.query(Comment)\
	.filter(Comment.author == db_author)\
	.filter(Comment.is_removed == False)\
	.filter(Comment.created < min_comment_date)\
	.count()
count_comments_total = database.session.query(Comment)\
	.filter(Comment.author == db_author)\
	.count()
count_comments_removed = database.session.query(Comment)\
	.filter(Comment.author == db_author)\
	.filter(Comment.is_removed == True)\
	.count()
count_comments_deleted = database.session.query(Comment)\
	.filter(Comment.author == db_author)\
	.filter(Comment.is_deleted == True)\
	.count()
log.info(f"Total: {count_comments_total}")
log.info(f"Removed: {count_comments_removed}")
log.info(f"Deleted: {count_comments_deleted}")
log.info(f"Before threshold: {count_comments}")

count_karma = database.session.query(func.sum(Comment.karma).label('karma'))\
	.filter(Comment.author == db_author)\
	.filter(Comment.created < min_comment_date)\
	.scalar()
count_karma_total = database.session.query(func.sum(Comment.karma).label('karma'))\
	.filter(Comment.author == db_author)\
	.filter(Comment.created < min_comment_date)\
	.scalar()
log.info(f"Total karma: {count_karma_total}")
log.info(f"Before threshold karma: {count_karma}")
