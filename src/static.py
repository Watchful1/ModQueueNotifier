
SUBREDDIT = "CompetitiveOverwatch"
USER_AGENT = "ModQueueNotifier (by /u/Watchful1)"
LOOP_TIME = 1 * 60
REDDIT_OWNER = "Watchful1"
WEBHOOK = "https://discordapp.com/api/webhooks/{}/{}"


THRESHOLDS = {
	'unmod': {'post': 15, 'ping': 20},
	'unmod_hours': {'post': 4, 'ping': 6},
	'modqueue': {'post': 8, 'ping': 12},
	'modmail': {'post': 5, 'ping': 8},
	'modmail_hours': {'post': 12, 'ping': 24},
}

MODERATORS = {
	"merger3": "143730443777343488",
	"DerWaechter_": "193382989718093833",
	"connlocks": "139462031894904832",
	"Sorglos": "166045025153581056",
	"Watchful1": "95296130761371648",
	"blankepitaph": "262708160790396928",
	"Quantum027": "368589871092334612",
	"imKaku": "120207112646164480",
	"Unforgettable_": "177931363180085250",
	"KarmaCollect": "196018859889786880",
	"damnfinecoffee_": "308323435468029954",
	"MagnarHD": "209762662681149440",
	"wotugondo": "385460099138715650",
	"timberflynn": "195955430734823424",
	"Kralz": "172415421561962496",
	"ModWilliam": "321107093773877257",
	"Blaiidds": "204445334255042560",
	"DatGameGuy": "132969627050311680",
	"Dobvius": "171644935446069249",
	"FelipeDoesStats": "277798095906144257",
	"OWMatchThreads": "OWMatchThreads",
	"AutoModerator": "AutoModerator",
}

KNOWN_LOG_TYPES = {
	'spamlink',
	'removelink',
	'approvelink',
	'spamcomment',
	'removecomment',
	'approvecomment',
	'showcomment',
	'distinguish',
	'marknsfw',
	'ignorereports',
	'unignorereports',
	'setsuggestedsort',
	'sticky',
	'unsticky',
	'setcontestmode',
	'unsetcontestmode',
	'lock',
	'unlock',
	'spoiler',
	'unspoiler',
	'modmail_enrollment',
	'markoriginalcontent',
}

WARNING_LOG_TYPES = {
	"banuser": {"details": "permanent", "print": ["target_author", "details"]},
	'unbanuser': {"description": "!was temporary"},
	'editflair': {"mod": "!OWMatchThreads", "target_title": "!"},
	'wikirevise': {"mod": "!OWMatchThreads", "details": "!Page usernotes edited"},
}