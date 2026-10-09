#!/usr/bin/env python3
"""Have Gemini watch videos and describe how they are built.

Two passes per video, because the larger model tends to invent a transcript from what it
sees: a fast pass transcribes the audio verbatim, then a second pass at 2 FPS analyses the
picture with that transcript supplied.

Writes one file per video to research/analyses/, keeps the video in research/videos/ and a
sheet of stills in research/frames/. Other people's videos and words are downloaded to
understand how a video is built, not to reuse them: keep research/ out of anything you publish.

If research/brief.md exists, its text tells the model who the analysis is for (what you
make, what you can and cannot film), which makes "what to copy" more useful.

Needs GEMINI_API_KEY in the project's .env; the API charges per video. The two models can be
changed in reel.json: {"research": {"visual_model": "models/...", "transcript_model": "models/..."}}.

Usage:
  reel watch --top 40                # best outliers from research/outliers.json
  reel watch --top 20 --group peers  # one seed group
  reel watch --file clip.mp4         # a local file, e.g. one of your own edits
"""

import argparse
import base64
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import kit

ROOT = kit.find_project()
RESEARCH = ROOT / "research"
VIDEOS = RESEARCH / "videos"
ANALYSES = RESEARCH / "analyses"
FRAMES = RESEARCH / "frames"
API = "https://generativelanguage.googleapis.com"

MODELS = kit.settings().get("research", {})
VISUAL_MODEL = MODELS.get("visual_model", "models/gemini-3.1-pro-preview")
TRANSCRIPT_MODEL = MODELS.get("transcript_model", "models/gemini-3.8-flash")
DEFAULT_BRIEF = "The reader is a solo creator who wants to learn how this video is built, so be concrete about what is copyable."

# Inline requests are capped at about 20 MB including base64 overhead.
INLINE_LIMIT_BYTES = 13 * 1024 * 1024

TRANSCRIPT_PROMPT = """Transcribe the spoken audio of this video verbatim in its original language.
Return JSON: {"language": "ISO code", "has_speech": bool, "segments": [{"start": seconds, "end": seconds, "text": "..."}]}
Segments should be one sentence or clause each. Transcribe only what is audibly spoken.
Do not use on-screen text to fill gaps. If there is no speech, return an empty segments list."""

ANALYSIS_PROMPT = """You are analysing an organic short-form video (Instagram Reel or TikTok).
{CREATOR}

Context about this post:
{CONTEXT}

Verbatim transcript from a separate audio pass (trust this over your own hearing):
{TRANSCRIPT}

Watch the video at 2 FPS and return ONLY valid JSON with these fields:

{{
  "duration_seconds": <float>,
  "format": "talking_head" | "talking_head_plus_screen" | "green_screen" | "screen_recording_voiceover" | "walk_and_talk" | "street_interview" | "skit" | "podcast_clip" | "motion_graphic" | "other",
  "face_on_screen_percent": <int>,
  "topic": "one sentence: what the video is about",
  "core_claim": "the one thing the viewer is supposed to take away",

  "hook": {{
    "first_frame": "what is visible in the very first frame",
    "spoken_first_line": "first sentence spoken, verbatim from the transcript",
    "on_screen_text": "exact text on screen in the first 3 seconds, or null",
    "mechanism": "e.g. consequence, contrarian_claim, question, result_first, curiosity_gap, named_brand, number, demonstration, personal_stake",
    "seconds_until_topic_is_clear": <float>,
    "why_it_works": "specific, not generic"
  }},

  "structure": [
    {{"range": "0:00-0:04", "beat": "hook | context | point | example | proof | turn | payoff | cta", "what_happens": "...", "what_is_on_screen": "..."}}
  ],

  "delivery": {{
    "energy": "calm | conversational | energetic | intense",
    "pace": "slow | medium | fast",
    "scripted_or_loose": "sounds scripted | sounds like free talk | mixed",
    "eye_contact": "direct to lens | off camera | mixed"
  }},

  "setting": {{
    "location": "e.g. desk, sofa, kitchen, street, car, studio",
    "framing": "e.g. chest-up selfie, waist-up tripod, close-up",
    "camera": "handheld | tripod | moving",
    "lighting": "window | ring light | studio | mixed | poor",
    "production_level": "phone raw | phone polished | camera polished | studio"
  }},

  "editing": {{
    "total_cuts": <int>,
    "avg_seconds_between_cuts": <float>,
    "jump_cuts_on_speech": <bool>,
    "punch_in_zooms": <int>,
    "broll_or_cutaways": [{{"range": "0:10-0:13", "what": "screen recording of the product | stock | screenshot of a post | ..."}}],
    "captions": {{"present": <bool>, "style": "word-by-word highlight | 2-3 word chunks | full sentence | none", "position": "top | middle | bottom", "look": "font weight, colours, background"}},
    "other_overlays": ["title card", "progress bar", "emoji", "arrows", "..."],
    "music": "none | quiet bed | prominent",
    "sound_effects": <bool>
  }},

  "cta": {{"present": <bool>, "type": "comment keyword | follow | link in bio | save | none", "wording": "verbatim or null"}},

  "series": {{"looks_like_recurring_series": <bool>, "premise": "the repeatable premise, or null"}},

  "copyability": {{
    "effort_for_solo_creator": "low | medium | high",
    "needs_beyond_phone_and_bullets": ["screen recordings", "motion design", "second person", "location", "..."],
    "what_to_copy": ["3 to 5 specific, structural things worth copying"],
    "what_not_to_copy": "anything that only works for this creator, or null"
  }},

  "why_it_outperformed": "2-3 sentences: your best explanation for why this did better than this account's usual video. Say what you cannot know."
}}

Rules:
- Quote spoken and on-screen text verbatim in the original language. Do not translate.
- Every hard cut is a cut; count them from what you see.
- If something is not visible or audible, use null. Do not guess.
- No markdown fences, no commentary."""


