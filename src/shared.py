import discord_logging
import math
import requests
import traceback
import prawcore.exceptions
from collections import defaultdict
from datetime import datetime, timedelta
from sqlalchemy.sql import func, text

log = discord_logging.get_logger()

import counters
import utils
import static
from database import LogItem, Comment, User, Submission
from classes import UserNotes, Note


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
	if count_comments < subreddit.restricted['comments']:
		return f"comments {count_comments} < {subreddit.restricted['comments']}"

	count_karma = database.session.query(func.sum(Comment.karma).label('karma'))\
		.filter(Comment.subreddit_id == subreddit.sub_id)\
		.filter(Comment.author == db_author)\
		.filter(Comment.created < min_comment_date)\
		.scalar()
	if count_karma < subreddit.restricted['karma']:
		return f"karma {count_karma} < {subreddit.restricted['karma']}"

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
		if reddit_submission.is_self or reddit_submission.selftext is not None:
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
					#requests.post(subreddit.webhook, data={"content": notify_string})
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
			.all():
		fullnames.append(comment.fullname())
		object_map[comment.fullname()] = comment
	# for submission in database.session.query(Submission)\
	# 		.filter(Submission.karma == None)\
	# 		.filter(Submission.created < max_date)\
	# 		.filter(Submission.subreddit_id == subreddit.sub_id)\
	# 		.all():
	# 	fullnames.append(submission.fullname())
	# 	object_map[submission.fullname()] = submission

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
				else:
					result = "removed"
					db_object.is_removed = True
					log.warning(f"Unknown removed category : {reddit_object.removed_by_category} : <https://www.reddit.com/r/{subreddit.name}/comments/{db_object.submission_id}/>")

				if subreddit.flair_restricted(reddit_object.link_flair_text) and not db_object.is_restricted:
					log.warning(
						f"User may have added restricted flair after submitting : "
						f"<https://www.reddit.com/r/{subreddit.name}/comments/{db_object.submission_id}/>")
			else:
				log.warning(f"Something went wrong backfilling karma. Unknown object type: {reddit_object.name}")
			counters.backfill.labels(subreddit=subreddit.name, type=obj_type, result=result).inc()

			del object_map[reddit_object.name]

		if len(object_map) > 0:
			counters.backfill.labels(subreddit=subreddit.name, type="object", result="missing").inc(len(object_map))
			log.warning(f"{len(object_map)} objects missing when backfilling karma for r/{subreddit.name}. {(','.join(object_map.keys()))} : {(','.join(fullnames))}")


def ingest_log(subreddit, database):
	subreddit.mod_log = []
	for log_item in subreddit.sub_object.mod.log(limit=None):
		if database.session.query(LogItem).filter_by(id=log_item.id).count() > 0:
			break

		subreddit.mod_log.append(log_item)

		counters.mod_actions.labels(moderator=log_item.mod.name, subreddit=subreddit.name).inc()

		warning_type = None
		warning_items = []
		if log_item.mod.name not in subreddit.moderators:
			warning_type = "1"
			if log_item.action in {'removecomment', 'removelink', 'marknsfw'}:
				warning_items.append(f"[{log_item.target_title}](<https://www.reddit.com/{log_item.target_permalink}>) by u/{log_item.target_author}")
		elif subreddit.warning_log_types is not None and log_item.action in subreddit.warning_log_types:
			sub_filters = subreddit.warning_log_types[log_item.action]
			for item, value in sub_filters.items():
				if item == "print":
					for field_name in value:
						warning_items.append(getattr(log_item, field_name))
					continue
				log_item_value = getattr(log_item, item)
				if value.startswith("!"):
					if value == "!":
						if log_item_value is None:
							warning_type = "5"
						else:
							warning_type = None
							break
					elif log_item_value != value[1:]:
						warning_type = "4"
					else:
						warning_type = None
						break
				elif value.startswith("~"):
					if value[1:] in log_item_value:
						warning_type = "6"
					else:
						warning_type = None
						break
				elif log_item_value == value:
					warning_type = "3"
				else:
					warning_type = None
					break
		elif log_item.action not in subreddit.known_log_types:
			warning_type = "2"

		if warning_type is not None:
			log.warning(
				f"r/{subreddit.name}: {warning_type}:Mod action by u/{log_item.mod.name}: {log_item.action} {' '.join(warning_items)}")

		database.session.merge(LogItem(log_item))
	discord_logging.flush_discord()


def process_modqueue_reapprove(subreddit):
	for item in list(subreddit.modqueue()):
		if item.approved:
			approve = True
			if len(subreddit.reapprove_reasons):
				for report in item.user_reports:
					if report[0] not in subreddit.reapprove_reasons:
						approve = False
						break

			if approve:
				log.info(f"Reapproving item: {item.id}")
				item.mod.approve()
				subreddit.modqueue().remove(item)


