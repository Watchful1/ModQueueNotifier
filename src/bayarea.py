import discord_logging
import prawcore.exceptions
import requests
import traceback
from sqlalchemy.sql import func
from datetime import datetime, timedelta

log = discord_logging.get_logger()

import counters
import utils
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


def get_comments_for_thread(subreddit, database, thread_id):
	comments = database.session.query(Comment) \
		.join(Submission) \
		.filter(Submission.submission_id == thread_id) \
		.all()

	author_dict = {}
	good_comments = []
	bad_comments_dict = {}
	fullnames = []
	for comment in comments:
		if comment.author.name in author_dict:
			author_result = author_dict[comment.author.name]
		else:
			author_result = author_comment_restricted(subreddit, database, comment.author)
			author_dict[comment.author.name] = author_result

		if author_result is None or comment.author.name == "CustomModBot":
			good_comments.append((comment, "good"))
		else:
			bad_comments_dict[comment.comment_id] = (comment, author_result)
			fullnames.append(f"t1_{comment.comment_id}")

	bad_comments = []
	try:
		for comment in subreddit.reddit.info(fullnames):
			if comment.score < 10:
				bad_comments.append(bad_comments_dict[comment.id])
			else:
				good_comments.append(bad_comments_dict[comment.id])
	except Exception as err:
		utils.process_error(f"Error loading comment scores when reprocessing thread", err, traceback.format_exc())

	return good_comments, bad_comments


def author_comment_restricted(subreddit, database, db_author):
	min_comment_date = datetime.utcnow() - timedelta(days=subreddit.restricted['comment_days'])
	count_comments = database.session.query(Comment)\
		.filter(Comment.subreddit_id == subreddit.sub_id)\
		.filter(Comment.author == db_author)\
		.filter(Comment.is_removed == False)\
		.filter(Comment.created < min_comment_date)\
		.count()
	count_submissions = database.session.query(Submission)\
		.filter(Submission.subreddit_id == subreddit.sub_id)\
		.filter(Submission.author == db_author)\
		.filter(Submission.is_removed == False)\
		.filter(Submission.created < min_comment_date)\
		.count()
	if count_comments + count_submissions < subreddit.restricted['comments']:
		return f"comments {count_comments} + {count_submissions} = {count_comments + count_submissions} < {subreddit.restricted['comments']}"

	count_comment_karma = database.session.query(func.sum(Comment.karma).label('karma'))\
		.filter(Comment.subreddit_id == subreddit.sub_id)\
		.filter(Comment.author == db_author)\
		.filter(Comment.created < min_comment_date)\
		.scalar()
	if count_comment_karma is None:
		count_comment_karma = 0
	count_submission_karma = database.session.query(func.sum(Submission.karma).label('karma'))\
		.filter(Submission.subreddit_id == subreddit.sub_id)\
		.filter(Submission.author == db_author)\
		.filter(Submission.created < min_comment_date)\
		.scalar()
	if count_submission_karma is None:
		count_submission_karma = 0
	if count_comment_karma + count_submission_karma < subreddit.restricted['karma']:
		return f"karma {count_comment_karma} + {count_submission_karma} = {count_comment_karma + count_submission_karma} < {subreddit.restricted['karma']}"

	return None


def action_comment(subreddit, comment, author_result):
	comment.is_author_restricted = True
	if subreddit.restricted['action'] == "remove":
		subreddit.reddit.comment(comment.comment_id).mod.remove()
		comment.is_removed = True
		log.info(f"Comment {comment.comment_id} by u/{comment.author.name} removed: {author_result}")
	elif subreddit.restricted['action'] == "report":
		subreddit.reddit.comment(comment.comment_id).report(f"sensitive report: {author_result}")
		log.info(f"Comment {comment.comment_id} by u/{comment.author.name} reported: {author_result}")
	else:
		log.warning(f"Invalid restriction action {subreddit.restricted['action']}")