def http(method, url, key, body=None, headers=None, timeout=600):
    request = urllib.request.Request(url, method=method, data=body, headers={"x-goog-api-key": key, **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


def upload_file(path, key):
    size = path.stat().st_size
    status, headers, _ = http(
        "POST", f"{API}/upload/v1beta/files", key,
        body=json.dumps({"file": {"display_name": path.name}}).encode(),
        headers={
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(size),
            "X-Goog-Upload-Header-Content-Type": "video/mp4",
            "Content-Type": "application/json",
        },
    )
    upload_url = {k.lower(): v for k, v in headers.items()}.get("x-goog-upload-url")
    if status != 200 or not upload_url:
        raise RuntimeError(f"upload start failed ({status})")
    status, _, raw = http(
        "POST", upload_url, key, body=path.read_bytes(),
        headers={"X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize"},
    )
    if status != 200:
        raise RuntimeError(f"upload failed ({status})")
    info = json.loads(raw)["file"]
    while info.get("state") == "PROCESSING":
        time.sleep(3)
        info = json.loads(http("GET", f"{API}/v1beta/{info['name']}", key)[2])
    if info.get("state") != "ACTIVE":
        raise RuntimeError(f"uploaded file ended in state {info.get('state')}")
    return {"file_data": {"mime_type": "video/mp4", "file_uri": info["uri"]}}


def video_part(path, key):
    if path.stat().st_size <= INLINE_LIMIT_BYTES:
        return {"inline_data": {"mime_type": "video/mp4", "data": base64.b64encode(path.read_bytes()).decode()}}
    return upload_file(path, key)


def generate(model, part, prompt, key, fps=None, high_res=False):
    media = dict(part)
    if fps:
        media["videoMetadata"] = {"fps": fps}
    config = {"temperature": 0.1, "maxOutputTokens": 16384, "responseMimeType": "application/json"}
    if high_res:
        config["mediaResolution"] = "MEDIA_RESOLUTION_HIGH"
    body = {"contents": [{"parts": [media, {"text": prompt}]}], "generationConfig": config}
    for attempt in range(3):
        status, _, raw = http("POST", f"{API}/v1beta/{model}:generateContent", key, body=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        if status in (429, 500, 503) and attempt < 2:
            time.sleep(20 * (attempt + 1))
            continue
        break
    if status != 200:
        return {"error": f"http_{status}", "body": raw[:400].decode(errors="replace")}
    data = json.loads(raw)
    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    usage = data.get("usageMetadata", {})
    try:
        return {"result": json.loads(text), "tokens": usage.get("totalTokenCount")}
    except json.JSONDecodeError as error:
        return {"error": "json_parse", "detail": str(error), "raw": text[:1500]}


def slug_for(post):
    tail = re.sub(r"[^A-Za-z0-9_-]", "", (post.get("url") or "").rstrip("/").split("/")[-1])[:20]
    return f"{post['platform']}_{post['handle']}_{tail}"


def download(post, path):
    if path.exists() and path.stat().st_size > 10_000:
        return True
    if not post.get("video_url"):
        # yt-dlp is installed next to this Python by `reel setup`.
        downloader = Path(sys.executable).with_name("yt-dlp")
        downloader = downloader if downloader.exists() else shutil.which("yt-dlp")
        if not (downloader and post.get("url")):
            return False
        subprocess.run([str(downloader), "-q", "--no-warnings", "-f", "mp4", "-o", str(path), post["url"]], check=False, timeout=300)
        return path.exists() and path.stat().st_size > 10_000
    request = urllib.request.Request(post["video_url"], headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            path.write_bytes(response.read())
    except Exception as error:
        print(f"  download failed for {path.name}: {error}")
        return False
    return path.stat().st_size > 10_000


def contact_sheet(video, out):
    """Stills to look at: the first 3 seconds densely, then one frame every 4 seconds."""
    if out.exists():
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    select = "select='lt(t\\,3)*not(mod(n\\,8))+gte(t\\,3)*isnan(prev_selected_t)+gte(t-prev_selected_t\\,4)',scale=270:-2,tile=6x4"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-vf", select, "-frames:v", "1", "-q:v", "4", str(out)],
        check=False,
    )


def watch(post, video, key, force=False):
    out = ANALYSES / f"{video.stem}.json"
    if out.exists() and not force:
        return "skipped"
    part = video_part(video, key)
    transcript = generate(TRANSCRIPT_MODEL, part, TRANSCRIPT_PROMPT, key)
    segments = (transcript.get("result") or {}).get("segments") or []
    spoken = "\n".join(f"[{s.get('start', 0):.1f}] {s.get('text', '')}" for s in segments) or "(no speech detected)"
    context = "\n".join(
        f"- {label}: {post[field]}"
        for label, field in [
            ("Account", "handle"), ("Platform", "platform"), ("Plays", "plays"),
            ("Median plays of this account's recent posts", "account_median_plays"),
            ("Plays relative to that median", "ratio"), ("Likes", "likes"), ("Comments", "comments"),
            ("Caption", "caption"),
        ]
        if post.get(field) not in (None, "")
    ) or "- none (local file)"
    analysis = generate(
        VISUAL_MODEL, part,
        ANALYSIS_PROMPT.format(CREATOR=brief()[:2000], CONTEXT=context[:3000], TRANSCRIPT=spoken[:8000]),
        key, fps=2, high_res=True,
    )
    ANALYSES.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"post": post, "transcript": transcript, "analysis": analysis}, indent=2, ensure_ascii=False))
    contact_sheet(video, FRAMES / f"{video.stem}.jpg")
    return "error" if "error" in analysis else "ok"


