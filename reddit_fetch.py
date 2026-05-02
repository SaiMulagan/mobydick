"""
Fetch top + hot posts from book-related subreddits via Reddit's public JSON
endpoints. No API key required. Output is newline-delimited JSON, ready for
`bq load --source_format=NEWLINE_DELIMITED_JSON`.

Polite throttle: 2 seconds between requests. Well under Reddit's 60-per-10-min
unauthenticated rate limit.
"""

import json
import time
from pathlib import Path

import requests

USER_AGENT = "moby-dicks-research/0.1 (course project; contact via repo)"

# Each entry: (subreddit, listing, time_filter_or_None)
LISTINGS = [
    ("books",           "hot", None),
    ("books",           "top", "year"),
    ("suggestmeabook",  "hot", None),
    ("suggestmeabook",  "top", "year"),
    ("literature",      "top", "year"),
]

THROTTLE_SECONDS = 2
LIMIT = 100
OUT_PATH = Path("reddit_posts.ndjson")


def fetch_listing(subreddit: str, sort: str, time_filter: str | None) -> dict:
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
    params = {"limit": LIMIT}
    if time_filter:
        params["t"] = time_filter
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def extract_posts(payload: dict, subreddit: str, sort: str) -> list[dict]:
    posts = []
    for child in payload.get("data", {}).get("children", []):
        d = child.get("data", {})
        posts.append({
            "post_id":        d.get("id"),
            "subreddit":      subreddit,
            "sort_bucket":    sort,
            "title":          d.get("title", ""),
            "selftext":       d.get("selftext", ""),
            "score":          d.get("score", 0),
            "upvote_ratio":   d.get("upvote_ratio", 0.0),
            "num_comments":   d.get("num_comments", 0),
            "created_utc":    d.get("created_utc", 0),
            "permalink":      d.get("permalink", ""),
            "url":            d.get("url", ""),
            "author":         d.get("author", ""),
            "link_flair_text": d.get("link_flair_text"),
        })
    return posts


def main() -> None:
    all_posts: list[dict] = []
    seen_ids: set[str] = set()

    for subreddit, sort, time_filter in LISTINGS:
        label = f"r/{subreddit} {sort}" + (f" t={time_filter}" if time_filter else "")
        print(f"[fetch] {label}")
        try:
            payload = fetch_listing(subreddit, sort, time_filter)
        except requests.HTTPError as e:
            print(f"  ERROR: {e}; skipping")
            time.sleep(THROTTLE_SECONDS)
            continue

        posts = extract_posts(payload, subreddit, sort)
        new = 0
        for p in posts:
            pid = p["post_id"]
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_posts.append(p)
                new += 1
        print(f"  -> {len(posts)} posts in listing, {new} new after dedup")
        time.sleep(THROTTLE_SECONDS)

    with OUT_PATH.open("w") as f:
        for p in all_posts:
            f.write(json.dumps(p) + "\n")

    print(f"\nWrote {len(all_posts)} unique posts to {OUT_PATH}")


if __name__ == "__main__":
    main()