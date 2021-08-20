import praw
import discord_logging

log = discord_logging.init_logging()

import database
from database import LogItem

reddit = praw.Reddit("Watchful1")
database.init()

i = 0
try:
	for log_item in reddit.subreddit('bayarea').mod.log(limit=None):
		db_item = LogItem(log_item)
		i += 1
		if i % 1000 == 0:
			log.info(db_item.created)
		database.session.merge(db_item)
except Exception as err:
	log.info(f"hit exception: {err}")

# for log_item in r.subreddit('competitiveoverwatch').mod.log(limit=18, params={'after': "ModAction_3aaa38d4-b710-11ea-a8db-0edd6169107d"}):
# 	db_item = LogItem(log_item)
# 	i += 1
# 	if i % 1000 == 0:
# 		log.info(db_item.created)
# 	session.merge(db_item)
#
# for log_item in r.subreddit('competitiveoverwatch').mod.log(limit=None, params={'after': "ModAction_2f551d3e-b70e-11ea-9ebd-0edc78f729f3"}):
# 	db_item = LogItem(log_item)
# 	i += 1
# 	if i % 1000 == 0:
# 		log.info(db_item.created)
# 	session.merge(db_item)

database.session.commit()
database.engine.dispose()