def add_submission(subreddit, database, db_submission, reddit_submission):
	flair_restricted = subreddit.flair_restricted(reddit_submission.link_flair_text)
	reprocess_submission = False
	flair_changed = False
	if db_submission is None:
		db_user = database.session.query(User).filter_by(name=reddit_submission.author.name).first()
		if db_user is None:
			db_user = User(name=reddit_submission.author.name)
			database.session.add(db_user)

		db_submission = Submission(
			submission_id=reddit_submission.id,
			created=datetime.utcfromtimestamp(reddit_submission.created_utc),
			is_restricted=flair_restricted,
			author=db_user,
			subreddit_id=subreddit.sub_id
		)
		database.session.add(db_submission)
		reprocess_submission = flair_restricted

	elif db_submission.is_restricted is not flair_restricted:
		db_submission.is_restricted = flair_restricted
		reprocess_submission = flair_restricted
		flair_changed = True

	if reprocess_submission:
		log.info(f"Marking submission {reddit_submission.id} as restricted")

		db_user = db_submission.author
		comment_text = None
		if reddit_submission.is_self or (reddit_submission.selftext is not None and reddit_submission.selftext != ""):
			log.warning(
				f"[Submission](<https://www.reddit.com/r/{subreddit.name}/comments/{db_submission.submission_id}/>) by "
				f"u/{db_user.name} removed. Self posts not allowed"
			)

			# comment_text = \
			# 	f"This subreddit restricts submissions on sensitive topics from users who don't have an established history of posting in the subreddit. " \
			# 	f"You don't meet our requirements so your submission has been removed.\n\n" \
			# 	f"You can read more about this policy [here]() and [message the mods](https://www.reddit.com/message/compose/?to=/r/{subreddit.name}) " \
			# 	f"if you think this is a mistake."

		elif author_comment_restricted(subreddit, database, db_user):
			log.warning(
				f"[Submission](<https://www.reddit.com/r/{subreddit.name}/comments/{db_submission.submission_id}/>) by "
				f"u/{db_user.name} removed. Insufficient subreddit history"
			)

			# comment_text = \
			# 	f"This subreddit requires submissions on sensitive topics to be direct links to a news article. " \
			# 	f"Your submission was either a self post or a link that included submission text so it has been removed.\n\n" \
			# 	f"You can read more about this policy [here]() and [message the mods](https://www.reddit.com/message/compose/?to=/r/{subreddit.name}) " \
			# 	f"if you think this is a mistake."

		elif subreddit.days_between_restricted_submissions is not None:
			submission_filter_date = datetime.utcnow() - timedelta(days=subreddit.days_between_restricted_submissions)
			previous_submission = database.session.query(Submission) \
				.filter(Submission.submission_id != db_submission.submission_id) \
				.filter(Submission.author == db_user) \
				.filter(Submission.is_restricted == True) \
				.filter(Submission.is_removed == False)\
				.filter(Submission.created > submission_filter_date) \
				.order_by(Submission.created.desc()) \
				.first()

			if previous_submission is not None:
				log.warning(
					f"[Submission](<https://www.reddit.com/r/{subreddit.name}/comments/{db_submission.submission_id}/>) by "
					f"u/{db_user.name} removed. "
					f"[Recent submission](<https://www.reddit.com/r/{subreddit.name}/comments/{previous_submission.submission_id}/>) "
					f"from {(datetime.utcnow() - previous_submission.created).days} days ago."
				)

				# comment_text = \
				# 	f"This subreddit restricts submissions on sensitive topics to once every " \
				# 	f"{subreddit.days_between_restricted_submissions} days per user. Since your previous sensitive topic [submission]" \
				# 	f"(https://www.reddit.com/r/{subreddit.name}/comments/{previous_submission.submission_id}) was " \
				# 	f"{(datetime.utcnow() - previous_submission.created).days} days ago, this one has been removed.\n\n" \
				# 	f"You can read more about this policy [here]() and [message the mods](https://www.reddit.com/message/compose/?to=/r/{subreddit.name}) " \
				# 	f"if you think this is a mistake."

				if flair_changed:
					log.warning(f"Banning u/{db_user.name} for {subreddit.days_between_restricted_submissions} days due to incorrectly flaired submission")
					# ban_message = f"Your [recent submission](https://www.reddit.com/r/{subreddit.name}/comments/{db_submission.submission_id}/) was incorrectly " \
					# 	f"flaired. Since the correct flair would have indicated it was a sensitive topic and you posted another [sensitive topic submission]" \
					# 	f"(https://www.reddit.com/r/{subreddit.name}/comments/{previous_submission.submission_id}) within the last " \
					# 	f"{subreddit.days_between_restricted_submissions} days, you have been automatically banned.\n\n" \
					# 	f"You can read more about this policy [here]() and reply to this message if you think this is a mistake."
					#
					# subreddit.sub_object.banned.add(
					# 	db_user.name,
					# 	duration=subreddit.days_between_restricted_submissions,
					# 	ban_reason=f"Deliberate incorrect flair",
					# 	ban_message=ban_message)
					# utils.add_usernote(
					# 	subreddit,
					# 	db_user.name,
					# 	subreddit.get_account_name(),
					# 	"spamwarn",
					# 	f"{subreddit.days_between_restricted_submissions}d - incorrect flair",
					# 	f"https://www.reddit.com/r/{subreddit.name}/comments/{db_submission.submission_id}/")

		if comment_text is not None:
			comment_count = database.session.query(Comment).filter(Comment.submission_id == db_submission.submission_id).count()
			if comment_count >= 10:
				log.warning(f"Not removing submission because it has {comment_count} comments")
			else:
				reddit_submission.mod.remove()
				reddit_submission.mod.lock()
				bot_comment = reddit_submission.reply(comment_text)
				subreddit.approve_comment(bot_comment, True)

		elif subreddit.restricted['action'] == "remove":
			bot_comment = reddit_submission.reply(
				"Due to the topic, enhanced moderation has been turned on for this thread. Comments from users new "
				"to r/bayarea will be automatically removed. See [this thread](https://www.reddit.com/r/bayarea/comments/p8hnzl/automatically_removing_comments_from_new_users_in/) for more details.")
			# bot_comment = reddit_submission.reply(
			# 	f"The flair of this posts indicates it's a controversial topic. Enhanced moderation has been turned on for this thread. Comments from users without a history of commenting in r/{subreddit.name} "
			# 	"will be automatically removed. You can read more about this policy [here]().")
			subreddit.approve_comment(bot_comment, True)

		good_comments, bad_comments = get_comments_for_thread(subreddit, database, reddit_submission.id)
		if len(bad_comments) + len(good_comments) > 0:
			log.info(f"Reprocessing submission {reddit_submission.id} with {len(good_comments) + len(bad_comments)} comments")
			for comment, author_result in bad_comments:
				action_comment(subreddit, comment, author_result)
			log.warning(f"Finished submission <https://www.reddit.com{reddit_submission.permalink}>, removed {len(bad_comments)}/{len(good_comments) + len(bad_comments)} comments")

	return db_submission