def brief():
    file = RESEARCH / "brief.md"
    # Notes to yourself in <!-- comments --> are not sent.
    text = re.sub(r"<!--.*?-->", "", file.read_text(), flags=re.S).strip() if file.exists() else ""
    return text or DEFAULT_BRIEF


def pick(posts, top, group, min_ratio, per_account, max_age_days):
    chosen, seen = [], {}
    for post in posts:
        if group and post.get("group") != group:
            continue
        # Pinned all-time hits come back with the recent posts; formats older than a year
        # say little about what works now.
        if (post.get("ratio") or 0) < min_ratio or not 3 <= (post.get("age_days") or 0) <= max_age_days:
            continue
        key = (post["platform"], post["handle"])
        if seen.get(key, 0) >= per_account:
            continue
        seen[key] = seen.get(key, 0) + 1
        chosen.append(post)
        if len(chosen) >= top:
            break
    return chosen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--group")
    parser.add_argument("--min-ratio", type=float, default=2.0)
    parser.add_argument("--per-account", type=int, default=2)
    parser.add_argument("--max-age-days", type=int, default=365)
    parser.add_argument("--file")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--concurrency", type=int, default=3)
    args = parser.parse_args()
    key = kit.env("GEMINI_API_KEY")

    if args.file:
        video = Path(args.file).resolve()
        print(video.name, watch({"platform": "local", "handle": "own", "url": video.stem}, video, key, args.force))
        return

    if not (RESEARCH / "outliers.json").exists():
        sys.exit("research/outliers.json is missing: run `reel scrape` first")
    posts = pick(json.loads((RESEARCH / "outliers.json").read_text())["posts"], args.top, args.group, args.min_ratio, args.per_account, args.max_age_days)
    VIDEOS.mkdir(parents=True, exist_ok=True)

    def job(post):
        video = VIDEOS / f"{slug_for(post)}.mp4"
        if not download(post, video):
            return video.stem, "no_video"
        try:
            return video.stem, watch(post, video, key, args.force)
        except Exception as error:
            return video.stem, f"failed: {error}"

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for name, status in pool.map(job, posts):
            print(f"{status:10} {name}")


if __name__ == "__main__":
    main()
