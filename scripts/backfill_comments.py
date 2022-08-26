import discord_logging
import requests
import time
import json
import praw
import sys
from datetime import datetime, timezone, timedelta

log = discord_logging.init_logging()

from database import Comment, User, Submission, Database


database = Database()
url = "https://api.pushshift.io/reddit/comment/search?limit=1000&sort=desc&subreddit=Marriage&before="
start_time = datetime.utcnow() #  datetime.strptime("21-11-19 15:34:07", '%y-%m-%d %H:%M:%S')
end_time = datetime.strptime("22-08-20 01:43:35", '%y-%m-%d %H:%M:%S')  # start_time - timedelta(days=300)

count = 0
previous_epoch = int(start_time.replace(tzinfo=timezone.utc).timestamp()) - 1
while True:
	new_url = url + str(previous_epoch)
	json_text = requests.get(new_url, headers={'User-Agent': "Post downloader by /u/Watchful1"})
	time.sleep(1)  # pushshift has a rate limit, if we send requests too fast it will start returning error messages
	try:
		json_data = json_text.json()
	except json.decoder.JSONDecodeError:
		time.sleep(1)
		continue

	if 'data' not in json_data:
		break
	objects = json_data['data']
	if len(objects) == 0:
		break

	for comment in objects:
		previous_epoch = comment['created_utc'] - 1
		count += 1

		submission_id = comment['link_id'][3:]
		comment_created = datetime.utcfromtimestamp(comment['created_utc'])

		if comment_created <= end_time:
			log.info(f"{count} : {(comment_created.strftime('%Y-%m-%d'))}")
			database.session.commit()
			database.engine.dispose()
			sys.exit()

		db_submission = database.session.query(Submission).filter_by(submission_id=submission_id).first()
		if db_submission is None:
			db_submission = Submission(
				submission_id=submission_id,
				created=comment_created,
				is_restricted=False
			)
			database.session.add(db_submission)

		db_user = database.session.query(User).filter_by(name=comment['author']).first()
		if db_user is None:
			db_user = database.session.merge(User(name=comment['author']))

		db_comment = database.session.merge(Comment(
			comment_id=comment['id'],
			author=db_user,
			submission=db_submission,
			created=comment_created,
			subreddit_id=3
		))

		if count % 1000 == 0:
			log.info(f"{count} : {(comment_created.strftime('%Y-%m-%d'))}")
			database.session.commit()

database.engine.dispose()
