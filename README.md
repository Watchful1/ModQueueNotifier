# ModQueueBot

This is a custom moderation bot created by u/Watchful1.

## Features

### Log saving
Saves the entirety of the mod log to a database for easy historical analysis and searching. Also notifies when it encounters a new log item of specific types

### Modqueue comments
Checks the modqueue for any comments that have been reported by a moderator where the report is

* `r1 w` sends a modmail to the user warning them for breaking the rules
* `r1 3` bans the user for 3 days, works for any number of days
* `r1 p` permabans the user
* `r1` reads the users toolbox usernotes to determine the length of their most recent ban, then bans them based on the next tier below. If the most recent action was more than 6 months ago, uses the same tier instead of going to the next one.
  * Warning
  * 3 day ban
  * 7 day ban
  * 14 day ban
  * Permaban 

In all cases, the message to the user includes a link to the infringing comment. The bot also 

* Removes the comment and all child comments
* Archives the modmail message that was generated

### Count queue sizes
Counts the size of the unmod and mod queues, as well as the number of modmails, plus the age in hours of the oldest item in unmod and the oldest modmail. These are then saved as a metric over time.

Highlighted modmails are excluded from these counts

### Ping queue sizes - only in r/competitiveoverwatch
Based on the counts above, posts in discord when they reach certain thresholds, as well as pinging @here at a higher threshold

* Unmod - 15, ping 20
* Unmod age - 4, ping 6
* Modqueue - 8, ping 12
* Modmail - 5, ping 8
* Modmail age - 12, ping 24

### Modqueue submissions - only in r/competitiveoverwatch
Checks the modqueue for any submissions that have been reported by a moderator for any of the regular report reasons

* Removes the post
* Locks the post
* Changes the flair to "removed"
* Comments the removal reason in a stickied comment on the post

Additionally, uses the relevant removal reason for custom reports `offtopic` and `dupe`

### Modqueue reapprove - only in r/competitiveoverwatch
Checks for any items in the modqueue that have been previously manually approved, but have since been reported as low value or spam, and reapproves them

### Report highlighted modmails - only in r/competitiveoverwatch
Notifies when there's a new reply to a modmail that is marked as highlighted, or is from an admin

### Report archived modmails without response - only in r/competitiveoverwatch
Notifies if a modmail is archived without any response from a mod

### Process new submissions - only in r/competitiveoverwatch
If the post is the new weekly short questions megathread, edits the sidebar to update the link

If the submission is approved, but doesn't have a flair set, pings the mod who did it in discord

### Process modmails - only in r/competitiveoverwatch
Checks modmail for notifications from automod that a post has gotten three reports, then checks the post in question. If the post was deleted, removed or approved, replies to the modmail with the action and then archives it
