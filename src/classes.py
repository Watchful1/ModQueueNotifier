from datetime import datetime, timedelta
import discord_logging
import json
import base64
import zlib
import re

log = discord_logging.get_logger()


class Subreddit:
	def __init__(
			self,
			name,
			reddit,
			moderators,
			known_log_types=None,
			warning_log_types=None,
			report_reasons=None,
			comment_report_reasons=None,
			reapprove_reasons=None,
			thresholds=None,
			webhook=None,
			restricted=None,
			backup_reddit=None,
			name_in_modmails=True
	):
		self.name = name
		self.reddit = reddit
		self.backup_reddit = backup_reddit
		self.moderators = moderators

		self.known_log_types = known_log_types
		self.warning_log_types = warning_log_types
		self.report_reasons = report_reasons
		self.comment_report_reasons = comment_report_reasons
		self.reapprove_reasons = reapprove_reasons
		self.thresholds = thresholds
		self.webhook = webhook
		self.restricted = restricted
		self.name_in_modmails = name_in_modmails

		self.sub_object = reddit.subreddit(self.name)
		self.post_checked = datetime.utcnow()
		self.posts_notified = Queue(50)
		self.processed_modmails = {}
		self.last_posted = None
		self.has_posted = False

		self.mail_count = 0
		self.unmod_count = 0
		self.reported_count = 0
		self.oldest_modmail_hours = None
		self.oldest_unmod_hours = None

		self._modqueue = None
		self._all_modmail = None
		self._archived_modmail = None
		self._appeal_modmail = None
		self.mod_log = []

		self.ban_tiers = [
			0,
			3,
			7,
			14
		]

	def get_next_ban_tier(self, current_days, get_current_tier):
		prev_tier = self.ban_tiers[0]
		if current_days is None:
			return prev_tier
		else:
			for tier_days in self.ban_tiers:
				if current_days < tier_days:
					if get_current_tier:
						return prev_tier
					else:
						return tier_days
				prev_tier = tier_days

		if get_current_tier:
			return prev_tier
		else:
			return -1

	def check_threshold(self, bldr, level, key, string):
		if level >= self.thresholds[key]['post']:
			bldr.append(f"{string}: {level}")
		if level >= self.thresholds[key]['ping']:
			return True
		return False

	def ping_string(self):
		if self.thresholds is None:
			return None
		results = []
		ping_here = False
		ping_here = self.check_threshold(results, self.unmod_count, 'unmod', "Unmod") or ping_here
		ping_here = self.check_threshold(results, self.oldest_unmod_hours, 'unmod_hours', "Oldest unmod in hours") or ping_here
		ping_here = self.check_threshold(results, self.reported_count, 'modqueue', "Modqueue") or ping_here
		ping_here = self.check_threshold(results, self.mail_count, 'modmail', "Modmail") or ping_here
		ping_here = self.check_threshold(results, self.oldest_modmail_hours, 'modmail_hours', "Oldest modmail in hours") or ping_here
		if len(results):
			count_string = ', '.join(results)
			if ping_here:
				count_string = "@here " + count_string
			return count_string
		return None

	def modqueue(self):
		if self._modqueue is None:
			self._modqueue = list(self.sub_object.mod.modqueue())
		return self._modqueue

	def all_modmail(self):
		if self._all_modmail is None:
			self._all_modmail = list(self.sub_object.modmail.conversations(state='all'))
		return self._all_modmail

	def archived_modmail(self):
		if self._archived_modmail is None:
			self._archived_modmail = list(self.sub_object.modmail.conversations(state='archived', limit=10))
		return self._archived_modmail

	def appeal_modmail(self):
		if self._appeal_modmail is None:
			self._appeal_modmail = list(self.sub_object.modmail.conversations(state='appeals'))
		return self._appeal_modmail

	def combined_modmail(self):
		combined_modmail = list(self.all_modmail())
		combined_modmail.extend(list(self.appeal_modmail()))
		return combined_modmail

	def clear_cache(self):
		self._modqueue = None
		self._all_modmail = None
		self._archived_modmail = None
		self._appeal_modmail = None
		self.mail_count = 0
		self.unmod_count = 0
		self.reported_count = 0
		self.oldest_modmail_hours = None
		self.oldest_unmod_hours = None

	def flair_restricted(self, flair):
		if self.restricted['flairs'] is None:
			return False
		return flair in self.restricted['flairs']


