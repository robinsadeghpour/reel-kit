#!/usr/bin/env python3
"""Make a project folder for your videos. Never overwrites a file that is already there.

  footage/<name>/     your raw files for one video
  out/<name>/         the edit of that video: plan.json, the ledger, the renders
  reel.json           the project's standing settings (language, colours, loudness)
  STYLE.md            how you want your videos, in words; the editing skill reads and keeps it
  research/           seed accounts and what the research commands find
  .env.example        the keys the research commands need
  .gitignore          keeps footage, renders and keys out of git

Usage: reel init [FOLDER] [--language en] [--locale en-US]
"""

import argparse
import json
import shutil
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", nargs="?", default=".")
    parser.add_argument("--language", help="the language you speak in your videos, as a two-letter code")
    parser.add_argument("--locale", help="the language web pages are asked for when taking screenshots, e.g. de-DE")
    args = parser.parse_args()
    root = Path(args.folder).expanduser().resolve()
    for folder in ("footage", "out", "research"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    for source in sorted(TEMPLATES.rglob("*")):
        if source.is_dir():
            continue
        relative = source.relative_to(TEMPLATES)
        # Dotfiles are stored without their dot so they are not mistaken for the kit's own.
        target = root / relative.parent / ("." + relative.name[4:] if relative.name.startswith("dot-") else relative.name)
        if target.exists():
            print(f"kept     {target.relative_to(root)}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        print(f"created  {target.relative_to(root)}")
    if args.language or args.locale:
        file = root / "reel.json"
        settings = json.loads(file.read_text())
        settings.update({key: value for key, value in (("language", args.language), ("locale", args.locale)) if value})
        file.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    print(f"\nProject ready in {root}. Put a recording in footage/<name>/ and ask for an edit.")


if __name__ == "__main__":
    main()
