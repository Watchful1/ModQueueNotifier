from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine, Column, String, DateTime, Integer, ForeignKey, Boolean
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
from shutil import copyfile


Base = declarative_base()
engine = None
session = None
backup_folder = "backup"
database_name = "database.db"


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

	def __init__(
		self,
		submission_id,
		created,
		is_restricted
	):
		self.submission_id = submission_id
		self.created = created
		self.is_restricted = is_restricted

	def __str__(self):
		return self.submission_id


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

	author = relationship("User", lazy="joined")
	submission = relationship("Submission", lazy="joined")

	def __init__(
		self,
		comment_id,
		author,
		submission,
		created
	):
		self.comment_id = comment_id
		self.author = author
		self.submission = submission
		self.created = created
		self.karma = None
		self.is_removed = False
		self.is_deleted = False

	def __str__(self):
		return self.comment_id


def init():
	global engine
	global session
	engine = create_engine(f'sqlite:///{database_name}')
	session_maker = sessionmaker(bind=engine)
	session = session_maker()
	Base.metadata.create_all(engine)
	session.commit()


def backup():
	global engine
	global session
	session.commit()
	engine.dispose()

	if not os.path.exists(backup_folder):
		os.makedirs(backup_folder)

	copyfile(
		database_name,
		backup_folder + "/" +
			datetime.utcnow().strftime("%Y-%m-%d_%H-%M") +
			".db"
	)

	init()
