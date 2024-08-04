import discord_logging

log = discord_logging.get_logger()

from classes import Rule


USER_AGENT = "ModQueueNotifier (by /u/Watchful1)"


WHITELISTED_ACCOUNTS = {
	"OWMatchThreads",
	"AutoModerator",
	"CustomModBot",
	"bayarea-ModTeam",
	"Competitiveoverwatch-ModTeam",
}

REDDIT_ACCOUNTS = {
	"reddit",
	"Anti-Evil",
	"comment-nuke",
}


COMPOW_MODERATORS = {
	#"merger3": "143730443777343488",
	#"DerWaechter_": "193382989718093833",
	#"connlocks": "139462031894904832",
	#"Sorglos": "166045025153581056",
	"Watchful1": "95296130761371648",
	"blankepitaph": "262708160790396928",
	#"Quantum027": "368589871092334612",
	"imKaku": "120207112646164480",
	#"KarmaCollect": "196018859889786880",
	#"wotugondo": "385460099138715650",
	"ModWilliam": "321107093773877257",
	"Dobvius": "171644935446069249",
	#"FelipeDoesStats2": "277798095906144257",
	"lolburger13": "272096309320613888",
	"TheUltimate721": "330534850849406977",
	"UnknownQTY": "432625266532024330",
	"OWMatchThreads": "OWMatchThreads",
	"AutoModerator": "AutoModerator",
}

BAYAREA_MODERATORS = {
	#"dihydrogen_monoxide": "74601397701578752",
	"TrucyWright": "145398757582700544",
	"Watchful1": "95296130761371648",
	"-dantastic-": "543108284849324034",
	"which_objective": "714692771687956511",
	"MsNewKicks": "811705167673688086",
	#"DuckyFreeman": "318215764303675392",
	"AutoModerator": "AutoModerator",
	"CustomModBot": "CustomModBot",
	"BotDefense": "BotDefense",
	"comment-nuke": "comment-nuke",
}

COMPOW_KNOWN_LOG_TYPES = {
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
	'submit_scheduled_post',
	'addremovalreason',
}

BAYAREA_KNOWN_LOG_TYPES = {
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
	'banuser',
	'unbanuser',
	'editflair',
	'submit_scheduled_post',
	'unmuteuser',
	'addremovalreason',
}

COMPOW_WARNING_LOG_TYPES = {
	"banuser": {"details": "~permanent", "print": ["target_author", "details"]},
	'unbanuser': {"description": "!was temporary"},
	'editflair': {"mod": "!OWMatchThreads", "target_title": "!"},
	'wikirevise': {"mod": "!OWMatchThreads", "details": "!Page usernotes edited"},
	'editsettings': {"mod": "!OWMatchThreads", "details": "!description"},
}

BAYAREA_WARNING_LOG_TYPES = {
	'wikirevise': {"mod": "!OWMatchThreads", "details": "!Page usernotes edited"},
}

REMOVAL_REASON_HEADER = """Thank you for your submission to /r/{}! Unfortunately it was removed for the following reason(s):"""
REMOVAL_REASON_FOOTER = """Please [message the moderators](https://www.reddit.com/message/compose?to=/r/{}) if you have any questions."""

