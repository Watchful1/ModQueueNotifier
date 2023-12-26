from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine, Column, String, DateTime, Integer, ForeignKey, Boolean
from sqlalchemy.orm import sessionmaker, relationship, aliased
from sqlalchemy.sql import func
from datetime import datetime, timedelta
import os
import time
from shutil import copyfile
import discord_logging

log = discord_logging.get_logger()

import counters


Base = declarative_base()


class LogItem(Base):
	__tablename__ = 'log'

	id = Column(String(60), primary_key=True)
	created = Column(DateTime, nullable=False)
	mod = Column(String(60), nullable=False)
	action = Column(String(80), nullable=False)
	details = Column(String(80))
	target_author = Column(String(80))
	target_fullname = Column(String(20))
	target_permalink = Column(String(160))
	target_title = Column(String(300))
	target_body = Column(String(300))
	description = Column(String(300))
	subreddit = Column(String(60))

	def __init__(self, log_item):
		self.id = log_item.id
		self.created = datetime.utcfromtimestamp(log_item.created_utc)
		self.mod = log_item.mod.name
		self.action = log_item.action
		self.details = log_item.details
		self.target_author = log_item.target_author if log_item.target_author else None
		self.target_fullname = log_item.target_fullname
		self.target_permalink = log_item.target_permalink
		self.target_title = log_item.target_title
		self.target_body = log_item.target_body
		self.description = log_item.description
		self.subreddit = log_item.subreddit


class User(Base):
	__tablename__ = 'users'

	id = Column(Integer, primary_key=True)
	name = Column(String(80, collation="NOCASE"), nullable=False, unique=True)
	is_deleted = Column(Boolean, nullable=False)

	def __init__(
		self,
		name,
		is_deleted=False
	):
		self.name = name
		self.is_deleted = is_deleted

	def __str__(self):
		return f"u/{self.name}"


class Submission(Base):
	__tablename__ = 'submissions'

	id = Column(Integer, primary_key=True)
	submission_id = Column(String(12), nullable=False, unique=True)
	is_restricted = Column(Boolean, nullable=False)
	created = Column(DateTime, nullable=False)
	is_notified = Column(Boolean, nullable=False, default=False)
	author_id = Column(Integer, ForeignKey('users.id'), nullable=False)
	karma = Column(Integer)
	is_removed = Column(Boolean, nullable=False)
	is_deleted = Column(Boolean, nullable=False)
	subreddit_id = Column(Integer, nullable=False)

	author = relationship("User", lazy="joined")

	def __init__(
		self,
		submission_id,
		created,
		is_restricted,
		author,
		subreddit_id,
		karma=None,
		is_removed=False,
		is_deleted=False
	):
		self.submission_id = submission_id
		self.author = author
		self.created = created
		self.is_restricted = is_restricted
		self.is_notified = False
		self.subreddit_id = subreddit_id
		self.karma = karma
		self.is_removed = is_removed
		self.is_deleted = is_deleted

	def __str__(self):
		return self.submission_id

	def fullname(self):
		return f"t3_{self.submission_id}"


class Comment(Base):
	__tablename__ = 'comments'

	id = Column(Integer, primary_key=True)
	comment_id = Column(String(12), nullable=False, unique=True)
	author_id = Column(Integer, ForeignKey('users.id'), nullable=False)
	submission_id = Column(String(12), ForeignKey('submissions.id'), nullable=False)
	created = Column(DateTime, nullable=False)
	karma = Column(Integer)
	is_removed = Column(Boolean, nullable=False)
	is_deleted = Column(Boolean, nullable=False)
	is_author_restricted = Column(Boolean, nullable=False)
	subreddit_id = Column(Integer, nullable=False)

	author = relationship("User", lazy="joined")
	submission = relationship("Submission", lazy="joined")

	def __init__(
		self,
		comment_id,
		author,
		submission,
		created,
		subreddit_id,
		karma=None,
		is_removed=False,
		is_deleted=False,
		is_author_restricted=False
	):
		self.comment_id = comment_id
		self.author = author
		self.submission = submission
		self.created = created
		self.subreddit_id = subreddit_id
		self.karma = karma
		self.is_removed = is_removed
		self.is_deleted = is_deleted
		self.is_author_restricted = is_author_restricted

	def __str__(self):
		return self.comment_id

	def fullname(self):
		return f"t1_{self.comment_id}"


