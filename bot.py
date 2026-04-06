import json
import os
import sys
from pathlib import Path

import feedparser
import praw

POSTED_FILE = Path("posted.json")


def load_posted() -> set:
    if POSTED_FILE.exists():
        with POSTED_FILE.open() as f:
            return set(json.load(f))
    return set()


def save_posted(posted: set) -> None:
    with POSTED_FILE.open("w") as f:
        json.dump(sorted(posted), f, indent=2)


def load_feeds() -> list:
    with open("feeds.json") as f:
        return json.load(f)


def get_reddit() -> praw.Reddit:
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        username=os.environ["REDDIT_USERNAME"],
        password=os.environ["REDDIT_PASSWORD"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", "rss-reddit-bot/1.0"),
    )


def process_feed(reddit: praw.Reddit, feed_config: dict, posted: set) -> int:
    url = feed_config["url"]
    subreddit_name = feed_config["subreddit"]
    flair = feed_config.get("flair")
    title_template = feed_config.get("title_template", "{title}")
    max_posts = feed_config.get("max_posts_per_run", 5)

    feed = feedparser.parse(url)
    if feed.bozo and not feed.entries:
        print(f"[WARN] Could not parse feed: {url}", file=sys.stderr)
        return 0

    subreddit = reddit.subreddit(subreddit_name)
    count = 0

    # Iterate entries from oldest to newest so the subreddit order is correct
    for entry in reversed(feed.entries):
        if count >= max_posts:
            break

        entry_id = entry.get("id") or entry.get("link")
        if not entry_id or entry_id in posted:
            continue

        title = title_template.format(
            title=entry.get("title", "No title"),
            source=feed.feed.get("title", ""),
        )
        link = entry.get("link", "")

        try:
            submission = subreddit.submit(title=title, url=link, resubmit=False)
            if flair:
                # Try to set flair; ignore if flair is not available
                try:
                    choices = list(subreddit.flair.link_templates.user_selectable())
                    match = next((c for c in choices if c["flair_text"] == flair), None)
                    if match:
                        submission.flair.select(match["flair_template_id"])
                except Exception:
                    pass

            posted.add(entry_id)
            count += 1
            print(f"[OK] Posted to r/{subreddit_name}: {title}")
        except praw.exceptions.APIException as e:
            if "ALREADY_SUB" in str(e):
                # URL was already submitted — still mark as seen
                posted.add(entry_id)
                print(f"[SKIP] Already submitted: {title}")
            else:
                print(f"[ERR] Reddit API error for '{title}': {e}", file=sys.stderr)
        except Exception as e:
            print(f"[ERR] Unexpected error for '{title}': {e}", file=sys.stderr)

    return count


def main() -> None:
    reddit = get_reddit()
    feeds = load_feeds()
    posted = load_posted()

    total = 0
    for feed_config in feeds:
        total += process_feed(reddit, feed_config, posted)

    save_posted(posted)
    print(f"Done. {total} new post(s) submitted.")


if __name__ == "__main__":
    main()
