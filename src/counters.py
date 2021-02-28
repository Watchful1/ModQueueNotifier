import prometheus_client

mod_actions = prometheus_client.Counter("bot_mod_actions", "Mod actions by moderator", ['moderator', 'subreddit'])
queue_size = prometheus_client.Gauge("bot_queue_size", "Queue size", ['type', 'subreddit'])


def init(port):
	prometheus_client.start_http_server(port)
