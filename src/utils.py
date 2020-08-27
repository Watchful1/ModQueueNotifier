from datetime import datetime
import static
import json
import base64
import zlib
import discord_logging
import re

log = discord_logging.get_logger()


def check_threshold(bldr, level, key, string):
	if level >= static.THRESHOLDS[key]['post']:
		bldr.append(string)
	if level >= static.THRESHOLDS[key]['ping']:
		return True
	return False


def parse_modmail_datetime(datetime_string):
	return datetime.strptime(datetime_string, "%Y-%m-%dT%H:%M:%S.%f+00:00")


def conversation_is_unread(conversation):
	return conversation.last_unread is not None and parse_modmail_datetime(conversation.last_unread) > \
				parse_modmail_datetime(conversation.last_updated)


def conversation_not_processed(conversation, processed_modmails, start_time):
	last_replied = parse_modmail_datetime(conversation.last_updated)
	return last_replied > start_time and (conversation.id not in processed_modmails or last_replied > processed_modmails[conversation.id])


def get_usernotes(sub):
	wikipage = sub.wiki['usernotes']
	json_data = json.loads(wikipage.content_md)
	blob = json_data["blob"]
	decoded = base64.b64decode(blob)
	raw = zlib.decompress(decoded)
	parsed = json.loads(raw)
	return json_data, parsed


def add_usernote(sub, user, mod_name, type, note_text, permalink):
	notes_json, notes = get_usernotes(sub)

	warning_index = None
	for index, warning in enumerate(notes_json["constants"]["warnings"]):
		if warning == type:
			warning_index = index
			break
	if warning_index is None:
		log.warning(f"Unable to find usernote index for type: {type}")
		return
	mod_index = None
	for index, mod in enumerate(notes_json["constants"]["users"]):
		if mod == mod_name:
			mod_index = index
			break
	if mod_index is None:
		log.warning(f"Unable to find mod index for: {mod_name}")
		return

	groups = re.search(r'(?:comments/)(\w{3,8})(?:/_/)(\w{3,8})', permalink, flags=re.IGNORECASE)
	if not groups:
		log.warning(f"Unable to extract ids from: {permalink}")
		return
	else:
		link_id = groups.group(1)
		comment_id = groups.group(2)
		link = f"l,{link_id},{comment_id}"

	note = {
		'n': note_text,
		't': int(datetime.utcnow().timestamp()),
		'm': mod_index,
		'l': link,
		'w': warning_index
	}
	if user.name in notes_json:
		notes_json[user.name]['ns'].append(note)
	else:
		notes_json[user.name] = {'ns': [note]}


def warn_ban_user(user, mod_name, subreddit, days_ban, permalink):
	if days_ban is None:
		user.message("Rule 1 warning", f"No poor or abusive behavior\n\nhttps://www.reddit.com{permalink}", from_subreddit=subreddit.display_name)
		add_usernote(subreddit, user, mod_name, "abusewarn", "abusive comment", permalink)
	else:
		subreddit.banned.add(user, ban_reason="abusive commment", ban_message=f"No poor or abusive behavior\n\nhttps://www.reddit.com{permalink}")
		add_usernote(subreddit, user, mod_name, "ban", f"{days_ban}d - abusive comment", permalink)


class Queue:
	def __init__(self, max_size):
		self.list = []
		self.max_size = max_size
		self.set = set()

	def put(self, item):
		if len(self.list) >= self.max_size:
			self.list.pop(0)
		self.list.append(item)
		self.set.add(item)

	def contains(self, item):
		return item in self.set