class Database:
	def __init__(self, location="database.db"):
		self.engine = None
		self.session = None
		self.location = location
		self.init(self.location)

	def init(self, location):
		self.engine = create_engine(f'sqlite:///{location}')
		session_maker = sessionmaker(bind=self.engine)
		self.session = session_maker()
		Base.metadata.create_all(self.engine)
		self.session.commit()

	def close(self):
		self.session.commit()
		self.engine.dispose()

	def backup(self, backup_folder="backup"):
		self.close()

		if not os.path.exists(backup_folder):
			os.makedirs(backup_folder)

		copyfile(
			self.location,
			backup_folder + "/" +
				datetime.utcnow().strftime("%Y-%m-%d_%H-%M") +
				".db"
		)

		self.init(self.location)

	def update_object_counts(self):
		for subreddit, subreddit_id in (("competitiveoverwatch", 1), ("bayarea", 2)):
			counters.objects.labels(type="log_item", subreddit=subreddit).set(self.session.query(LogItem).filter(subreddit_id == subreddit_id).count())
		counters.objects.labels(type="submission", subreddit="bayarea").set(self.session.query(Submission).filter(subreddit_id == 2).count())
		counters.objects.labels(type="comment", subreddit="bayarea").set(self.session.query(Comment).filter(subreddit_id == 2).count())
		counters.objects.labels(type="user", subreddit="bayarea").set(self.session.query(User).count())

	def cleanup(self):
		count_submissions_0_2 = 0
		count_submissions_2_3 = 0
		for submission in self.session.query(Submission).join(Comment).filter(Submission.subreddit_id == 0).filter(Comment.subreddit_id == 2).limit(1000).all():
			submission.subreddit_id = 2
			count_submissions_0_2 += 1
		for submission in self.session.query(Submission).join(Comment).filter(Submission.subreddit_id == 2).filter(Comment.subreddit_id == 3).limit(1000).all():
			submission.subreddit_id = 3
			count_submissions_2_3 += 1
		log.info(f"Updated subreddit ids : {count_submissions_0_2} : {count_submissions_2_3}")

	def purge(self):
		start_time = time.perf_counter()
		deleted_comment_ids = []
		before_date = datetime.utcnow() - timedelta(days=365)
		for comment in self.session.query(Comment).filter(Comment.created < before_date).limit(1000).all():
			deleted_comment_ids.append(comment.comment_id)
			self.session.delete(comment)
		if not len(deleted_comment_ids):
			deleted_comment_ids.append("none")

		deleted_submission_ids = []
		# comment1 = aliased(Comment)
		# subquery = (self.session.query(comment1, func.count('*').label("count"))
		# 	.group_by(comment1.submission_id)
		# 	.subquery())
		# for submission in self.session.query(Submission)\
		# 		.join(subquery, Submission.id == subquery.c.submission_id, isouter=True)\
		# 		.filter(subquery.c.count == None).filter(Submission.created < before_date).limit(1000).all():
		# 	deleted_submission_ids.append(submission.submission_id)
		# 	#self.session.delete(submission)
		if not len(deleted_submission_ids):
			deleted_submission_ids.append("none")

		deleted_users = []
		for user in self.session.query(User)\
				.join(Comment, User.id == Comment.author_id, isouter=True)\
				.join(Submission, User.id == Submission.author_id, isouter=True)\
				.filter(Comment.id == None).filter(Submission.id == None).limit(1000).all():
			deleted_users.append(f"{user.name}:{user.id}")
			self.session.delete(user)
		if not len(deleted_users):
			deleted_users.append("none")

		delta_time = time.perf_counter() - start_time
		log.info(
			f"Cleanup {' '.join(deleted_comment_ids)} : {' '.join(deleted_submission_ids)} : {' '.join(deleted_users)} in "
			f"{delta_time:.2f} seconds")
