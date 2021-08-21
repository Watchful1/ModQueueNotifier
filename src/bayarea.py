import discord_logging
from sqlalchemy.sql import func
from datetime import datetime, timedelta

log = discord_logging.get_logger()

import counters
from database import Comment, User, Submission


def author_restricted(subreddit, database, db_author):
	min_comment_date = datetime.utcnow() - timedelta(days=subreddit.restricted['comment_days'])
	count_comments = database.session.query(Comment)\
		.filter(Comment.author == db_author)\
		.filter(Comment.is_removed == False)\
		.filter(Comment.created < min_comment_date)\
		.count()
	if count_comments < subreddit.restricted['comments']:
		return f"comments {count_comments} < {subreddit.restricted['comments']}"

	count_karma = database.session.query(func.sum(Comment.karma).label('karma'))\
		.filter(Comment.author == db_author)\
		.filter(Comment.created < min_comment_date)\
		.scalar()
	if count_karma < subreddit.restricted['karma']:
		return f"karma {count_karma} < {subreddit.restricted['karma']}"

	return None


def add_submission(subreddit, database, db_submission, reddit_submission):
	flair_restricted = subreddit.flair_restricted(reddit_submission.link_flair_text)
	reprocess_submission = False
	if db_submission is None:
		db_submission = Submission(
			submission_id=reddit_submission.id,
			created=datetime.utcfromtimestamp(reddit_submission.created_utc),
			is_restricted=flair_restricted
		)
		database.session.add(db_submission)
		reprocess_submission = flair_restricted

	elif db_submission.is_restricted is not flair_restricted:
		db_submission.is_restricted = flair_restricted
		reprocess_submission = flair_restricted

	if reprocess_submission:
		log.info(f"Marking submission {reddit_submission.id} as restricted")
		bot_comment = reddit_submission.reply(
			"Due to the topic, enhanced moderation has been turned on for this thread. Comments from users new "
			"to r/bayarea will be automatically removed. See [this thread](https://www.reddit.com/r/bayarea/comments/p8hnzl/automatically_removing_comments_from_new_users_in/) for more details.")
		bot_comment.mod.distinguish(how="yes", sticky=True)

		comments = database.session.query(Comment)\
			.join(Submission)\
			.filter(Submission.submission_id == reddit_submission.id)\
			.all()
		if len(comments) > 0:
			log.info(f"Reprocessing submission {reddit_submission.id} with {len(comments)} comments")
			author_dict = {}
			count_removed = 0
			for comment in comments:
				if comment.author.name in author_dict:
					author_result = author_dict[comment.author.name]
				else:
					author_result = author_restricted(subreddit, database, comment.author)
					author_dict[comment.author.name] = author_result

				if author_result is None:
					continue
				else:
					subreddit.reddit.comment(comment.comment_id).mod.remove(mod_note=f"filtered: {author_result}")
					comment.is_removed = True
					count_removed += 1
					log.info(f"Comment {comment.comment_id} by u/{comment.author.name} removed: {author_result}")
			log.warning(f"Finished submission https://www.reddit.com{reddit_submission.permalink}, removed {count_removed}/{len(comments)} comments")

	return db_submission


def ingest_comments(subreddit, database):
	for comment in subreddit.sub_object.comments(limit=None):
		if database.session.query(Comment).filter_by(comment_id=comment.id).count() > 0:
			break

		db_submission = database.session.query(Submission).filter_by(submission_id=comment.link_id[3:]).first()
		if db_submission is None:
			db_submission = add_submission(subreddit, database, None, comment.submission)

		db_user = database.session.query(User).filter_by(name=comment.author.name).first()
		if db_user is None:
			db_user = User(name=comment.author.name)
			database.session.add(db_user)

		db_comment = database.session.merge(Comment(
			comment_id=comment.id,
			author=db_user,
			submission=db_submission,
			created=datetime.utcfromtimestamp(comment.created_utc)
		))

		if db_submission.is_restricted:
			author_result = author_restricted(subreddit, database, db_user)
			if author_result is not None:
				counters.user_comments.labels(subreddit=subreddit.name, result="filtered").inc()
				comment.mod.remove(mod_note=f"filtered: {author_result}")
				db_comment.is_removed = True
				log.info(f"Comment {comment.id} by u/{comment.author.name} removed: {author_result}")
			else:
				counters.user_comments.labels(subreddit=subreddit.name, result="allowed").inc()
		else:
			counters.user_comments.labels(subreddit=subreddit.name, result="allowed").inc()


def check_flair_changes(subreddit, database):
	for log_item in subreddit.mod_log:
		if log_item.action == "editflair":
			submission_id = log_item.target_fullname[3:]
			add_submission(
				subreddit,
				database,
				database.session.query(Submission).filter_by(submission_id=submission_id).first(),
				subreddit.reddit.submission(submission_id)
			)


def backfill_karma(subreddit, database):
	max_comment_date = datetime.utcnow() - timedelta(hours=24)
	comments = database.session.query(Comment)\
		.filter(Comment.karma == None)\
		.filter(Comment.created < max_comment_date)\
		.all()
	fullnames = []
	comment_map = {}
	for comment in comments:
		fullnames.append(f"t1_{comment.comment_id}")
		comment_map[comment.comment_id] = comment

		if len(fullnames) >= 100 or len(fullnames) == len(comments):
			reddit_comments = subreddit.reddit.info(fullnames)
			for reddit_comment in reddit_comments:
				sub_comment = comment_map[reddit_comment.id]
				sub_comment.karma = reddit_comment.score
				if reddit_comment.body == "[removed]" or reddit_comment.banned_by is not None:
					counters.backfill_comments.labels(subreddit=subreddit.name, result="removed").inc()
					sub_comment.is_removed = True
				elif reddit_comment.body == "[deleted]":
					counters.backfill_comments.labels(subreddit=subreddit.name, result="deleted").inc()
					sub_comment.is_deleted = True
				else:
					counters.backfill_comments.labels(subreddit=subreddit.name, result="updated").inc()

				del comment_map[reddit_comment.id]

			if len(comment_map) > 0:
				counters.backfill_comments.labels(subreddit=subreddit.name, result="missing").inc(len(comment_map))
				log.warning(f"{len(comment_map)} comments missing when backfilling karma")

			comment_map = {}
			fullnames = []

# database clean