COMPOW_RULES = [
	Rule(
		report_reason="#1 No Poor or Abusive Behavior", rule_number="1",
		post_text=""">Posts and comments that are toxic or break Reddiquette will be removed. This includes, but is not limited to:

>* Personal attacks, targeted harassment, and/or any other form of abusive behavior against other users, players, or community figures (Remember that players and community figures read /r/CompetitiveOverwatch too!)  
* Any form of hate speech or bigotry is not tolerated (such as sexism, racism, homophobia, transphobia, ableism, etc)  
* Witch-hunts, vote manipulation, and/or brigading (also see Rule #6 for further clarification about witch-hunts)  
* Posting other users' personal information without their consent (doxing)  
* Offering, requesting, promoting, and/or linking to cheats, rank manipulation services, and/or game-breaking exploits  
* Photos or videos taken of players, community figures, or other persons without their consent, outside of official events  
* Trolling and/or repeated comments/posts that cause significant Community Disruption.  

>If you see any doxing or feel that you are the target of harassment, please [message the mod team](https://www.reddit.com/message/compose?to=%2Fr%2FCompetitiveoverwatch) immediately!""",
		comment_text="No poor or abusive behavior",
		short_text="abusive comment",
	),
	Rule(
		report_reason="#2 No Low-Value Content", rule_number="2",
		post_text=""">Your post is in violation of Rule #2 and is considered low value. A list of examples of high vs low value content [can be found here](https://www.reddit.com/r/Competitiveoverwatch/wiki/rules#wiki_rule_.232_no_off-topic_or_low-value_content).""",
	),
	Rule(
		report_reason="#3 No Spoilers in titles for 24 Hours", rule_number="3",
		post_text=""">Your post title contains a spoiler. Because not everybody has the luxury of watching live, we prevent spoilers for 24 hours after a match or tournament. However, you may re-post your thread with a more suitable title.""",
	),
	Rule(
		report_reason="#4 Limit Self Promotion", rule_number="4",
		post_text=""">For every 9 posts or comments you make on other people's content here on /r/CompetitiveOverwatch, you are allowed to post 1 item of your own content. Even if you are not the creator, repeatedly posting the same person's content is subject to this rule as well. You must post at least 9 non-affiliated comments or submissions between each post. These comments and posts should be genuine, and not meaningless fluff intended solely to reach the 9:1 ratio.

>Exceptions:

>* Tournament announcements and news articles announcing team signings and/or roster changes  
* Official content from Overwatch League teams or Contenders teams  
* Written articles where the entire text of the article is posted to the subreddit  

>Prohibited:

>* Prize draws and/or giveaways  
* Gambling or other paid services  
* Discord communities unless they are for a tournament.  
* LFT self-posts for players, coaches, or staff  """,
	),
	Rule(
		report_reason="#5 Meme Restrictions", rule_number="5",
		post_text="""Your post is in violation of our meme guidelines under Rule #5:

Memes must be related to competitive Overwatch and based on a non-generic template.

A non-generic template contains content that is entirely from the Overwatch game, Overwatch-related media, or competitive Overwatch tournaments. Overwatch images imposed over a generic template are not allowed.

The exception is made for video memes (for example, Overwatch related text and images overlaid onto a video) and templates recreated in their entirety (for example, https://i.redd.it/vvvyde85a4j31.png).""",
	),
	Rule(
		report_reason="#6 Accusations or Calls to Action", rule_number="6",
		post_text=""">No Unsubstantiated Accusations or Calls to Action

>Posting clips, images or claims that could result in a person being subject to investigation and/or disciplinary action by Blizzard, team management, or other authority is prohibited until there is an official public announcement, or if it is published by a reputable source (see below for details).

>This includes, but is not limited to the following:

>- Cheating
>- Boosting
>- Throwing / One-tricking
>- False reporting

> If you come across anyone doing any of the above, report them directly to Blizzard through the proper channels, do not post a thread about the incident here.

> A post being classified as "published by a reputable source" requires one of the following three:

>- Being a party directly linked to the story.
>- A proven track record of investigative journalism.
>- Confidential verification of the story to the mod team.""",
	),
	Rule(
		report_reason="#7 Gameplay Content", rule_number="7",
		post_text="""###Rule #7 Gameplay Content

>All gameplay content, such as clips and videos where the main focus is on the gameplay, must primarily contain content from competitive modes such as the competitive ladder, scrims, and/or tournaments, and are subject to the following limitations:

>* General gameplay videos are never allowed, including VOD review requests (head over to /r/OverwatchUniversity for VOD review requests)  
* Montages and/or frag movies must be of a pro-player, pro-team, and/or community figures  
* Stream highlights must showcase an extremely high-level of play, an exceptional level of skill, and/or a highly unusual moment  
* Tournament highlights are generally allowed provided that they are clips of an actual play and/or strategy  

> All other clips and videos are subject to Rule #2 instead.""",
	),
	Rule(
		report_reason="#8 No Misleading Titles", rule_number="8",
		post_text="""> Titles of posts cannot be misleading, including in the following ways:

> * Titles cannot falsely imply that an announcement is official.
> * Titles cannot paraphrase or summarize in a way that misrepresents the content of the post.""",
	),
	Rule(
		report_reason="#9 No duplicate posts", rule_number="9",
		post_text=""">Someone else has posted about this topic recently. Occasionally we may pick an alternative thread if it has more discussion, even if it's not the first thread on a subject.""",
	),
	Rule(
		report_reason="#10 No Off-Topic Content", rule_number="10",
		post_text=""">This post doesn't relate to Competitive Overwatch or Overwatch esports.""",
	),
]

