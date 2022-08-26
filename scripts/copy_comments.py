import discord_logging

log = discord_logging.init_logging()

from database import Comment, User, Submission, Database

if __name__ == "__main__":
	database_new = Database("database.db")
	database_prod = Database("database_prod.db")

	comments = database_new.session.query(Comment).all()
	count = 0
	total_comments = len(comments)
	new_submissions = 0
	new_users = 0
	log.info(f"{count}/{total_comments}: {new_submissions}|{new_users}")

	for comment in comments:
		db_submission = database_prod.session.query(Submission).filter_by(submission_id=comment.submission_id).first()
		if db_submission is None:
			new_submissions += 1
			db_submission = Submission(
				submission_id=comment.submission_id,
				created=comment.created,
				is_restricted=False
			)
			database_prod.session.add(db_submission)

		comment_author_name = comment.author.name
		db_user = database_prod.session.query(User).filter_by(name=comment_author_name).first()
		if db_user is None:
			new_users += 1
			db_user = database_prod.session.merge(User(name=comment_author_name))
		database_prod.session.merge(Comment(
			comment_id=comment.comment_id,
			author=db_user,
			submission=db_submission,
			created=comment.created,
			subreddit_id=3,
			karma=comment.karma,
			is_removed=comment.is_removed,
			is_deleted=comment.is_deleted
		))
		count += 1
		if count % 1000 == 0:
			log.info(f"{count}/{total_comments}: {new_submissions}|{new_users}")
			database_prod.session.commit()

	log.info(f"{count}/{total_comments}: {new_submissions}|{new_users}")
	database_prod.close()
	database_new.close()
