#!/usr/bin/env python3
"""Build one page with everything the research found, to look through.

Reads research/outliers.json and whatever else is there (analyses, shape, formats, strips,
downloaded videos) and writes research/wall.html: the measured formats on top, then every
breakout as a card with its numbers, its first line, how it is built and what is worth
copying. Open the file in a browser; downloaded videos play in place.

The page holds other people's captions and transcripts. It is for your own reading: do not
publish it.

Usage: reel wall [--min-ratio 2] [--max-age-days 365] [--group NAME]
"""

import argparse
import json
import re
import sys

import kit

ROOT = kit.find_project()
RESEARCH = ROOT / "research"

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research wall</title>
<style>
  :root { --bg:#f6f5f2; --card:#fff; --ink:#16161a; --soft:#6b6b76; --line:#e4e2dc; --accent:#3d6b00; --chip:#eef4dd; }
  @media (prefers-color-scheme: dark) { :root { --bg:#111114; --card:#1b1b20; --ink:#f1f1f4; --soft:#9a9aa6; --line:#2c2c34; --accent:#c8f53c; --chip:#2a3312; } }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }
  main { max-width:1180px; margin:0 auto; padding:28px 16px 80px; }
  h1 { font-size:26px; margin:0 0 4px; } h2 { font-size:18px; margin:36px 0 12px; }
  p.lead { color:var(--soft); margin:0 0 20px; max-width:70ch; }
  .bar { display:flex; flex-wrap:wrap; gap:8px; margin:0 0 18px; }
  .bar button { font:inherit; padding:6px 12px; border-radius:999px; border:1px solid var(--line); background:var(--card); color:var(--ink); cursor:pointer; }
  .bar button[aria-pressed=true] { background:var(--ink); color:var(--bg); border-color:var(--ink); }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(330px,1fr)); gap:14px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:14px; min-width:0; }
  .card img, .card video { width:100%; border-radius:8px; display:block; margin-bottom:10px; background:#000; }
  .card video { max-height:520px; }
  .top { display:flex; justify-content:space-between; gap:10px; align-items:baseline; }
  .ratio { font-size:22px; font-weight:700; color:var(--accent); white-space:nowrap; }
  .who { font-weight:600; overflow-wrap:anywhere; } .meta { color:var(--soft); font-size:13px; }
  .hook { margin:10px 0 6px; font-size:16px; font-weight:600; overflow-wrap:anywhere; }
  .chips { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0; }
  .chips span { background:var(--chip); border-radius:6px; padding:2px 8px; font-size:12px; }
  ul { margin:6px 0; padding-left:18px; } li { margin:2px 0; }
  details { margin-top:8px; } summary { cursor:pointer; color:var(--soft); font-size:13px; }
  a { color:var(--accent); }
  .scroll { overflow-x:auto; background:var(--card); border:1px solid var(--line); border-radius:14px; }
  table { border-collapse:collapse; width:100%; }
  tr:last-child td { border-bottom:0; }
  th, td { text-align:left; padding:8px 12px; border-bottom:1px solid var(--line); vertical-align:top; } th { font-size:12px; color:var(--soft); font-weight:600; }
</style>
</head>
<body>
<main>
  <h1>Research wall</h1>
  <p class="lead" id="lead"></p>
  <section id="formats"></section>
  <h2>Breakouts</h2>
  <div class="bar" id="bar"></div>
  <div class="grid" id="grid"></div>
</main>
<script>
const DATA = /*__DATA__*/null;
const el = (tag, attrs = {}, kids = []) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) { if (k === "text") node.textContent = v; else node.setAttribute(k, v); }
  for (const kid of [].concat(kids)) if (kid) node.append(kid);
  return node;
};
const compact = (n) => n >= 1e6 ? (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + "M" : n >= 1e3 ? Math.round(n / 1e3) + "K" : String(n);
const multiple = (r) => (r >= 10 ? Math.round(r) : r.toFixed(1)) + "\\u00d7";
const state = { only: "all", group: "all" };

document.getElementById("lead").textContent =
  `${DATA.videos.length} videos that did at least ${DATA.minRatio} times their account's usual plays, from ${DATA.accounts} accounts and ${DATA.posts} posts. ` +
  `${DATA.videos.filter((v) => v.analysis).length} have been watched and broken down. The multiple compares a video with the median of the same account, so it says something about the video and not the size of the account.`;

if (DATA.formats.length) {
  const rows = DATA.formats.map((f) => el("tr", {}, [
    el("td", {}, [el("strong", { text: f.name }), el("div", { class: "meta", text: f.how || "" })]),
    el("td", { text: f.handles.join(", ") }),
    el("td", { text: `${f.episodes}` }),
    el("td", { text: `${f.beat2x} of ${f.episodes}` }),
    el("td", { text: `${f.below_half} of ${f.episodes}` }),
    el("td", {}, f.examples.map((x, i) => el("div", {}, el("a", { href: x.url, target: "_blank", rel: "noopener", text: `example ${i + 1} (${multiple(x.ratio)})` })))),
  ]));
  document.getElementById("formats").append(
    el("h2", { text: "Formats that repeat" }),
    el("div", { class: "scroll" }, el("table", {}, [el("tr", {}, ["Format", "Who", "Episodes", "Beat 2\\u00d7 usual", "Below half", "Strongest"].map((t) => el("th", { text: t }))), ...rows])));
}

function card(v) {
  const a = v.analysis;
  const media = v.video ? el("video", { controls: "", preload: "none", src: v.video, poster: v.strip || "" }) : v.strip ? el("img", { src: v.strip, alt: "", loading: "lazy" }) : null;
  const facts = [v.posted, v.duration ? `${Math.round(v.duration)} s` : null, v.cuts_per_minute != null ? `${v.cuts_per_minute} cuts/min` : null, v.group].filter(Boolean).join(" \\u00b7 ");
  const kids = [
    media,
    el("div", { class: "top" }, [el("div", {}, [el("div", { class: "who", text: `@${v.handle}` }), el("div", { class: "meta", text: `${v.platform} \\u00b7 ${compact(v.plays)} plays, usual ${compact(v.median)}` })]), el("div", { class: "ratio", text: multiple(v.ratio) })]),
    el("div", { class: "meta", text: facts }),
  ];
  if (a) {
    kids.push(el("div", { class: "hook", text: a.hook.line ? `\\u201c${a.hook.line}\\u201d` : a.topic || "" }));
    kids.push(el("div", { class: "chips" }, [a.format, a.hook.mechanism, a.scripted, a.captions && `captions: ${a.captions}`, a.effort && `effort: ${a.effort}`].filter(Boolean).map((t) => el("span", { text: String(t).replaceAll("_", " ") }))));
    if (a.hook.text) kids.push(el("div", { class: "meta", text: `On screen: ${a.hook.text}` }));
    if (a.copy.length) kids.push(el("ul", {}, a.copy.map((t) => el("li", { text: t }))));
    kids.push(el("details", {}, [el("summary", { text: "How it is built" }),
      el("ul", {}, a.beats.map((b) => el("li", { text: `${b.range} ${b.beat}: ${b.what}` }))),
      a.hook.why ? el("p", { text: `Why the opening works: ${a.hook.why}` }) : null,
      a.why ? el("p", { text: `Why it did well: ${a.why}` }) : null,
      a.needs.length ? el("p", { class: "meta", text: `Needs: ${a.needs.join(", ")}` }) : null]));
  } else {
    kids.push(el("div", { class: "hook", text: v.caption || "No caption" }));
    kids.push(el("div", { class: "meta", text: "Not watched yet (reel watch)" }));
  }
  kids.push(el("div", {}, el("a", { href: v.url, target: "_blank", rel: "noopener", text: "Open the original" })));
  return el("article", { class: "card" }, kids);
}

function chips(key, options) {
  return options.map(([value, text]) => {
    const button = el("button", { type: "button", "aria-pressed": String(state[key] === value), text });
    button.onclick = () => { state[key] = value; render(); };
    return button;
  });
}

function render() {
  const groups = [...new Set(DATA.videos.map((v) => v.group).filter(Boolean))];
  document.getElementById("bar").replaceChildren(
    ...chips("only", [["all", "All"], ["watched", "Watched"], ["unwatched", "Not watched"]]),
    ...(groups.length > 1 ? chips("group", [["all", "Every group"], ...groups.map((g) => [g, g])]) : []));
  const shown = DATA.videos.filter((v) => (state.only === "all" || (state.only === "watched") === Boolean(v.analysis)) && (state.group === "all" || v.group === state.group));
  document.getElementById("grid").replaceChildren(...shown.map(card));
}
render();
</script>
</body>
</html>
"""


def slug(post):
    tail = re.sub(r"[^A-Za-z0-9_-]", "", (post.get("url") or "").rstrip("/").split("/")[-1])[:20]
    return f"{post['platform']}_{post['handle']}_{tail}"


def breakdown(key):
    """The parts of a video's analysis the page shows, or None when it has not been watched."""
    file = RESEARCH / "analyses" / f"{key}.json"
    if not file.exists():
        return None
    analysis = json.loads(file.read_text())["analysis"].get("result")
    if not analysis:
        return None
    hook, editing, copyability = analysis.get("hook") or {}, analysis.get("editing") or {}, analysis.get("copyability") or {}
    captions = editing.get("captions") or {}
    return {
        "format": analysis.get("format"),
        "topic": analysis.get("topic"),
        "hook": {"line": hook.get("spoken_first_line"), "text": hook.get("on_screen_text"), "mechanism": hook.get("mechanism"), "why": hook.get("why_it_works")},
        "beats": [{"range": b.get("range") or "", "beat": b.get("beat") or "", "what": b.get("what_happens") or ""} for b in (analysis.get("structure") or [])[:10]],
        "scripted": (analysis.get("delivery") or {}).get("scripted_or_loose"),
        "captions": captions.get("style") if captions.get("present") else "none",
        "copy": copyability.get("what_to_copy") or [],
        "effort": copyability.get("effort_for_solo_creator"),
        "needs": copyability.get("needs_beyond_phone_and_bullets") or [],
        "why": analysis.get("why_it_outperformed"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-ratio", type=float, default=2.0)
    parser.add_argument("--max-age-days", type=int, default=365)
    parser.add_argument("--group")
    args = parser.parse_args()
    outliers = RESEARCH / "outliers.json"
    if not outliers.exists():
        sys.exit("research/outliers.json is missing: run `reel scrape` first")
    posts = json.loads(outliers.read_text())["posts"]
    shape = json.loads((RESEARCH / "shape.json").read_text()) if (RESEARCH / "shape.json").exists() else {}
    formats = json.loads((RESEARCH / "formats.json").read_text()) if (RESEARCH / "formats.json").exists() else []
    videos = []
    for post in posts:
        key = slug(post)
        analysis = breakdown(key)
        # A watched video is always shown; the rest only if they are a recent breakout.
        if not analysis and ((post.get("ratio") or 0) < args.min_ratio or not 3 <= (post.get("age_days") or 0) <= args.max_age_days):
            continue
        if args.group and post.get("group") != args.group:
            continue
        caption = " ".join((post.get("caption") or "").split())
        videos.append({
            "handle": post["handle"], "platform": post["platform"], "url": post["url"], "group": post.get("group"),
            "plays": post["plays"], "median": round(post["account_median_plays"]), "ratio": post["ratio"],
            "posted": (post.get("posted") or "")[:10], "duration": post.get("duration"),
            "caption": caption[:180] + ("…" if len(caption) > 180 else ""),
            "cuts_per_minute": (shape.get(key) or {}).get("cuts_per_minute"),
            "strip": f"strips/{key}.jpg" if (RESEARCH / "strips" / f"{key}.jpg").exists() else f"frames/{key}.jpg" if (RESEARCH / "frames" / f"{key}.jpg").exists() else None,
            "video": f"videos/{key}.mp4" if (RESEARCH / "videos" / f"{key}.mp4").exists() else None,
            "analysis": analysis,
        })
    data = {"videos": videos, "formats": formats, "posts": len(posts), "accounts": len({(p["platform"], p["handle"]) for p in posts}), "minRatio": args.min_ratio}
    out = RESEARCH / "wall.html"
    out.write_text(PAGE.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))
    print(f"{len(videos)} videos ({sum(1 for v in videos if v['analysis'])} watched), {len(formats)} formats -> {out}")


if __name__ == "__main__":
    main()