BAYAREA_RULES = [
	Rule(
		report_reason="#1 No poor or hostile behavior", rule_number="1",
		comment_text="No poor or hostile behavior", short_text="abusive comment",
	),
	Rule(
		report_reason="#2 No racism or other hate speech", rule_number="2",
		comment_text="No racism or other hate speech", short_text="racism/hate",
	),
	Rule(
		report_reason="#3 No advocating violence", rule_number="3",
		comment_text="No advocating violence", short_text="advocate violence",
	),
	Rule(
		report_reason="#4 No duplicate posts", rule_number="4",
		post_text="""Someone else has posted about this topic recently. Only posts with substantial new information will be allowed.""",
	),
	Rule(
		report_reason="#5 No advertising", rule_number="5",
		post_text="""Advertising anything that you or anyone associated with you makes money off of is not allowed. Giveaways, fundraisers and bayclub membership posts are not allowed.""",
		comment_text="No advertising", short_text="advertising",
	),
	Rule(
		report_reason="#6 No unverified or mislabeled crime posts", rule_number="6",
		post_text="""All posts about crime need a news article from a reputable organization or a statement from a state official or police force. They also must be correctly flaired.""",
	),
	Rule(
		report_reason="#7 No unverified contact information in missing person posts", rule_number="7",
		post_text="""Missing person posts may only link to official contact information. No personal phone numbers or social media.""",
	),
	Rule(
		report_reason="#8 Posts must be about the bay area", rule_number="8",
		post_text="""Posts must be about the bay area. Topics that are relevant to the bay but aren't directly in the bay are allowed.""",
	),
]

