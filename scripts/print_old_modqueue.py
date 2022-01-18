import praw

if __name__ == "__main__":
	reddit = praw.Reddit("OWMatchThreads")

	for queue_item in reddit.subreddit("CompetitiveOverwatch").mod.modqueue():
		print(f"https://www.reddit.com/{queue_item.permalink}")
