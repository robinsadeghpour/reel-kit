#!/usr/bin/env python3
"""Shared by the other scripts: where the project is, how a plan is read, fonts, language.

The kit (these scripts, the font, the sounds) and the project (footage, plans, renders)
live in different places. Paths inside a plan are relative to the project root, which is
the nearest folder at or above the plan that holds a reel.json, or else the folder the
command is run from. REEL_PROJECT overrides both.

reel.json holds a project's standing settings (language, colours, loudness). A plan can
set any of them again for one video.

Not run on its own.
"""

import functools
import json
import os
import re
import subprocess
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
ROOT = Path.cwd().resolve()

# Settings a plan inherits from reel.json when it does not set them itself.
INHERITED = ("language", "locale", "captions", "caption_y", "theme", "font", "loudness", "sfx", "sfx_volume", "thousands", "fillers", "whisper_model")

# Hesitation sounds, per language. They are matched against a whole word with its
# punctuation removed. Kept apart by language because one language's filler is another's
# word: "um" is a preposition in German, "er" is a pronoun.
HESITATIONS = {
    "de": r"ä+h*m*|e+h+m*|h+m+|m+h*m*|ö+h*m*|uh+m*",
    "en": r"u+h+m*|u+m+|e+r+m*|e+h+m*|h+m+|m+h*m+",
    None: r"ä+h*m*|e+h+m*|h+m+|m+h*m*|ö+h*m*|u+h+m*",
}
# Small words that make a phrase a filler when it consists of nothing else.
SMALL_WORDS = {"de": r"ja+|ne+|so+|okay|ok", "en": r"so+|okay|ok|yeah|right|well|like", None: r"okay|ok"}
# Given to the transcriber so it writes hesitations down instead of leaving them out.
PROMPTS = {"de": "Ähm, äh, also, ähm, hm, ja, äh, genau, ähm, so, äh.", "en": "Um, uh, so, um, hm, yeah, uh, like, um."}
# Which character groups the digits of a large number.
THOUSANDS = {**dict.fromkeys(("de", "es", "it", "pt", "nl", "da", "tr", "id"), "."), **dict.fromkeys(("fr", "sv", "nb", "fi", "cs", "pl", "ru"), " ")}

WEIGHTS = {"Regular": 400, "Medium": 500, "Semibold": 600, "Bold": 700, "Heavy": 800, "Black": 900}
FONT_FILE = KIT / "assets" / "fonts" / "InterVariable.ttf"


def find_project(start=None):
    """Work out the project root and remember it."""
    global ROOT
    if os.environ.get("REEL_PROJECT"):
        ROOT = Path(os.environ["REEL_PROJECT"]).expanduser().resolve()
        return ROOT
    here = Path(start or Path.cwd()).resolve()
    for folder in [here, *here.parents]:
        if (folder / "reel.json").exists():
            ROOT = folder
            return ROOT
    ROOT = Path.cwd().resolve()
    return ROOT


def path(value):
    """A path from a plan: absolute as it is, anything else from the project root."""
    value = Path(value).expanduser()
    return value if value.is_absolute() else ROOT / value


def settings():
    file = ROOT / "reel.json"
    if not file.exists():
        return {}
    try:
        return json.loads(file.read_text())
    except json.JSONDecodeError as error:
        raise SystemExit(f"{file} is not valid JSON: {error}")


def env(name, required=True):
    """A key from the environment, or from the project's .env file."""
    if os.environ.get(name):
        return os.environ[name]
    file = ROOT / ".env"
    if file.exists():
        for line in file.read_text().splitlines():
            if line.strip().startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("'\"")
    if required:
        raise SystemExit(f"{name} is not set. Put it in {file} or in the environment.")
    return None


