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

from classes import SubredditNotes, UserNotes, Note


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


def get_usernotes(subreddit):
	json_text = subreddit.sub_object.wiki['usernotes'].content_md
	return SubredditNotes.from_dict(subreddit.name, json_text)


def save_usernotes(subreddit, sub_notes, change_reason):
	json_dict = sub_notes.to_dict()
	try:
		subreddit.sub_object.wiki['usernotes'].edit(json.dumps(json_dict), reason=change_reason)
	except prawcore.exceptions.SpecialError:
		log.warning(f"Failed to save usernotes for r/{subreddit.name}, SpecialError")
		if subreddit.backup_reddit is not None:
			try:
				subreddit.backup_reddit.subreddit(subreddit.name).wiki['usernotes'].edit(json.dumps(json_dict), reason=change_reason)
				log.warning(f"Saved usernotes for r/{subreddit.name} with backup reddit")
			except prawcore.exceptions.SpecialError:
				log.warning(f"Failed to save usernotes for r/{subreddit.name} with backup reddit, SpecialError")


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
