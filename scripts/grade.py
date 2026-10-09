#!/usr/bin/env python3
"""Show a recording before and after each colour grade, side by side, to pick one.

Takes three frames spread over the recording and writes one sheet: a row per frame, the
ungraded picture first, then each grade in cut.py's GRADES. Look at skin first (healthy,
not orange), then at whether the darks are still readable and the lights are not blown.

Usage: reel grade RECORDING OUT.jpg [--custom "ffmpeg,filter,chain"]
"""

import argparse
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

import cut
import kit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("out")
    parser.add_argument("--custom")
    args = parser.parse_args()
    grades = {"ungraded": "", **cut.GRADES}
    if args.custom:
        grades["custom"] = args.custom
    length = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", args.source], capture_output=True, text=True).stdout)
    width, rows = 432, []
    with tempfile.TemporaryDirectory() as tmp:
        for share in (0.15, 0.5, 0.85):
            row = []
            for name, chain in grades.items():
                still = Path(tmp) / "still.png"
                filters = (chain + "," if chain else "") + f"scale={width}:-2"
                subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{length * share:.2f}", "-i", args.source, "-map", "0:v:0", "-frames:v", "1", "-vf", filters, str(still)], check=True)
                tile = Image.open(still).convert("RGB")
                ImageDraw.Draw(tile).text((10, 8), name, font=kit.font(26, "Bold"), fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0))
                row.append(tile)
            rows.append(row)
    sheet = Image.new("RGB", (width * len(grades), sum(r[0].height for r in rows)))
    y = 0
    for row in rows:
        for i, tile in enumerate(row):
            sheet.paste(tile, (i * width, y))
        y += row[0].height
    sheet.save(args.out, quality=90)
    print(f"{len(grades)} versions x {len(rows)} frames -> {args.out}")


if __name__ == "__main__":
    main()
