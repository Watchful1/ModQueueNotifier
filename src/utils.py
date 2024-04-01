from datetime import datetime

import praw

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
	try:
		return datetime.strptime(datetime_string, "%Y-%m-%dT%H:%M:%S.%f+00:00")
	except ValueError:
		return datetime.strptime(datetime_string, "%Y-%m-%dT%H:%M:%S.%f+0000")


def conversation_is_unread(conversation):
	return conversation.last_unread is not None and parse_modmail_datetime(conversation.last_unread) > \
				parse_modmail_datetime(conversation.last_updated)


def conversation_not_processed(conversation, processed_modmails, start_time):
	last_replied = parse_modmail_datetime(conversation.last_updated)
	return last_replied > start_time and (conversation.id not in processed_modmails or last_replied > processed_modmails[conversation.id])


def recursive_remove_comments(comment, count_removed=1):
	log.debug(f"Recursive removing {comment.id}")
	comment.refresh()
	for child_comment in comment.replies:
		count_removed = recursive_remove_comments(child_comment, count_removed)
	if not comment.removed:
		comment.mod.remove()
		count_removed += 1
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


def add_usernote(subreddit, username, mod_name, type, note_text, permalink):
	sub_notes = get_usernotes(subreddit)
	user_note = sub_notes.get_user_note(username)
	note = Note.build_note(sub_notes, mod_name, type, note_text, datetime.utcnow(), permalink)

	if user_note is not None:
		user_note.add_new_note(note)
	else:
		user_note = UserNotes(username)
		user_note.add_new_note(note)
		sub_notes.add_update_user_note(user_note)
	save_usernotes(subreddit, sub_notes, f"\"create new note on user {username}\" via {subreddit.get_account_name()}")


def warn_archive(author_obj, subreddit, subject, message):
	try:
		author_obj.message(
			subject,
			message,
			from_subreddit=subreddit.name)
	except praw.exceptions.RedditAPIException:
		log.warning(f"Error sending warning message to u/{author_obj.name}")
	found = False
	for conversation in list(subreddit.all_modmail()):
		#log.warning(f"{conversation.id} : {len(conversation.authors)} authors : u/{conversation.authors[0].name} : {len(conversation.messages)} messages")
		if len(conversation.authors) == 2 and \
				conversation.authors[0].name in {subreddit.get_account_name(), author_obj.name} and \
				conversation.authors[1].name in {subreddit.get_account_name(), author_obj.name} and \
				len(conversation.messages) == 1:
			log.info(f"Archiving {conversation.authors[0].name} message: {conversation.id}")
			conversation.archive()
			subreddit.all_modmail().remove(conversation)
			found = True
			break
	if not found:
		log.warning(f"Couldn't find modmail to archive")
