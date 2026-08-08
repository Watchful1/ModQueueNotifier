"""Spike 1, answered with the PRAW bot's credentials instead of a Devvit install.

The Devvit menu item can only run where the app is installed, and installing on
the real subreddits needs approval. But the question — does every rule's
violation reason match a removal reason title? — is about *those subreddits'
data*, which a mock setup in a test sub cannot answer. The PRAW bot already has
moderator access to both, so ask it directly.

Run from the repo root:

    pipenv run python scripts/spike1_rules_vs_reasons.py

Uses `CustomModBot` from praw.ini, the same account main.py drives CompOW with.

Deliberately imports nothing from `src/`. `static.py` calls
`discord_logging.get_logger()` at import time and raises unless the logger has
been initialised first, so pulling it in for one constant would mean standing up
the bot's whole logging stack to read a user-agent string.
"""

import praw

# Copied from src/static.py rather than imported, per the note above.
USER_AGENT = "ModQueueNotifier (by /u/Watchful1)"

ACCOUNT = "CustomModBot"
SUBREDDITS = ["CompetitiveOverwatch", "bayarea"]

reddit = praw.Reddit(ACCOUNT, user_agent=USER_AGENT)
print(f"logged in as u/{reddit.user.me().name}\n")

for name in SUBREDDITS:
    sub = reddit.subreddit(name)

    # `subreddit.rules` — a cached property returning an iterable SubredditRules.
    # Not `subreddit.mod.rules()`: rules are public, so they do not live behind
    # the moderation interface. Removal reasons are mod-only and do.
    rules = list(sub.rules)
    reasons = list(sub.mod.removal_reasons)

    print(f"=== r/{name}: {len(rules)} rule(s), {len(reasons)} removal reason(s) ===")

    # The raw fields first. Two runs of this script died on a guessed attribute
    # name, so show what is actually there before relying on any of it.
    if rules:
        print(f"\n  rule attributes: {sorted(vars(rules[0]))}")
    if reasons:
        print(f"  removal reason attributes: {sorted(vars(reasons[0]))}")

    reason_titles = {getattr(r, "title", None) for r in reasons}
    reason_titles.discard(None)

    print("\n  removal reason titles:")
    for title in sorted(reason_titles):
        print(f"    {title!r}")

    print("\n  rules:")
    unmatched = []
    for rule in rules:
        # `violation_reason` is the short form shown in the report dialog; it
        # falls back to the rule's short_name when a mod never set one, which is
        # itself worth seeing in the output.
        violation = getattr(rule, "violation_reason", None) or rule.short_name
        hit = violation in reason_titles
        if not hit:
            unmatched.append(violation)
        print(f"    [{'MATCH' if hit else 'NO   '}] {rule.short_name!r}")
        print(f"             violation_reason = {violation!r}")

    if not rules:
        verdict = "no rules configured — inconclusive"
    elif not unmatched:
        verdict = "YES — every rule has a matching removal reason title"
    else:
        verdict = (
            f"NO — {len(unmatched)} of {len(rules)} rule(s) have no matching "
            f"removal reason title: {unmatched!r}"
        )
    print(f"\n  VERDICT for r/{name}: {verdict}\n")