def ingest_submissions(subreddit, database):
	for submission in subreddit.sub_object.new(limit=25):
		db_submission = database.session.query(Submission).filter_by(submission_id=submission.id).first()
		if db_submission is None:
			db_submission = add_submission(subreddit, database, None, submission)


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
			created=datetime.utcfromtimestamp(comment.created_utc),
			subreddit_id=subreddit.sub_id
		))

		if db_submission.is_restricted and comment.author.name != "CustomModBot":
			author_result = author_comment_restricted(subreddit, database, db_user)
			if author_result is not None:
				counters.user_comments.labels(subreddit=subreddit.name, result="filtered").inc()
				action_comment(subreddit, db_comment, author_result)
			else:
				counters.user_comments.labels(subreddit=subreddit.name, result="allowed").inc()
		else:
			counters.user_comments.labels(subreddit=subreddit.name, result="allowed").inc()

			if not db_submission.is_notified:
				age_in_hours = int((datetime.utcnow() - db_submission.created).total_seconds()) / (60 * 60)
				if age_in_hours < 2 and database.session.query(Comment).filter(Comment.submission == db_submission).count() > 50:
					good_comments, bad_comments = get_comments_for_thread(subreddit, database, db_submission.submission_id)
					notify_string = f"Non-moderated submission is {round(age_in_hours, 1)} hours old with {len(good_comments)} comments from good accounts and {len(bad_comments)} comments from accounts with low history: <https://www.reddit.com/r/{subreddit.name}/comments/{db_submission.submission_id}/>"
					log.info(notify_string)
					subreddit.post_to_discord(notify_string)
					db_submission.is_notified = True


