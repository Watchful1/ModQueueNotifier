from datetime import datetime
import static
import json
import base64
import zlib
import discord_logging
import re
import requests
import prawcore
import math

log = discord_logging.get_logger()


def process_error(message, exception, traceback):
	is_transient = \
		isinstance(exception, prawcore.exceptions.ServerError) or \
		isinstance(exception, requests.exceptions.Timeout) or \
		isinstance(exception, requests.exceptions.ReadTimeout) or \
		isinstance(exception, requests.exceptions.RequestException)
	log.warning(f"{message}: {type(exception).__name__} : {exception}")
	if is_transient:
		log.info(traceback)
	else:
		log.warning(traceback)

	return is_transient


def parse_modmail_datetime(datetime_string):
	return datetime.strptime(datetime_string, "%Y-%m-%dT%H:%M:%S.%f+00:00")


def conversation_is_unread(conversation):
	return conversation.last_unread is not None and parse_modmail_datetime(conversation.last_unread) > \
				parse_modmail_datetime(conversation.last_updated)


def conversation_not_processed(conversation, processed_modmails, start_time):
	last_replied = parse_modmail_datetime(conversation.last_updated)
	return last_replied > start_time and (conversation.id not in processed_modmails or last_replied > processed_modmails[conversation.id])


def recursive_remove_comments(comment, count_removed=1):
	comment.refresh()
	for child_comment in comment.replies:
		count_removed = recursive_remove_comments(child_comment, count_removed)
		child_comment.mod.remove()
		count_removed += 1
	comment.mod.remove()
	return count_removed


def get_usernotes(sub):
	wiki_page = sub.wiki['usernotes']
	json_data = json.loads(wiki_page.content_md)
	blob = json_data["blob"]
	decoded = base64.b64decode(blob)
	raw = zlib.decompress(decoded)
	parsed = json.loads(raw)
	return json_data, parsed


def save_usernotes(sub, notes_json, notes, user):
	blob = json.dumps(notes).encode()
	compressed_blob = zlib.compress(blob)
	encoded_blob = base64.b64encode(compressed_blob).decode()
	notes_json['blob'] = str(encoded_blob)
	wiki_page = sub.wiki['usernotes']
	wiki_page.edit(json.dumps(notes_json), reason=f"\"create new note on user {user}\" via OWMatchThreads")


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

	groups = re.search(r'(?:comments/)(\w{3,8})(?:/.+/)(\w{3,8})', permalink, flags=re.IGNORECASE)
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
	if user.name in notes:
		notes[user.name]['ns'].insert(0, note)
	else:
		notes[user.name] = {'ns': [note]}

	save_usernotes(sub, notes_json, notes, user)


def warn_ban_user(user, mod_name, subreddit, days_ban, permalink):
	if days_ban is None:
		log.info(f"Warning u/{user.name}, rule 1 from u/{mod_name}")
		user.message("Rule 1 warning", f"No poor or abusive behavior\n\nhttps://www.reddit.com{permalink}\n\nFrom u/{mod_name}", from_subreddit=subreddit.name)
		add_usernote(subreddit.sub_object, user, mod_name, "abusewarn", "abusive comment", permalink)
	else:
		log.info(f"Banning u/{user.name} for {days_ban} days, rule 1 from u/{mod_name}")
		subreddit.banned.add(user, duration=days_ban, ban_reason=f"abusive commment u/{mod_name}", ban_message=f"No poor or abusive behavior\n\nhttps://www.reddit.com{permalink}\n\nFrom u/{mod_name}")
		add_usernote(subreddit.sub_object, user, mod_name, "ban", f"{days_ban}d - abusive comment", permalink)