def process_modqueue_old(subreddit):
	for item in list(subreddit.modqueue()):
		item_date = datetime.utcfromtimestamp(item.created_utc)
		if item_date < datetime.utcnow() - timedelta(days=180):
			log.info(f"r/{subreddit.name}: [Old item in modqueue](https://www.reddit.com/{item.permalink}), automatically removing")
			item.mod.remove()


def process_modqueue_comments(subreddit):
	for item in list(subreddit.modqueue()):
		if item.fullname.startswith("t1_") and len(item.mod_reports):
			for report_reason, mod_name in item.mod_reports:
				items = report_reason.split(" ")
				if items[0].lower() in subreddit.comment_report_reasons:
					report_object = subreddit.comment_report_reasons[items[0].lower()]
					days = None
					action_string = "error, invalid action"
					additional_note = None
					if len(items) > 1:
						if items[1] == 'w':
							log.info(f"Processing new warning comment report: {report_reason}")
							days = 0
							action_string = "warned"
						elif items[1] == 'p':
							log.info(f"Processing new permaban comment report: {report_reason}")
							days = -1
							action_string = "permabanned"
						else:
							try:
								days = int(items[1])
								log.info(f"Processing new {days} day ban comment report: {report_reason}")
								action_string = f"banned for {days} days"
							except ValueError:
								additional_note = ' '.join(items[1:])
								pass

					if additional_note is None and len(items) > 2:
						additional_note = ' '.join(items[2:])

					sub_notes = utils.get_usernotes(subreddit)
					username = item.author.name
					user_note = sub_notes.get_user_note(username)
					if days is None:
						if user_note is not None:
							days_ban, note_is_old = user_note.get_recent_warn_ban()
							log.info(f"Processing new comment report: {report_reason}. Got {days_ban} days ban from notes")
						else:
							days_ban, note_is_old = None, False
							log.info(f"Processing new comment report: {report_reason}. No usernotes")
						days = subreddit.get_next_ban_tier(days_ban, note_is_old)
						if days == -1:
							action_string = "permabanned based on usernotes"
						elif days == 0:
							action_string = "warned based on usernotes"
						else:
							action_string = f"banned for {days} days based on usernotes"

					item_link = f"https://www.reddit.com{item.permalink}"
					reason_text = report_object['reason']
					if additional_note is not None:
						reason_text = reason_text + "\n\n" + additional_note
					warn_ban_message = f"{reason_text}\n\n{item_link}"
					if subreddit.name_in_modmails:
						warn_ban_message += f"\n\nFrom u/{mod_name}"
					if days == 0:
						log.info(f"Warning u/{username}, rule {report_object['rule']} from u/{mod_name}")
						item.author.message(
							f"Rule {report_object['rule']} warning",
							warn_ban_message,
							from_subreddit=subreddit.name)
						log.warning(f"Searching for modmail to archive after warn:")
						for conversation in list(subreddit.all_modmail()):
							log.warning(f"{conversation.id} : {len(conversation.authors)} authors : u/{conversation.authors[0].name} : {len(conversation.messages)} messages")
							if len(conversation.authors) == 2 and \
									conversation.authors[0].name in {subreddit.get_account_name(), username} and \
									conversation.authors[1].name in {subreddit.get_account_name(), username} and \
									len(conversation.messages) == 1:
								log.warning(f"Archiving {conversation.authors[0].name} message: {conversation.id}")
								conversation.archive()
								subreddit.all_modmail().remove(conversation)
								break

						note = Note.build_note(sub_notes, mod_name, "abusewarn", report_object['short_reason'], datetime.utcnow(), item_link)
					else:
						if days == -1:
							log.warning(f"Banning u/{username} permanently, rule {report_object['rule']} from u/{mod_name}")
							subreddit.sub_object.banned.add(
								item.author,
								ban_reason=f"{report_object['short_reason']} u/{mod_name}",
								ban_message=warn_ban_message)
							note = Note.build_note(sub_notes, mod_name, "permban", report_object['short_reason'], datetime.utcnow(), item_link)
						else:
							log.info(f"Banning u/{username} for {days} days, rule {report_object['rule']} from u/{mod_name}")
							subreddit.sub_object.banned.add(
								item.author,
								duration=days,
								ban_reason=f"{report_object['short_reason']} u/{mod_name}",
								ban_message=warn_ban_message)
							note = Note.build_note(sub_notes, mod_name, "ban", f"{days}d - {report_object['short_reason']}", datetime.utcnow(), item_link)

					if user_note is not None:
						user_note.add_new_note(note)
					else:
						user_note = UserNotes(username)
						user_note.add_new_note(note)
						sub_notes.add_update_user_note(user_note)
					utils.save_usernotes(subreddit, sub_notes, f"\"create new note on user {username}\" via {subreddit.get_account_name()}")

					count_removed = utils.recursive_remove_comments(item)
					if count_removed > 1:
						log.info(f"Recursively removed {count_removed} comments")

					log.warning(f"r/{subreddit.name}:u/{mod_name}: u/{username} {action_string}")

					subreddit.modqueue().remove(item)
					break