def probe(file):
    """Width and height of a video as it is shown, after any rotation the camera recorded."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:stream_side_data=rotation:stream_tags=rotate",
                          "-of", "json", str(file)], capture_output=True, text=True).stdout
    streams = (json.loads(out) if out.strip() else {}).get("streams") or []
    if not streams:
        raise SystemExit(f"no picture found in {file}")
    stream = streams[0]
    turn = next((d["rotation"] for d in stream.get("side_data_list", []) if "rotation" in d), (stream.get("tags") or {}).get("rotate", 0))
    width, height = stream["width"], stream["height"]
    return (height, width) if abs(int(float(turn))) % 180 == 90 else (width, height)


def window(main):
    """The largest upright 9:16 piece of the recording: (width, height). Zoom 1.0 shows all of it."""
    width, height = main["width"], main["height"]
    if width * 16 > height * 9:
        return height * 9 / 16, height
    return width, width * 16 / 9


def read_plan(plan_path):
    """The plan exactly as written, for a script that writes it back."""
    plan_path = Path(plan_path).resolve()
    if not plan_path.exists():
        raise SystemExit(f"no plan at {plan_path}")
    find_project(plan_path.parent)
    try:
        return plan_path, json.loads(plan_path.read_text())
    except json.JSONDecodeError as error:
        raise SystemExit(f"{plan_path} is not valid JSON: {error}")


def load_plan(plan_path):
    """The plan ready to use: project settings filled in, looks applied, sizes measured."""
    plan_path, plan = read_plan(plan_path)
    defaults = settings()
    for key in INHERITED:
        if key in defaults and key not in plan:
            plan[key] = defaults[key]
    if not plan.get("language"):
        ledger = plan_path.parent / "analysis" / "ledger.json"
        plan["language"] = (json.loads(ledger.read_text()).get("language") if ledger.exists() else None) or "en"
    main = plan["main"]
    if not path(main["file"]).exists():
        raise SystemExit(f"{main['file']} not found under {ROOT}. Paths in a plan start at the project root: run from there, or put a reel.json in it.")
    if "width" not in main or "height" not in main:
        main["width"], main["height"] = probe(path(main["file"]))
    main.setdefault("focus", [0.5, 0.5])
    # A segment can name a look ("tight", "card") instead of repeating zoom and focus.
    plan["segments"] = [{**plan.get("looks", {}).get(seg.get("look"), {}), **seg} for seg in plan["segments"]]
    # A clip's crop is [x, y, width, height], like everywhere else in a plan; ffmpeg wants it the other way round.
    for clip in plan.get("clips", {}).values():
        if isinstance(clip.get("crop"), (list, tuple)):
            x, y, w, h = clip["crop"]
            clip["crop"] = f"{w}:{h}:{x}:{y}"
    if plan.get("font"):
        set_font(plan["font"])
    return plan_path, plan


def set_font(file):
    global FONT_FILE
    FONT_FILE = path(file)
    if not FONT_FILE.exists():
        raise SystemExit(f"font {FONT_FILE} not found")


@functools.lru_cache(maxsize=512)
def _font(file, size, weight):
    from PIL import ImageFont

    face = ImageFont.truetype(file, size)
    try:
        axes = face.get_variation_axes()
    except (OSError, NotImplementedError):
        return face  # one fixed weight: use it as it is
    values = []
    for axis in axes:
        name = axis["name"].decode() if isinstance(axis["name"], bytes) else axis["name"]
        wanted = WEIGHTS.get(weight, 700) if "weight" in name.lower() else size if "optical" in name.lower() else axis["default"]
        values.append(min(max(wanted, axis["minimum"]), axis["maximum"]))
    face.set_variation_by_axes(values)
    return face


def font(size, weight="Bold"):
    """The kit's typeface at a size and weight. Any font with a weight axis works; see "font" in reel.json."""
    return _font(str(FONT_FILE), size, weight)


def norm(word):
    """A word reduced to its letters and digits, for comparing."""
    return "".join(ch for ch in word.lower() if ch.isalnum())


def fillers(language, extra=None):
    """What counts as a hesitation in this language: (sound pattern, filler-phrase pattern, transcriber prompt).

    "fillers" in reel.json adds to it: {"sounds": ["eeh"], "words": ["basically"], "prompt": "..."}.
    """
    extra = extra or {}
    sounds = "|".join([HESITATIONS.get(language, HESITATIONS[None])] + [re.escape(norm(s)) for s in extra.get("sounds", [])])
    small = "|".join([sounds, SMALL_WORDS.get(language, SMALL_WORDS[None])] + [re.escape(norm(w)) for w in extra.get("words", [])])
    return re.compile(f"^({sounds})$", re.I), re.compile(f"^({small})$", re.I), extra.get("prompt") or PROMPTS.get(language)


def thousands(plan):
    return plan.get("thousands") or THOUSANDS.get((plan.get("language") or "en")[:2], ",")
