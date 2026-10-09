#!/usr/bin/env python3
"""Measure how each downloaded reference video is made: length and number of hard cuts.

Cuts per minute is a cheap, local stand-in for "how much editing does this need".
Also writes a six-frame strip per video under research/strips/ for looking at by eye.
Works on whatever `reel watch` has downloaded to research/videos/, and costs nothing.

Usage: reel shape
"""

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor

import kit

ROOT = kit.find_project()
VIDEOS = ROOT / "research" / "videos"
STRIPS = ROOT / "research" / "strips"
OUT = ROOT / "research" / "shape.json"
SCENE_THRESHOLD = 0.3


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip()
    return float(out) if out else 0.0


def measure(path):
    seconds = duration(path)
    if not seconds:
        return path.stem, None
    log = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-an", "-vf", f"scale=160:-2,select='gt(scene,{SCENE_THRESHOLD})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    cuts = len(re.findall(r"pts_time:", log))
    strip = STRIPS / f"{path.stem}.jpg"
    if not strip.exists():
        step = max(seconds / 6, 0.1)
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-i", str(path), "-vf", f"fps=1/{step:.3f},scale=150:266:force_original_aspect_ratio=increase,crop=150:266,tile=6x1", "-frames:v", "1", "-q:v", "5", str(strip)],
            check=False,
        )
    return path.stem, {"seconds": round(seconds, 1), "cuts": cuts, "cuts_per_minute": round(cuts / seconds * 60, 1)}


def main():
    STRIPS.mkdir(parents=True, exist_ok=True)
    paths = sorted(VIDEOS.glob("*.mp4"))
    with ThreadPoolExecutor(max_workers=6) as pool:
        shape = {key: value for key, value in pool.map(measure, paths) if value}
    OUT.write_text(json.dumps(shape, indent=1))
    print(len(shape), "videos measured")


if __name__ == "__main__":
    main()
