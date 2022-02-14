import praw

if __name__ == "__main__":
	reddit = praw.Reddit("Watchful1")

	for queue_item in reddit.subreddit("bayarea").mod.modqueue():
		print(f"https://www.reddit.com{queue_item.permalink}")
