#!/usr/bin/env python3
"""Scrape recent posts for the seed accounts and rank outliers.

Reads research/seeds.json, runs the Apify Instagram Reels and TikTok actors, stores the
raw items under research/raw/, and writes research/outliers.json: every post with its
plays relative to the median of the same account, which is the only comparison that
says anything about the video rather than the size of the account.

research/seeds.json lists the accounts to learn from, per platform. "group" and "lang" are
free labels of yours, kept on every post so you can filter by them later:

  {"instagram": [{"handle": "someone", "group": "peers", "lang": "en"}],
   "tiktok":    [{"handle": "someone", "group": "peers", "lang": "en"}]}

Needs APIFY_TOKEN in the project's .env. Apify charges per result; each run prints its cost.
Scraping is subject to the platforms' terms and your local law; that judgement is yours.

Usage:
  reel scrape --limit 25            # scrape both platforms, then rank
  reel scrape --platform instagram  # one platform
  reel scrape --rank-only           # re-rank from stored raw files
"""

import argparse
import json
import statistics
import sys
import time
import urllib.request
from datetime import datetime, timezone

import kit

ROOT = kit.find_project()
RAW = ROOT / "research" / "raw"
SEEDS = ROOT / "research" / "seeds.json"
OUT = ROOT / "research" / "outliers.json"
API = "https://api.apify.com/v2"

ACTORS = {
    "instagram": "apify~instagram-reel-scraper",
    "tiktok": "clockworks~tiktok-scraper",
}

# Counts on very fresh posts are still climbing, so they would look like underperformers.
MIN_AGE_DAYS = 3
MIN_POSTS_FOR_MEDIAN = 5


def api(method, path, token, body=None):
    request = urllib.request.Request(
        f"{API}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())


def actor_input(platform, handles, limit):
    if platform == "instagram":
        return {"username": handles, "resultsLimit": limit}
    return {
        "profiles": handles,
        "resultsPerPage": limit,
        "profileSorting": "latest",
        "shouldDownloadVideos": False,
        "shouldDownloadCovers": False,
        "shouldDownloadSubtitles": False,
    }


def run_actor(platform, handles, limit, token):
    run = api("POST", f"/acts/{ACTORS[platform]}/runs", token, actor_input(platform, handles, limit))["data"]
    print(f"{platform}: run {run['id']} started for {len(handles)} accounts")
    while run["status"] in ("READY", "RUNNING"):
        time.sleep(10)
        run = api("GET", f"/actor-runs/{run['id']}", token)["data"]
    print(f"{platform}: {run['status']}, cost ${run.get('usageTotalUsd', 0):.3f}")
    if run["status"] != "SUCCEEDED":
        sys.exit(f"{platform} run ended as {run['status']}")
    return api("GET", f"/datasets/{run['defaultDatasetId']}/items?clean=true", token)


def normalize(platform, item):
    if platform == "instagram":
        if item.get("error") or not item.get("ownerUsername"):
            return None
        return {
            "platform": "instagram",
            "handle": item["ownerUsername"],
            "url": item.get("url"),
            "posted": item.get("timestamp"),
            "plays": item.get("videoPlayCount") or item.get("videoViewCount"),
            "likes": item.get("likesCount"),
            "comments": item.get("commentsCount"),
            "shares": None,
            "duration": item.get("videoDuration"),
            "caption": item.get("caption") or "",
            "pinned": bool(item.get("isPinned")),
            "video_url": item.get("videoUrl"),
        }
    author = item.get("authorMeta") or {}
    if not author.get("name") or item.get("isSlideshow"):
        return None
    return {
        "platform": "tiktok",
        "handle": author["name"],
        "url": item.get("webVideoUrl"),
        "posted": item.get("createTimeISO"),
        "plays": item.get("playCount"),
        "likes": item.get("diggCount"),
        "comments": item.get("commentCount"),
        "shares": item.get("shareCount"),
        "duration": (item.get("videoMeta") or {}).get("duration"),
        "caption": item.get("text") or "",
        "pinned": bool(item.get("isPinned")),
        # The actor returns no file link unless it is paid to download; watch.py fetches
        # TikTok videos from the page URL instead.
        "video_url": None,
        "followers": author.get("fans"),
    }


def age_days(posted):
    if not posted:
        return None
    return (datetime.now(timezone.utc) - datetime.fromisoformat(posted.replace("Z", "+00:00"))).days


def rank(seeds):
    meta = {(p, s["handle"].lower()): s for p in ACTORS for s in seeds.get(p, [])}
    posts, missing = [], []
    for platform in ACTORS:
        path = RAW / f"{platform}.json"
        if not path.exists():
            continue
        for item in json.loads(path.read_text()):
            if platform == "instagram" and item.get("error"):
                missing.append({"platform": platform, "handle": item.get("username"), "error": item["error"]})
                continue
            post = normalize(platform, item)
            if post and post["plays"]:
                posts.append(post)

    by_account = {}
    for post in posts:
        by_account.setdefault((post["platform"], post["handle"].lower()), []).append(post)

    ranked = []
    for key, items in by_account.items():
        # A collab post shows up under the other account's handle; without the seed's
        # own baseline the ratio would be meaningless.
        if key not in meta:
            continue
        baseline = [p["plays"] for p in items if not p["pinned"] and (age_days(p["posted"]) or 0) >= MIN_AGE_DAYS]
        if len(baseline) < MIN_POSTS_FOR_MEDIAN:
            continue
        median = statistics.median(baseline)
        for post in items:
            post["account_median_plays"] = median
            post["ratio"] = round(post["plays"] / median, 2) if median else None
            post["age_days"] = age_days(post["posted"])
            post["lang"] = meta[key].get("lang")
            post["group"] = meta[key].get("group")
            ranked.append(post)

    ranked.sort(key=lambda p: p["ratio"] or 0, reverse=True)
    OUT.write_text(json.dumps({"posts": ranked, "missing": missing}, indent=2, ensure_ascii=False))
    print(f"ranked {len(ranked)} posts from {len({(p['platform'], p['handle']) for p in ranked})} accounts -> {OUT}")
    if missing:
        print("not found:", ", ".join(f"{m['platform']}:{m['handle']}" for m in missing))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=list(ACTORS))
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--rank-only", action="store_true")
    args = parser.parse_args()

    if not SEEDS.exists():
        sys.exit(f"{SEEDS} is missing. It lists the accounts to learn from; `reel init` writes an example.")
    seeds = json.loads(SEEDS.read_text())
    if not args.rank_only:
        token = kit.env("APIFY_TOKEN")
        RAW.mkdir(parents=True, exist_ok=True)
        for platform in [args.platform] if args.platform else list(ACTORS):
            handles = [s["handle"] for s in seeds.get(platform, [])]
            if not handles:
                continue
            items = run_actor(platform, handles, args.limit, token)
            (RAW / f"{platform}.json").write_text(json.dumps(items, ensure_ascii=False))
    rank(seeds)


if __name__ == "__main__":
    main()