def process_modqueue_submissions(subreddit):
	for item in list(subreddit.modqueue()):
		if len(subreddit.report_reasons) and item.fullname.startswith("t3_") and len(item.mod_reports):
			for report_reason, mod_name in item.mod_reports:
				if report_reason in subreddit.report_reasons:
					removal_dict = subreddit.report_reasons[report_reason]
					log.info(f"Removing post {item.id} for rule {removal_dict['rule']} from u/{mod_name}")
					item.mod.remove()
					item.mod.lock()
					item.mod.flair("Removed")
					subreddit.modqueue().remove(item)

					comment = item.reply(
						f"{static.REMOVAL_REASON_HEADER.format(subreddit.name)}\n\n{removal_dict['reason']}\n\n"
						f"{static.REMOVAL_REASON_FOOTER.format(subreddit.name)}\n\nTriggered by mod {mod_name}")
					comment.mod.distinguish(how="yes", sticky=True)

					break


def log_highlighted_modmail(subreddit, start_time):
	for conversation in subreddit.all_modmail():
		if utils.conversation_is_unread(conversation):
			conversation_type = None
			if len([author for author in conversation.authors if author.is_admin]) > 0:
				conversation_type = "Admin"
			elif conversation.is_highlighted:
				conversation_type = "Highlighted"
			if conversation_type is not None and utils.conversation_not_processed(
					conversation, subreddit.processed_modmails, start_time):
				log.warning(
					f"r/{subreddit.name}: {conversation_type} modmail has a new reply: https://mod.reddit.com/mail/all/{conversation.id}")
				subreddit.processed_modmails[conversation.id] = utils.parse_modmail_datetime(conversation.last_updated)


def ignore_modmail_requests(subreddit):
	for conversation in subreddit.all_modmail():
		if len(conversation.messages) <= 1:
			log.info(f"Auto-archiving modmail from {conversation.authors[0].name}")
			conversation.reply(
				author_hidden=True,
				body=f'''This is an automated reply. If you are not asking to join the subreddit, please reply again to this message and we will look at it shortly.

We have closed the subreddit due to the upcoming API changes that will kill off 3rd party apps and negatively impact users and mods alike. Read the following for more info and join us on our discord while the subreddit is disabled:

{subreddit.discord_link}  
https://www.reddit.com/r/Save3rdPartyApps/comments/13yh0jf/dont_let_reddit_kill_3rd_party_apps/'''
			)
			conversation.archive()


def log_archived_modmail_no_response(subreddit, start_time):
	for conversation in subreddit.archived_modmail():
		if conversation.last_user_update is not None and \
				(conversation.last_mod_update is None or utils.parse_modmail_datetime(
					conversation.last_mod_update) < utils.parse_modmail_datetime(
					conversation.last_user_update)) and \
				utils.conversation_not_processed(conversation, subreddit.processed_modmails, start_time):
			archived_by = conversation.mod_actions[-1].author.name
			if archived_by != "Watchful1":
				log.warning(
					f"Modmail archived without reply: https://mod.reddit.com/mail/arvhiced/{conversation.id} by u/{archived_by}")
			subreddit.processed_modmails[conversation.id] = utils.parse_modmail_datetime(conversation.last_updated)


