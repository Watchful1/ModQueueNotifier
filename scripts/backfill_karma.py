import discord_logging
import praw
import prawcore
from datetime import datetime

log = discord_logging.init_logging()

import database
from database import Comment, User, Submission


database.init()
reddit = praw.Reddit("Watchful1")


comments = database.session.query(Comment).filter_by(karma=None).all()
log.info(f"Processing {len(comments)} comments")
fullnames = []
comment_map = {}
processed = 0
deleted = 0
removed = 0
missing = 0
for comment in comments:
	fullnames.append(f"t1_{comment.comment_id}")
	comment_map[comment.comment_id] = comment

	if len(fullnames) >= 100 or len(fullnames) == len(comments):
		reddit_comments = reddit.info(fullnames)
		for reddit_comment in reddit_comments:
			processed += 1
			sub_comment = comment_map[reddit_comment.id]
			sub_comment.karma = reddit_comment.score
			if reddit_comment.body == "[removed]":
				removed += 1
				sub_comment.is_removed = True
			elif reddit_comment.body == "[deleted]":
				deleted += 1
				sub_comment.is_deleted = True

			del comment_map[reddit_comment.id]

			if processed % 1000 == 0:
				log.info(f"{processed}/{len(comments)} : {removed} : {deleted} : {missing}")
				database.session.commit()

		if len(comment_map) > 0:
			missing += len(comment_map)
			log.info(f"{len(comment_map)} comments missing")

		comment_map = {}
		fullnames = []

log.info(f"Done {len(comments)}")
database.session.commit()
database.engine.dispose()
