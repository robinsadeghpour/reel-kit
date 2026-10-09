#!/usr/bin/env python3
r"""Measure whether a format that a creator repeats keeps working.

A format here is a premise one creator has used several times ("mistake number N of 10",
"I gave the new model one job"). A single breakout says little; a premise that beats the
account's usual video again and again is something you can plan around.

You write the definitions, after looking through the wall, in research/formats.def.json:

  [{"key": "numbered-mistakes",
    "name": "Mistake number N of 10",
    "handles": ["someone"],
    "match": "^MISTAKE NO\\.",
    "how": "One real mistake per episode, with the number that made it hurt."}]

  handles   the accounts that run it
  match     optional pattern the caption must contain (case does not matter)
  exclude   optional pattern the caption must not contain
  since     optional date, YYYY-MM-DD: only episodes posted from then on
  anything else (how, notes, your own version of it) is carried through untouched

For each one this counts the episodes in the scrape, how often they beat twice the
account's usual plays, how often they fell below half, and picks the three strongest as
examples. Result: research/formats.json.

Usage: reel formats
"""

import json
import re
import statistics
import sys

import kit

ROOT = kit.find_project()
RESEARCH = ROOT / "research"
FILTERS = ("handles", "match", "exclude", "since")


def slug(post):
    tail = re.sub(r"[^A-Za-z0-9_-]", "", (post.get("url") or "").rstrip("/").split("/")[-1])[:20]
    return f"{post['platform']}_{post['handle']}_{tail}"


def episodes(spec, posts):
    found = {}
    handles = {handle.lower() for handle in spec["handles"]}
    for post in posts:
        caption = post.get("caption") or ""
        if post["handle"].lower() not in handles:
            continue
        if spec.get("match") and not re.search(spec["match"], caption, re.I | re.M):
            continue
        if spec.get("exclude") and re.search(spec["exclude"], caption, re.I):
            continue
        if spec.get("since") and (post.get("posted") or "") < spec["since"]:
            continue
        # The same video posted more than once (trial reels) counts once, by its best run.
        key = (post["platform"], caption[:80], round(post.get("duration") or 0))
        if key not in found or post["plays"] > found[key]["plays"]:
            found[key] = post
    return sorted(found.values(), key=lambda p: -p["ratio"])


def main():
    definitions, outliers = RESEARCH / "formats.def.json", RESEARCH / "outliers.json"
    if not outliers.exists():
        sys.exit("research/outliers.json is missing: run `reel scrape` first")
    if not definitions.exists():
        sys.exit("research/formats.def.json is missing. It lists the formats to measure; `reel formats --help` shows what one looks like.")
    posts = json.loads(outliers.read_text())["posts"]
    out = []
    for spec in json.loads(definitions.read_text()):
        eps = episodes(spec, posts)
        if not eps:
            print(f"{spec['name'][:44]:44} no episodes found: check handles and match")
            continue
        dates = sorted((p.get("posted") or "")[:10] for p in eps)
        out.append({
            **{key: value for key, value in spec.items() if key not in FILTERS},
            "handles": sorted({p["handle"] for p in eps}),
            "episodes": len(eps),
            "beat2x": sum(p["ratio"] >= 2 for p in eps),
            "below_half": sum(p["ratio"] < 0.5 for p in eps),
            "typical_plays": round(statistics.median(p["plays"] for p in eps)),
            "usual_plays": round(statistics.median(p["account_median_plays"] for p in eps)),
            "first": dates[0], "last": dates[-1],
            "examples": [{"id": slug(p), "url": p["url"], "ratio": p["ratio"], "plays": p["plays"], "posted": (p.get("posted") or "")[:10]} for p in eps[:3]],
        })
    (RESEARCH / "formats.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for f in out:
        print(f"{f['name'][:44]:44} eps={f['episodes']:2} beat2x={f['beat2x']:2} <0.5x={f['below_half']:2} typical={f['typical_plays']:>8} usual={f['usual_plays']:>8} {f['first']}..{f['last']}")


if __name__ == "__main__":
    main()
