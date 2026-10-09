#!/usr/bin/env python3
"""Check that everything the kit needs is there, and say what to do about what is not.

Reports on ffmpeg, the Python environment and its packages, a browser for screenshots, the
kit's font and sounds, the project in the current folder, and whether the keys for the
research commands are set (never their values).

Usage: reel doctor
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("REEL_KIT_HOME") or Path.home() / ".reel-kit").expanduser()
PACKAGES = {"faster_whisper": "transcription", "numpy": "audio analysis", "PIL": "graphics", "playwright": "screenshots", "yt_dlp": "research downloads"}
CHROME = ["/Applications/Google Chrome.app", "google-chrome", "google-chrome-stable", "chrome"]

rows, failed = [], False


def row(mark, what, note=""):
    global failed
    failed = failed or mark == "missing"
    rows.append((mark, what, note))


def key_set(name, project):
    if os.environ.get(name):
        return True
    env = project / ".env"
    return env.exists() and any(line.strip().startswith(f"{name}=") and line.split("=", 1)[1].strip() for line in env.read_text().splitlines())


def main():
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()

    for tool in ("ffmpeg", "ffprobe"):
        found = shutil.which(tool)
        version = subprocess.run([tool, "-version"], capture_output=True, text=True).stdout.split("\n")[0].split(" Copyright")[0] if found else ""
        row("ok" if found else "missing", tool, version or "install ffmpeg (macOS: brew install ffmpeg, Debian/Ubuntu: sudo apt install ffmpeg)")

    python = HOME / "venv" / "bin" / "python"
    if not python.exists():
        row("missing", "Python environment", "run: reel setup")
    else:
        check = "import importlib.util, json, sys; print(json.dumps({n: bool(importlib.util.find_spec(n)) for n in sys.argv[1:]}))"
        out = subprocess.run([str(python), "-c", check, *PACKAGES], capture_output=True, text=True).stdout
        have = json.loads(out) if out.strip() else {}
        row("ok", "Python environment", str(HOME / "venv"))
        for name, use in PACKAGES.items():
            row("ok" if have.get(name) else "missing", f"  {name}", use if have.get(name) else f"needed for {use}; run: reel setup")
        chrome = any(Path(c).exists() if c.startswith("/") else shutil.which(c) for c in CHROME)
        cache = [Path.home() / "Library/Caches/ms-playwright", Path.home() / ".cache/ms-playwright"]
        chromium = any(folder.exists() and any(folder.glob("chromium*")) for folder in cache)
        row("ok" if chrome or chromium else "optional", "browser for screenshots",
            "Google Chrome" if chrome else "downloaded Chromium" if chromium else "none: `reel shots` will not work until you install Chrome or run: reel setup")
        models = Path(os.environ.get("HF_HOME") or Path.home() / ".cache/huggingface") / "hub"
        cached = models.exists() and any(models.glob("models--*faster-whisper-large-v3-turbo*"))
        row("ok" if cached else "optional", "transcription model", "downloaded" if cached else "downloads on the first `reel analyze` (about 1.6 GB)")

    row("ok" if (KIT / "assets/fonts/InterVariable.ttf").exists() else "missing", "font", "assets/fonts/InterVariable.ttf")
    sounds = [name for name in ("pop", "pop-small", "whoosh", "tick") if (KIT / "assets/sfx" / f"{name}.wav").exists()]
    row("ok" if len(sounds) == 4 else "missing", "sounds", f"{len(sounds)} of 4 in assets/sfx" + ("" if len(sounds) == 4 else "; run: reel make-sfx"))

    project = next((folder for folder in [Path.cwd(), *Path.cwd().parents] if (folder / "reel.json").exists()), None)
    row("ok" if project else "optional", "project", str(project) if project else "no reel.json here or above; make a project with: reel init")
    for name, use in (("APIFY_TOKEN", "reel scrape"), ("GEMINI_API_KEY", "reel watch")):
        there = key_set(name, project or Path.cwd())
        row("ok" if there else "optional", f"  {name}", "set" if there else f"not set; only needed for `{use}`")

    width = max(len(what) for _, what, _ in rows)
    for mark, what, note in rows:
        print(f"{mark:9}{what:{width}}  {note}")
    print()
    print("Something needed is missing, see above." if failed else "Ready.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
