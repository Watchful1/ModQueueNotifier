import praw
import discord_logging
import re
from datetime import datetime

log = discord_logging.init_logging()

import utils

reddit = praw.Reddit("Watchful1")
sub = reddit.subreddit("CompetitiveOverwatch")

notes_json, notes = utils.get_usernotes(sub)
warnings = notes_json['constants']['warnings']
count_no_match = 0
count_match = 0
for username, note in notes.items():
	for note_item in note['ns']:
		warning_type = warnings[note_item['w']]
		if warning_type == 'ban':
			match = re.search(r'^\d+', note_item['n'])
			if match:
				count_match += 1
				# log.info(f"match: {int(match.group(0))} : {note_item['n']}")
			else:
				count_no_match += 1
				log.info(f"no match: {note_item['n']} : {notes_json['constants']['users'][note_item['m']]} : {datetime.utcfromtimestamp(note_item['t']).strftime('%Y-%m-%d %H:%M:%S %Z')}")

log.info(f"No match: {count_no_match}, match: {count_match}")

# utils.add_usernote(sub, reddit.redditor("Watchful1BotTest"), "Watchful1", "abusewarn", "test 3", "/r/Competitiveoverwatch/comments/ihdvix/test_post_please_ignore/g2zjjdo/")
# notes_json, notes = utils.get_usernotes(sub)
# print(f"{notes['Watchful1BotTest']}")
