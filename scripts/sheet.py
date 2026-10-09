#!/usr/bin/env python3
"""Put stills of a video on one sheet, to see what is in it without watching it.

Three uses:
  reel sheet VIDEO OUT.jpg                    about 40 stills spread over the whole video
  reel sheet VIDEO OUT.jpg --every 0.5        one still every half second (a dense sheet of a
                                              finished cut, to find glances away and bad frames)
  reel sheet VIDEO OUT.jpg --at 12.5 --grid   one large still with a ruler across it, to read off
                                              "focus", "head_top" and crops as shares of the frame

Options: --from S --to S (only this stretch), --columns N, --width PIXELS (of each still)

Each still is labelled with its time in seconds.
"""

import argparse
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

import kit


def duration(file):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(file)], capture_output=True, text=True).stdout.strip()
    if not out:
        raise SystemExit(f"cannot read {file}")
    return float(out)


def still(file, at, width, folder):
    target = Path(folder) / f"{at:010.3f}.jpg"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{at:.3f}", "-i", str(file), "-map", "0:v:0", "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "3", str(target)])
    return Image.open(target).convert("RGB") if target.exists() else None


def label(image, text, size):
    ImageDraw.Draw(image).text((6, 4), text, font=kit.font(size, "Bold"), fill=(255, 255, 255), stroke_width=max(2, size // 8), stroke_fill=(0, 0, 0))


def ruler(image):
    """A line every tenth of the way across and down, numbered, for reading positions off."""
    draw = ImageDraw.Draw(image)
    size = max(14, image.width // 45)
    for tenth in range(1, 10):
        x, y = image.width * tenth // 10, image.height * tenth // 10
        draw.line([x, 0, x, image.height], fill=(255, 235, 60), width=1)
        draw.line([0, y, image.width, y], fill=(255, 235, 60), width=1)
        draw.text((x + 4, image.height - size - 6), f"{tenth / 10:.1f}", font=kit.font(size, "Bold"), fill=(255, 235, 60), stroke_width=2, stroke_fill=(0, 0, 0))
        draw.text((4, y + 2), f"{tenth / 10:.1f}", font=kit.font(size, "Bold"), fill=(255, 235, 60), stroke_width=2, stroke_fill=(0, 0, 0))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video")
    parser.add_argument("out")
    parser.add_argument("--every", type=float, help="seconds between stills")
    parser.add_argument("--at", type=float, action="append", help="a still at exactly this second; can be given more than once")
    parser.add_argument("--from", dest="start", type=float, default=0.0)
    parser.add_argument("--to", dest="end", type=float)
    parser.add_argument("--columns", type=int)
    parser.add_argument("--width", type=int)
    parser.add_argument("--grid", action="store_true")
    args = parser.parse_args()

    end = args.end if args.end is not None else duration(args.video)
    if args.at:
        times = args.at
    else:
        every = args.every or max((end - args.start) / 40, 0.2)
        times = [args.start + every * i for i in range(int((end - args.start) / every) + 1) if args.start + every * i < end]
    width = args.width or (1080 if args.at and len(times) <= 2 else 216)
    with tempfile.TemporaryDirectory() as folder:
        stills = []
        for at in times:
            image = still(args.video, at, width, folder)
            if image is None:
                continue
            if args.grid:
                ruler(image)
            label(image, f"{at:.1f}s" if not float(at).is_integer() else f"{at:.0f}s", min(max(14, width // 12), 40))
            stills.append(image)
    if not stills:
        raise SystemExit("no stills could be taken")
    columns = args.columns or min(len(stills), 10)
    rows = -(-len(stills) // columns)
    tile_w, tile_h = stills[0].size
    sheet = Image.new("RGB", (columns * tile_w, rows * tile_h), (24, 24, 28))
    for index, image in enumerate(stills):
        sheet.paste(image, (index % columns * tile_w, index // columns * tile_h))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.out, quality=88)
    print(f"{len(stills)} stills, {columns} across, {sheet.width}x{sheet.height} -> {args.out}")


if __name__ == "__main__":
    main()
