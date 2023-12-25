import prometheus_client

mod_actions = prometheus_client.Counter("bot_mod_actions", "Mod actions by moderator", ['moderator', 'subreddit'])
queue_size = prometheus_client.Gauge("bot_queue_size", "Queue size", ['type', 'subreddit'])
loop_time = prometheus_client.Summary('bot_loop_time', "How long it took for one loop")
user_comments = prometheus_client.Counter("bot_user_comments", "Comments in subreddit", ['subreddit', 'result'])
backfill = prometheus_client.Counter("bot_backfill", "Backfill results", ['subreddit', 'type', 'result'])
objects = prometheus_client.Gauge('bot_objects', "Total number of objects by type", ['type', 'subreddit'])


def init(port):
	prometheus_client.start_http_server(port)
