import discord_logging
from sqlalchemy.sql import func
from datetime import datetime, timedelta

log = discord_logging.init_logging()

import database
from database import Comment, User, Submission


def author_restricted(subreddit, database, db_author):
	min_comment_date = datetime.utcnow() - timedelta(days=subreddit['comment_days'])
	count_comments = database.session.query(Comment)\
		.filter(Comment.author == db_author)\
		.filter(Comment.is_removed == False)\
		.filter(Comment.created < min_comment_date)\
		.count()
	if count_comments < subreddit['comments']:
		return f"comments {count_comments} < {subreddit['comments']}"

	count_karma = database.session.query(func.sum(Comment.karma).label('karma'))\
		.filter(Comment.author == db_author)\
		.filter(Comment.created < min_comment_date)\
		.scalar()
	if count_karma < subreddit['karma']:
		return f"karma {count_karma} < {subreddit['karma']}"

	return None


database.init()
reddit_submission_id = "p7k8bv"
bay_area = {
	'flairs': {"Politics"},
	'comment_days': 30,
	'comments': 10,
	'karma': 20
}

comments = database.session.query(Comment)\
	.join(Submission)\
	.filter(Submission.submission_id == reddit_submission_id)\
	.all()
if len(comments) > 0:
	log.info(f"Reprocessing submission {reddit_submission_id} with {len(comments)} comments")
	author_dict = {}
	count_removed = 0
	removed_authors = set()
	for comment in comments:
		if comment.author.name in author_dict:
			author_result = author_dict[comment.author.name]
		else:
			author_result = author_restricted(bay_area, database, comment.author)
			author_dict[comment.author.name] = author_result

		if author_result is None:
			continue
		else:
			#subreddit.reddit.comment(comment.comment_id).mod.remove()
			#comment.is_removed = True
			count_removed += 1
			removed_authors.add(comment.author.name)
			log.info(f"Comment {comment.comment_id} by u/{comment.author.name} removed: {author_result}")
	log.warning(f"Finished submission {reddit_submission_id}, removed {count_removed}/{len(comments)} comments from {len(removed_authors)} authors")

	for author in removed_authors:
		log.info(f"https://www.reddit.com/user/{author}")