class SubredditNotes:
	def __init__(self, subreddit_name, version, users, warnings, all_notes=None):
		self.subreddit_name = subreddit_name
		self.version = version

		self.order_to_user = {}
		self.user_to_order = {}
		for index, user in enumerate(users):
			self.order_to_user[index] = user
			self.user_to_order[user] = index

		self.order_to_warning = {}
		self.warning_to_order = {}
		for index, warning in enumerate(warnings):
			self.order_to_warning[index] = warning
			self.warning_to_order[warning] = index

		if all_notes is not None:
			self.all_notes = all_notes
		else:
			self.all_notes = {}

	def to_dict(self):
		notes_dict = {}
		total_notes = 0
		for username, user_note in self.all_notes.items():
			total_notes += len(user_note.notes)
			notes_dict[username] = user_note.to_dict()

		blob = json.dumps(notes_dict).encode()
		compressed_blob = zlib.compress(blob)
		encoded_blob = base64.b64encode(compressed_blob).decode()

		users_list = []
		for index in range(len(self.order_to_user)):
			users_list.append(self.order_to_user[index])
		warnings_list = []
		for index in range(len(self.order_to_warning)):
			warnings_list.append(self.order_to_warning[index])

		log.info(f"Exported notes for r/{self.subreddit_name}: {len(notes_dict)} : {total_notes}")
		return {
			'ver': 6,
			'constants': {
				'users': users_list,
				'warnings': warnings_list
			},
			'blob': str(encoded_blob)
		}

	def add_update_user_note(self, user_note):
		self.all_notes[user_note.username] = user_note

	def get_user_note(self, username):
		if username in self.all_notes:
			return self.all_notes[username]
		else:
			return None

	@staticmethod
	def from_dict(subreddit_name, json_text):
		json_data = json.loads(json_text)

		sub_notes = SubredditNotes(
			subreddit_name,
			json_data['ver'],
			json_data['constants']['users'],
			json_data['constants']['warnings'],
		)

		blob = json_data["blob"]
		decoded = base64.b64decode(blob)
		raw = zlib.decompress(decoded)
		parsed = json.loads(raw)

		total_notes = 0
		for username, notes_dict in parsed.items():
			user_notes = UserNotes(username)
			for note_dict in notes_dict['ns']:
				total_notes += 1
				user_notes.notes.append(Note(
					sub_notes,
					note_dict['m'],
					note_dict['w'],
					note_dict['n'],
					note_dict['t'],
					note_dict['l']
				))
			sub_notes.add_update_user_note(user_notes)

		log.info(f"Loaded notes for r/{subreddit_name}: {len(sub_notes.all_notes)} : {total_notes}")
		return sub_notes


class UserNotes:
	def __init__(self, username, notes=None):
		self.username = username
		if notes is not None:
			self.notes = notes
		else:
			self.notes = []

	def add_new_note(self, note):
		log.info(f"Added new note to u/{self.username} : {str(note.to_dict())}")
		self.notes.insert(0, note)

	def __str__(self):
		bldr = [f"u/{self.username}, {str(len(self.notes))}:"]
		for note in self.notes:
			bldr.append("\n")
			bldr.append(str(note))
		return ''.join(bldr)

	def to_dict(self):
		notes = []
		for note in self.notes:
			notes.append(note.to_dict())
		return {'ns': notes}

	def get_recent_warn_ban(self):
		for note in self.notes:
			note_type = note.get_type()
			note_is_old = note.get_datetime() < datetime.utcnow() - timedelta(days=182)  # roughly half a year
			if note_type == 'ban':
				match = re.search(r'^\d+', note.get_text())
				if match:
					return int(match.group(0)), note_is_old
				else:
					log.warning(f"u/{self.username} has a ban, but can't get length from: {note.get_text()}")
			elif note_type == 'abusewarn':
				return 0, note_is_old
			elif note_type == 'permban':
				return -1, note_is_old
		return None, False


class Note:
	def __init__(self, sub_notes, mod_id, warning_id, note_text, note_timestamp, short_link):
		self._sub_notes = sub_notes

		self._mod_id = mod_id
		self._warning_id = warning_id
		self._note_text = note_text
		self._note_timestamp = note_timestamp
		self._short_link = short_link

	def get_mod(self):
		return self._sub_notes.order_to_user[self._mod_id]

	def set_mod(self, mod_name):
		self._mod_id = self._sub_notes.user_to_order[mod_name]

	def get_type(self):
		return self._sub_notes.order_to_warning[self._warning_id]

	def set_type(self, type_name):
		self._warning_id = self._sub_notes.user_to_warning[type_name]

	def get_text(self):
		return self._note_text

	def set_text(self, text):
		self._note_text = text

	def get_datetime(self):
		return datetime.utcfromtimestamp(self._note_timestamp)

	def set_datetime(self, date_time):
		self._note_timestamp = int(date_time.timestamp())

	def get_link(self):
		return Note.short_to_link(self._short_link)

	def set_link(self, link):
		self._short_link = Note.link_to_short(link)

	def __str__(self):
		return f"{self.get_mod()}:{self.get_type()}:{self.get_datetime().strftime('%Y-%m-%d %H:%M:%S')}: {self.get_text()} : {self.get_link()}"

	def to_dict(self):
		return {
			'n': self._note_text,
			't': self._note_timestamp,
			'm': self._mod_id,
			'l': self._short_link,
			'w': self._warning_id
		}

	@staticmethod
	def build_note(sub_notes, mod_name, note_type, note_text, note_time, permalink):
		return Note(
			sub_notes,
			sub_notes.user_to_order[mod_name],
			sub_notes.warning_to_order[note_type],
			note_text,
			int(note_time.timestamp()),
			Note.link_to_short(permalink)
		)

	@staticmethod
	def short_to_link(short):
		if short.startswith("l,"):
			parts = short.split(",")
			if len(parts) == 3:  # this is a comment link
				return f"https://www.reddit.com/comments/{parts[1]}/_/{parts[2]}"
			elif len(parts) == 2:  # this is a submission link
				return f"https://www.reddit.com/comments/{parts[1]}"
			# otherwise it's neither, just return it
		elif short.startswith("m,"):
			parts = short.split(",")
			if len(parts) == 2:  # this is an old modmail link
				return f"https://www.reddit.com/message/messages/{parts[1]}"
		return short

	@staticmethod
	def link_to_short(link):
		groups = re.search(r'(?:comments/)(\w{3,8})(?:/.+/)(\w{3,8})', link, flags=re.IGNORECASE)
		if groups:
			return f"l,{groups.group(1)},{groups.group(2)}"
		groups = re.search(r'(?:comments/)(\w{3,8})', link, flags=re.IGNORECASE)
		if groups:
			return f"l,{groups.group(1)}"
		groups = re.search(r'(?:message/messages/)(\w{3,8})', link, flags=re.IGNORECASE)
		if groups:
			return f"m,{groups.group(1)}"
		return link


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
