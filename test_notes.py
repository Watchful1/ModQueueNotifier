import praw
import discord_logging

discord_logging.init_logging()

import utils

reddit = praw.Reddit("Watchful1")
sub = reddit.subreddit("CompetitiveOverwatch")

notes_json, notes = utils.get_usernotes(sub)
print(f"{notes['Watchful1BotTest']}")

utils.add_usernote(sub, reddit.redditor("Watchful1BotTest"), "Watchful1", "abusewarn", "test 3", "/r/Competitiveoverwatch/comments/ihdvix/test_post_please_ignore/g2zjjdo/")

notes_json, notes = utils.get_usernotes(sub)
print(f"{notes['Watchful1BotTest']}")
