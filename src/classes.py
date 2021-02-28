from datetime import datetime
import discord_logging

log = discord_logging.get_logger()


class Subreddit:
	def __init__(
			self,
			name,
			reddit,
			moderators,
			warning_log_types=None,
			report_reasons=None,
			reapprove_reasons=None,
			thresholds=None,
			webhook=None
	):
		self.name = name
		self.reddit = reddit
		self.moderators = moderators

		self.warning_log_types = warning_log_types
		self.report_reasons = report_reasons
		self.reapprove_reasons = reapprove_reasons
		self.thresholds = thresholds
		self.webhook = webhook

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