def check_flair_changes(subreddit, database):
	if len(subreddit.mod_log):
		for log_item in subreddit.mod_log:
			if log_item.action == "editflair":
				submission_id = log_item.target_fullname[3:]
				add_submission(
					subreddit,
					database,
					database.session.query(Submission).filter_by(submission_id=submission_id).first(),
					subreddit.reddit.submission(submission_id)
				)
	else:
		for log_item in subreddit.sub_object.mod.log(limit=20, action="editflair"):
			if log_item.target_fullname is None:
				continue
			submission_id = log_item.target_fullname[3:]
			if database.session.query(Submission).filter_by(submission_id=submission_id).filter_by(is_restricted=True).count() > 0:
				break
			add_submission(
				subreddit,
				database,
				database.session.query(Submission).filter_by(submission_id=submission_id).first(),
				subreddit.reddit.submission(submission_id)
			)


def backfill_karma(subreddit, database):
	max_date = datetime.utcnow() - timedelta(hours=24)
	fullnames = []
	object_map = {}
	for comment in database.session.query(Comment)\
			.filter(Comment.karma == None)\
			.filter(Comment.created < max_date)\
			.filter(Comment.subreddit_id == subreddit.sub_id)\
			.limit(1000)\
			.all():
		fullnames.append(comment.fullname())
		object_map[comment.fullname()] = comment
	for submission in database.session.query(Submission)\
			.filter(Submission.karma == None)\
			.filter(Submission.created < max_date)\
			.filter(Submission.subreddit_id == subreddit.sub_id)\
			.limit(1000)\
			.all():
		fullnames.append(submission.fullname())
		object_map[submission.fullname()] = submission

	if len(fullnames) > 0:
		reddit_objects = subreddit.reddit.info(fullnames)
		for reddit_object in reddit_objects:
			db_object = object_map[reddit_object.name]
			db_object.karma = reddit_object.score
			obj_type = "object"
			result = "updated"
			if reddit_object.name.startswith("t1_"):
				obj_type = "comment"
				if reddit_object.body == "[removed]" or reddit_object.banned_by is not None:
					result = "removed"
					db_object.is_removed = True
				elif reddit_object.body == "[deleted]":
					result = "deleted"
					db_object.is_deleted = True
			elif reddit_object.name.startswith("t3_"):
				obj_type = "submission"
				if (reddit_object.removed_by_category in
						{"moderator", "anti_evil_ops", "community_ops", "legal_operations", "copyright_takedown", "reddit", "author", "automod_filtered"} or
						reddit_object.banned_by is not None):
					result = "removed"
					db_object.is_removed = True
				elif reddit_object.removed_by_category == "deleted":
					result = "deleted"
					db_object.is_deleted = True
				elif reddit_object.removed_by_category is None:
					pass  # not removed
				else:
					result = "removed"
					db_object.is_removed = True
					log.warning(f"Unknown removed category : {reddit_object.removed_by_category} : <https://www.reddit.com/r/{subreddit.name}/comments/{db_object.submission_id}/>")

				# if subreddit.flair_restricted(reddit_object.link_flair_text) and not db_object.is_restricted:
				# 	log.warning(
				# 		f"User may have added restricted flair after submitting : "
				# 		f"<https://www.reddit.com/r/{subreddit.name}/comments/{db_object.submission_id}/>")
			else:
				log.warning(f"Something went wrong backfilling karma. Unknown object type: {reddit_object.name}")
			counters.backfill.labels(subreddit=subreddit.name, type=obj_type, result=result).inc()

			del object_map[reddit_object.name]

		if len(object_map) > 0:
			counters.backfill.labels(subreddit=subreddit.name, type="object", result="missing").inc(len(object_map))
			log.warning(f"{len(object_map)} objects missing when backfilling karma for r/{subreddit.name}. {(','.join(object_map.keys()))} : {(','.join(fullnames))}")
