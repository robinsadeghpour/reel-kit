#!/usr/bin/env python3
"""Install what the kit needs, once per machine.

Makes a Python environment in ~/.reel-kit/venv (REEL_KIT_HOME moves it), installs the
packages in requirements.txt into it, and makes sure there is a browser for screenshots:
your own Google Chrome if you have one, otherwise a downloaded Chromium.

ffmpeg is not installed for you. Get it from your package manager first
(macOS: brew install ffmpeg, Debian/Ubuntu: sudo apt install ffmpeg).

The transcription model (about 1.6 GB) downloads the first time `reel analyze` runs.
--model fetches it now instead.

Usage: reel setup [--no-browser] [--model]
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("REEL_KIT_HOME") or Path.home() / ".reel-kit").expanduser()
CHROME = ["/Applications/Google Chrome.app", "google-chrome", "google-chrome-stable", "chrome"]


def has_chrome():
    return any(Path(c).exists() if c.startswith("/") else shutil.which(c) for c in CHROME)


def run(cmd, what):
    print(f"-> {what}", flush=True)
    if subprocess.run([str(c) for c in cmd]).returncode != 0:
        sys.exit(f"failed: {what}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-browser", action="store_true", help="skip the browser; `reel shots` will need Google Chrome")
    parser.add_argument("--model", action="store_true", help="download the transcription model now")
    args = parser.parse_args()

    if sys.version_info < (3, 10):
        sys.exit(f"Python 3.10 or newer is needed, this is {sys.version.split()[0]}. Set REEL_PYTHON to a newer one.")
    missing = [tool for tool in ("ffmpeg", "ffprobe") if not shutil.which(tool)]
    if missing:
        sys.exit(f"{' and '.join(missing)} not found. Install ffmpeg first (macOS: brew install ffmpeg, Debian/Ubuntu: sudo apt install ffmpeg), then run this again.")

    python = HOME / "venv" / "bin" / "python"
    if not python.exists():
        HOME.mkdir(parents=True, exist_ok=True)
        run([sys.executable, "-m", "venv", HOME / "venv"], f"making a Python environment in {HOME / 'venv'}")
    run([python, "-m", "pip", "install", "--quiet", "--upgrade", "pip"], "updating pip")
    run([python, "-m", "pip", "install", "--quiet", "-r", KIT / "requirements.txt"], "installing packages (a few minutes the first time)")

    if args.no_browser:
        print("-> skipping the browser", flush=True)
    elif has_chrome():
        print("-> Google Chrome found, using it for screenshots", flush=True)
    else:
        run([python, "-m", "playwright", "install", "chromium"], "no Google Chrome here, downloading Chromium for screenshots")

    if args.model:
        run([python, "-c", "from faster_whisper import WhisperModel; WhisperModel('large-v3-turbo', device='cpu', compute_type='int8')"], "downloading the transcription model (about 1.6 GB)")

    print(flush=True)
    sys.exit(subprocess.run([sys.executable, str(KIT / "scripts" / "doctor.py")]).returncode)


if __name__ == "__main__":
    main()