def count_queues(subreddit):
	if subreddit.thresholds['modmail']['track']:
		oldest_modmail = datetime.utcnow()
		for conversation in subreddit.combined_modmail():
			if not conversation.is_highlighted:
				subreddit.mail_count += 1
				modmail_age = utils.parse_modmail_datetime(conversation.last_updated)
				if modmail_age < oldest_modmail:
					oldest_modmail = modmail_age

		subreddit.oldest_modmail_hours = math.trunc((datetime.utcnow() - oldest_modmail).seconds / (60 * 60))

		counters.queue_size.labels(type='modmail', subreddit=subreddit.name).set(subreddit.mail_count)
		counters.queue_size.labels(type='modmail_hours', subreddit=subreddit.name).set(subreddit.oldest_modmail_hours)

	if subreddit.thresholds['unmod']['track']:
		oldest_unmod = datetime.utcnow()
		for submission in subreddit.sub_object.mod.unmoderated():
			subreddit.unmod_count += 1
			oldest_unmod = datetime.utcfromtimestamp(submission.created_utc)
			subreddit.oldest_unmod_link = f"https://www.reddit.com{submission.permalink}"

		subreddit.oldest_unmod_hours = math.trunc((datetime.utcnow() - oldest_unmod).seconds / (60 * 60))

		counters.queue_size.labels(type='unmod', subreddit=subreddit.name).set(subreddit.unmod_count)
		counters.queue_size.labels(type='unmod_hours', subreddit=subreddit.name).set(subreddit.oldest_unmod_hours)

	if subreddit.thresholds['modqueue']['track']:
		subreddit.reported_count = len(list(subreddit.sub_object.mod.modqueue(limit=None)))

		counters.queue_size.labels(type='modqueue', subreddit=subreddit.name).set(subreddit.reported_count)

	log.debug(
		f"r/{subreddit.name}: Unmod: {subreddit.unmod_count}, age: {subreddit.oldest_unmod_hours}, "
		f"modqueue: {subreddit.reported_count}, modmail: {subreddit.mail_count}, "
		f"modmail hours: {subreddit.oldest_modmail_hours}")


def ping_queues(subreddit, database):
	count_string = subreddit.ping_string()

	if subreddit.last_posted is None or datetime.utcnow() - timedelta(hours=1) > subreddit.last_posted:
		if count_string is not None:
			log.info(f"Posting: {count_string}")
			requests.post(subreddit.webhook, data={"content": count_string})
			subreddit.last_posted = datetime.utcnow()
			subreddit.has_posted = True
		else:
			subreddit.has_posted = False
	else:
		if subreddit.has_posted and (subreddit.unmod_count == 0 and subreddit.reported_count == 0 and subreddit.mail_count == 0):
			log.info("Queue clear, figuring out who cleared it")
			mods = defaultdict(int)
			for item in database.session.query(LogItem).filter_by(subreddit=subreddit.case_sensitive_name).order_by(LogItem.created.desc()).limit(100).all():
				minutes_old = (datetime.utcnow() - item.created).seconds / 60
				if item.mod not in ("OWMatchThreads", "AutoModerator"):
					mods[item.mod] += 1
				if minutes_old > 40:
					break
			mod_clear = None
			mod_count = 2
			for mod in mods:
				if mods[mod] > mod_count:
					mod_clear = mod
					mod_count = mods[mod]

			if mod_clear is not None:
				clear_string = f"{mod_clear} cleared the queues!"
				log.info(clear_string)
				requests.post(subreddit.webhook, data={"content": clear_string})
			else:
				log.info("Couldn't figure out who cleared the queue")

			subreddit.has_posted = False


def post_overlapping_actions(subreddit, database):
	result = database.session.execute(text(f'''
select l1.mod, l1.action, l2.mod, l2.action, l1.target_fullname, l1.target_permalink
from log l1
	left join log l2
		on l1.target_fullname = l2.target_fullname
			and l1.id != l2.id
			and l1.action != l2.action
			and l1.mod != l2.mod
			and l1.created < l2.created
where l1.subreddit = '{subreddit.case_sensitive_name}'
	and l1.action in ('approvecomment','approvelink','removecomment','removelink')
	and l2.action in ('approvecomment','approvelink','removecomment','removelink')
	and l1.mod not in ('OWMatchThreads','AutoModerator','CustomModBot')
	and l2.mod not in ('OWMatchThreads','AutoModerator','CustomModBot')
	and ROUND((JULIANDAY(l2.created) - JULIANDAY(l1.created)) * 86400) < 3600
	and ROUND((JULIANDAY(current_timestamp) - JULIANDAY(l2.created)) * 86400) < 60 * 60 * 2
order by l1.created desc
limit 100'''))
	for mod1, action1, mod2, action2, fullname, permalink in result:
		if not subreddit.recent_overlaps.contains(fullname):
			action_name1 = "approved" if 'approve' in action1 else "removed"
			action_name2 = "approved" if 'approve' in action2 else "removed"
			item_type = "post" if 't3_' in fullname else "comment"

			subreddit.recent_overlaps.put(fullname)
			blame_string = f"{subreddit.get_discord_name(mod1)} {action_name1} and then {subreddit.get_discord_name(mod2)} {action_name2} [this {item_type}](<https://www.reddit.com{permalink}>). Make sure the second action is correct"
			log.info(f"Posting: {blame_string}")
			requests.post(subreddit.webhook, data={"content": blame_string})
