import praw
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.orm import sessionmaker
import discord_logging
from datetime import datetime

log = discord_logging.init_logging()
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


engine = create_engine(f'sqlite:///database.db')
Session = sessionmaker(bind=engine)
session = Session()
Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
session.commit()

r = praw.Reddit("Watchful1")

i = 0
try:
	for log_item in r.subreddit('competitiveoverwatch').mod.log(limit=None):
		db_item = LogItem(log_item)
		i += 1
		if i % 1000 == 0:
			log.info(db_item.created)
		session.merge(db_item)
except Exception:
	log.info("hit exception")

for log_item in r.subreddit('competitiveoverwatch').mod.log(limit=18, params={'after': "ModAction_3aaa38d4-b710-11ea-a8db-0edd6169107d"}):
	db_item = LogItem(log_item)
	i += 1
	if i % 1000 == 0:
		log.info(db_item.created)
	session.merge(db_item)

for log_item in r.subreddit('competitiveoverwatch').mod.log(limit=None, params={'after': "ModAction_2f551d3e-b70e-11ea-9ebd-0edc78f729f3"}):
	db_item = LogItem(log_item)
	i += 1
	if i % 1000 == 0:
		log.info(db_item.created)
	session.merge(db_item)

session.commit()
engine.dispose()
