import discord_logging
import re
import requests
from datetime import datetime

log = discord_logging.get_logger()


def process_submissions(subreddit):
	for submission in subreddit.sub_object.new(limit=25):
		processed = False
		if datetime.utcfromtimestamp(submission.created_utc) <= subreddit.post_checked:
			subreddit.post_checked = datetime.utcnow()
			processed = True

		if not processed:
			if submission.author.name == "AutoModerator" and "Weekly Short Questions Megathread" in submission.title:
				log.info(f"Found new short questions thread, updating sidebar: {submission.id}")
				submission.mod.approve()
				wiki_page = subreddit.sub_object.wiki['config/sidebar']
				edited_sidebar = re.sub(
					r'(\[Short Questions Megathread\]\(https://redd.it/)(\w{4,10})',
					f"\\g<1>{submission.id}",
					wiki_page.content_md
				)
				wiki_page.edit(edited_sidebar)

			if submission.discussion_type == 'CHAT' and submission.author.name not in ("Watchful1", "OWMatchThreads"):
				log.info(f"Removing live chat post: {submission.id} by u/{submission.author.name}")
				comment = submission.reply("Don't post live chat threads")
				comment.mod.distinguish(how="yes", sticky=True)
				submission.mod.remove()
				submission.mod.lock()

		if submission.approved and submission.link_flair_text is None and not subreddit.posts_notified.contains(submission.id):
			blame_string = f"{subreddit.get_discord_name(submission.approved_by)} approved without adding a flair: <https://www.reddit.com{submission.permalink}>"
			log.info(f"Posting: {blame_string}")
			subreddit.posts_notified.put(submission.id)
			requests.post(subreddit.webhook, data={"content": blame_string})


def parse_modmail(subreddit):
	for conversation in list(subreddit.all_modmail()):
		archive = None
		if len(conversation.authors) == 1 and \
				conversation.authors[0].name in {"AutoModerator"} and \
				len(conversation.messages) == 1:
			links = re.findall(r'(?:reddit.com/r/\w*/comments/)(\w*)', conversation.messages[0].body_markdown)
			if len(links) == 1:
				submission = subreddit.reddit.submission(links[0])
				if submission.selftext == "[deleted]" or submission.author == "[deleted]":
					archive = "Deleted by user"
				elif submission.locked or submission.removed:
					if len(submission.comments) and submission.comments[0].stickied:
						archive = f"Removed by u/{submission.comments[0].author.name}"
				elif submission.approved:
					archive = f"Approved by u/{submission.approved_by}"

			if archive is not None:
				log.info(f"Archiving automod notification: {conversation.id}")
				conversation.reply(archive, internal=True)
				conversation.archive()
				subreddit.all_modmail().remove(conversation)