COMPOW_REPORT_REASONS = {
	"#1 No Poor or Abusive Behavior":
		{"rule": "1", "reason": """>Posts and comments that are toxic or break Reddiquette will be removed. This includes, but is not limited to:

>* Personal attacks, targeted harassment, and/or any other form of abusive behavior against other users, players, or community figures (Remember that players and community figures read /r/CompetitiveOverwatch too!)  
* Any form of hate speech or bigotry is not tolerated (such as sexism, racism, homophobia, transphobia, ableism, etc)  
* Witch-hunts, vote manipulation, and/or brigading (also see Rule #6 for further clarification about witch-hunts)  
* Posting other users' personal information without their consent (doxing)  
* Offering, requesting, promoting, and/or linking to cheats, rank manipulation services, and/or game-breaking exploits  
* Photos or videos taken of players, community figures, or other persons without their consent, outside of official events  
* Trolling and/or repeated comments/posts that cause significant Community Disruption.  

>If you see any doxing or feel that you are the target of harassment, please [message the mod team](https://www.reddit.com/message/compose?to=%2Fr%2FCompetitiveoverwatch) immediately!"""
		},
	"#2 No Low-Value Content":
		{"rule": "2", "reason": """>Your post is in violation of Rule #2 and is considered low value. A list of examples of high vs low value content [can be found here](https://www.reddit.com/r/Competitiveoverwatch/wiki/rules#wiki_rule_.232_no_off-topic_or_low-value_content)."""
		},
	"#3 No Spoilers in titles for 24 Hours":
		{"rule": "3", "reason": """>Your post title contains a spoiler. Because not everybody has the luxury of watching live, we prevent spoilers for 24 hours after a match or tournament. However, you may re-post your thread with a more suitable title."""
		},
	"#4 Limit Self Promotion":
		{"rule": "4", "reason": """>For every 9 posts or comments you make on other people's content here on /r/CompetitiveOverwatch, you are allowed to post 1 item of your own content. Even if you are not the creator, repeatedly posting the same person's content is subject to this rule as well. You must post at least 9 non-affiliated comments or submissions between each post. These comments and posts should be genuine, and not meaningless fluff intended solely to reach the 9:1 ratio.

>Exceptions:

>* Tournament announcements and news articles announcing team signings and/or roster changes  
* Official content from Overwatch League teams or Contenders teams  
* Written articles where the entire text of the article is posted to the subreddit  

>Prohibited:

>* Prize draws and/or giveaways  
* Gambling or other paid services  
* Discord communities unless they are for a tournament.  
* LFT self-posts for players, coaches, or staff  """
		},
	"#5 Meme Restrictions":
		{"rule": "5", "reason": """Your post is in violation of our meme guidelines under Rule #5:

Memes must be related to competitive Overwatch and based on a non-generic template.

A non-generic template contains content that is entirely from the Overwatch game, Overwatch-related media, or competitive Overwatch tournaments. Overwatch images imposed over a generic template are not allowed.

The exception is made for video memes (for example, Overwatch related text and images overlaid onto a video) and templates recreated in their entirety (for example, https://i.redd.it/vvvyde85a4j31.png)."""
		},
	"#6 Accusations or Calls to Action":
		{"rule": "6", "reason": """>No Unsubstantiated Accusations or Calls to Action

>Posting clips, images or claims that could result in a person being subject to investigation and/or disciplinary action by Blizzard, team management, or other authority is prohibited until there is an official public announcement, or if it is published by a reputable source (see below for details).

>This includes, but is not limited to the following:

>- Cheating
>- Boosting
>- Throwing / One-tricking
>- False reporting

> If you come across anyone doing any of the above, report them directly to Blizzard through the proper channels, do not post a thread about the incident here.

> A post being classified as "published by a reputable source" requires one of the following three:

>- Being a party directly linked to the story.
>- A proven track record of investigative journalism.
>- Confidential verification of the story to the mod team."""
		},
	"#7 Gameplay Content":
		{"rule": "7", "reason": """###Rule #7 Gameplay Content

>All gameplay content, such as clips and videos where the main focus is on the gameplay, must primarily contain content from competitive modes such as the competitive ladder, scrims, and/or tournaments, and are subject to the following limitations:

>* General gameplay videos are never allowed, including VOD review requests (head over to /r/OverwatchUniversity for VOD review requests)  
* Montages and/or frag movies must be of a pro-player, pro-team, and/or community figures  
* Stream highlights must showcase an extremely high-level of play, an exceptional level of skill, and/or a highly unusual moment  
* Tournament highlights are generally allowed provided that they are clips of an actual play and/or strategy  

> All other clips and videos are subject to Rule #2 instead."""
		},
	"#8 No Misleading Titles":
		{"rule": "8", "reason": """> Titles of posts cannot be misleading, including in the following ways:

> * Titles cannot falsely imply that an announcement is official.
> * Titles cannot paraphrase or summarize in a way that misrepresents the content of the post."""
		},
	"#9 No duplicate posts":
		{"rule": "9", "reason": """>Someone else has posted about this topic recently. Occasionally we may pick an alternative thread if it has more discussion, even if it's not the first thread on a subject."""
		},
	"#10 No Off-Topic Content":
		{"rule": "10", "reason": """>This post doesn't relate to Competitive Overwatch or Overwatch esports."""
		},
}

COMPOW_COMMENT_REPORT_REASONS = {
	"r1":
		{"rule": "1", "reason": "No poor or abusive behavior", "short_reason": "abusive comment"
		}
}

BAYAREA_COMMENT_REPORT_REASONS = {
	"r1":
		{"rule": "1", "reason": "No hateful or mean-spirited comments", "short_reason": "abusive comment"
		},
	"r5":
		{"rule": "5", "reason": "No covid misinformation or vaccine skepticism.", "short_reason": "covid misinfo"
		}
}
