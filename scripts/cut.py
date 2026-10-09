#!/usr/bin/env python3
"""Render a talking-head video from a plan: chosen takes, layouts, cutaways, zoom cuts.

The plan (JSON) lists segments of the main recording in the order they should play. Each
segment has a layout:
  talk   the speaker full frame, at a zoom level
  panel  the speaker with a cropped clip of a second source in a box above them
  full   the second source filling the frame
  backdrop  the second source blurred and darkened, as a stage for a card drawn by graphics.py

and a sound source: the speaker's voice (default) or the clip's own sound ("sound": "clip").
The two never play together.

Picture and sound are built separately. The picture is one file per segment, joined. The
sound is cut in a single pass, so two segments that follow each other in the recording
(a zoom cut in the middle of a sentence) have no audio edit between them at all.

The speaker fills an upright 9:16 frame: the largest such piece of the recording, placed by
"focus". A recording that is already 9:16 is used whole; a wide one is cropped to the speaker.

"grade" in the plan names a colour grade for the speaker's footage (see GRADES). Clips and
graphics are not graded.

Graphics (cards, number stickers, big image cards) are drawn by graphics.py and laid over
the joined picture; their sound effects are mixed in quietly under the voice.

Captions are optional ("captions": true) and are timed from the finished audio.

Usage: reel cut out/<name>/plan.json [--graphics-only]

--graphics-only reuses the cut picture from the last run and redoes only the graphics and the
sound. Use it when only the "graphics" list changed; it is several times faster.
"""

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

import graphics
import kit

W, H, FPS = 1080, 1920, 30

# Level the voice before anything else: the raw recording has peaks far above its average,
# and normalising that directly is what made the earlier export sound overdriven.
VOICE_CHAIN = "highpass=f=80,acompressor=threshold=0.07:ratio=3:attack=6:release=160:makeup=2.5,alimiter=limit=0.7:attack=4:release=80:level=disabled"
FADE_IN, FADE_OUT = 0.045, 0.07

# Colour grades for the speaker's footage, chosen by "grade" in the plan. Each is an ffmpeg
# filter chain. Off unless a plan asks. "warm" was tuned on one room (cool screen light, a
# purple wall): a little more exposure and contrast, livelier colour without pushing skin,
# warmer skin tones, a soft vignette, light sharpening. "soft" is the same idea at half
# strength and without the vignette. Treat both as starting points for your own footage and
# compare them on a sheet first (`reel grade`).
GRADES = {
    "warm": ("exposure=exposure=0.08,curves=master='0/0 0.25/0.225 0.5/0.525 0.75/0.80 1/1',vibrance=intensity=0.2,"
             "colorbalance=rm=0.035:bm=-0.03:rh=0.02:bh=-0.02,vignette=angle=PI/6,cas=0.25"),
    "soft": "curves=master='0/0 0.25/0.235 0.5/0.515 0.75/0.785 1/1',vibrance=intensity=0.12,colorbalance=rm=0.02:bm=-0.02,cas=0.2",
}


def grade_filter(plan):
    grade = plan.get("grade")
    return (GRADES.get(grade, grade) + ",") if grade else ""


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"ffmpeg failed:\n{' '.join(map(str, cmd))[:900]}\n{result.stderr[-1500:]}")


def frame(t):
    return round(t * FPS) / FPS


def speaker_filter(zoom, main, focus=None, grade="", zoom_to=None, frames=0):
    focus = focus or main["focus"]
    # Zoom 1.0 shows the largest upright 9:16 piece of the recording; the focus places it.
    base_w, base_h = (int(side) // 2 * 2 for side in kit.window(main))
    if zoom_to and abs(zoom_to - zoom) > 1e-4 and frames > 1:
        # A slow push: the zoom moves evenly from one level to the other over the segment.
        # Drawn on a doubled picture so the window moves in steps too small to see.
        level = f"{zoom}+({zoom_to - zoom:.5f})*on/{frames - 1}"
        stage = ""
        if (base_w, base_h) != (main["width"], main["height"]):
            stage = f"crop={base_w}:{base_h}:{int((main['width'] - base_w) * focus[0]) // 2 * 2}:{int((main['height'] - base_h) * focus[1]) // 2 * 2},"
        return (f"{stage}fps={FPS},scale=iw*2:ih*2:flags=bicubic,format=yuv444p,"
                f"zoompan=z='{level}':x='(iw-iw/zoom)*{focus[0]}':y='(ih-ih/zoom)*{focus[1]}':d=1:s={W}x{H}:fps={FPS},"
                f"{grade}setsar=1,format=yuv420p")
    crop_w, crop_h = int(base_w / zoom) // 2 * 2, int(base_h / zoom) // 2 * 2
    x = int((main["width"] - crop_w) * focus[0]) // 2 * 2
    y = int((main["height"] - crop_h) * focus[1]) // 2 * 2
    return f"crop={crop_w}:{crop_h}:{x}:{y},scale={W}:{H},{grade}setsar=1,fps={FPS},format=yuv420p"


def render_picture(plan, seg, index, work):
    out = work / f"seg-{index:02d}.mp4"
    duration = round(seg["out"] - seg["in"], 4)
    main = plan["main"]
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{seg['in']:.4f}", "-t", f"{duration + 0.2:.4f}", "-i", str(kit.path(main["file"]))]
    speaker = speaker_filter(seg.get("zoom", 1.0), main, seg.get("focus"), grade_filter(plan), seg.get("zoom_to"), round(duration * FPS))
    inputs = 1
    if seg["layout"] == "talk":
        graph = f"[0:v:0]{speaker}[pic]"
    else:
        clip = plan["clips"][seg["clip"]]
        if Path(clip["file"]).suffix.lower() in (".png", ".jpg", ".jpeg"):
            # A still image stands in for a clip: held for the length of the segment.
            cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{duration + 0.2:.4f}", "-i", str(kit.path(clip["file"]))]
        else:
            cmd += ["-ss", f"{seg['clip_in']:.4f}", "-t", f"{duration + 0.2:.4f}", "-i", str(kit.path(clip["file"]))]
        inputs = 2
        crop = f"crop={clip['crop']}," if clip.get("crop") else ""
        if seg["layout"] == "backdrop":
            # Only the blurred, darkened clip: the clip itself is drawn on top as a card by graphics.py.
            graph = f"[1:v]{crop}fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=36,eq=brightness=-0.32:saturation=1.15,setsar=1,format=yuv420p[pic]"
        elif seg["layout"] == "panel":
            box = seg["box"]
            graph = (f"[0:v:0]{speaker}[base];[1:v]{crop}scale={box['width']}:-2,fps={FPS},pad=iw+10:ih+10:5:5:white[p];"
                     f"[base][p]overlay={(W - box['width'] - 10) // 2}:{box['y']}[pic]")
        else:
            graph = (f"[1:v]{crop}fps={FPS},split[a1][b1];"
                     f"[a1]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=28,eq=brightness=-0.28[bg];"
                     f"[b1]scale={W}:-2[fg];[bg][fg]overlay=0:{seg.get('y', 470)},setsar=1,format=yuv420p[pic]")
    if seg.get("sticker"):
        # A small graphic laid over the picture for the length of the segment.
        sticker = seg["sticker"]
        cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{duration + 0.2:.4f}", "-i", str(kit.path(sticker["file"]))]
        graph += f";[pic][{inputs}:v]overlay=(W-w)/2:{sticker['y']},format=yuv420p[v]"
    else:
        graph += ";[pic]null[v]"
    frames = round(duration * FPS)
    cmd += ["-filter_complex", graph, "-map", "[v]", "-an", "-frames:v", str(frames),
            "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)]
    run(cmd)
    return out, frames / FPS


def audio_spans(plan):
    """Merge segments that follow each other in the same recording into one uncut span."""
    spans = []
    for seg in plan["segments"]:
        clip_sound = seg.get("sound") == "clip"
        source = seg["clip"] if clip_sound else "main"
        start = seg["clip_in"] if clip_sound else seg["in"]
        length = seg["out"] - seg["in"]
        if spans and spans[-1]["source"] == source and abs(spans[-1]["start"] + spans[-1]["length"] - start) < 0.001:
            spans[-1]["length"] += length
            spans[-1]["fade_out"] = seg.get("fade_out", FADE_OUT)
        else:
            spans.append({"source": source, "start": start, "length": length, "volume": seg.get("clip_volume", 1.0),
                          "fade_in": seg.get("fade_in", FADE_IN), "fade_out": seg.get("fade_out", FADE_OUT)})
    return spans


def render_sound(plan, work, effects=()):
    spans = audio_spans(plan)
    sources = ["main"] + sorted({s["source"] for s in spans if s["source"] != "main"})
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", str(kit.path(plan["main"]["file"]))]
    for name in sources[1:]:
        cmd += ["-i", str(kit.path(plan["clips"][name]["file"]))]
    graph = []
    for number, span in enumerate(spans):
        end = span["start"] + span["length"]
        chain = VOICE_CHAIN if span["source"] == "main" else f"volume={span['volume']}"
        graph.append(f"[{sources.index(span['source'])}:a:0]atrim=start={span['start']:.4f}:end={end:.4f},asetpts=PTS-STARTPTS,aresample=48000,"
                     f"aformat=channel_layouts=stereo,{chain},afade=t=in:d={span['fade_in']},afade=t=out:st={max(span['length'] - span['fade_out'], 0):.4f}:d={span['fade_out']}[a{number}]")
    graph.append("".join(f"[a{n}]" for n in range(len(spans))) + f"concat=n={len(spans)}:v=0:a=1[out]")
    levelled = work / "voice-levelled.wav"
    run(cmd + ["-filter_complex", ";".join(graph), "-map", "[out]", "-ar", "48000", "-c:a", "pcm_s16le", str(levelled)])
    # Bring it to the target loudness (-15 LUFS unless the plan says otherwise) with one fixed
    # gain. The loudness filter's own automatic mode turns quiet moments up, which makes the
    # breaths between sentences louder than they were.
    log = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(levelled), "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
    measured = float(log[log.rfind("Summary"):].split("I:")[1].split("LUFS")[0])
    voice = work / "voice.wav"
    run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(levelled), "-af", f"volume={plan.get('loudness', -15.0) - measured:.2f}dB,alimiter=limit=0.75:level=disabled",
         "-ar", "48000", "-c:a", "pcm_s16le", str(voice)])
    sound = work / "sound.wav"
    if not effects:
        run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(voice), "-c", "copy", str(sound)])
        return sound, len(spans)
    # Effects sit under the voice: added after the voice has been levelled, so they do not pump it.
    cmd, graph = ["ffmpeg", "-loglevel", "error", "-y", "-i", str(voice)], []
    for number, effect in enumerate(effects, start=1):
        cmd += ["-i", str(kit.path(effect["file"]))]
        graph.append(f"[{number}:a]aresample=48000,aformat=channel_layouts=stereo,asetrate={round(48000 * effect['pitch'])},aresample=48000,"
                     f"volume={effect['gain']},adelay={round(effect['at'] * 1000)}:all=1[e{number}]")
    graph.append("[0:a]" + "".join(f"[e{n}]" for n in range(1, len(effects) + 1)) +
                 f"amix=inputs={len(effects) + 1}:normalize=0:duration=first,alimiter=limit=0.75:level=disabled[out]")
    run(cmd + ["-filter_complex", ";".join(graph), "-map", "[out]", "-ar", "48000", "-c:a", "pcm_s16le", str(sound)])
    return sound, len(spans)


def merge_tokens(words):
    """The transcriber splits compounds and decimals ("KI", "-Modell", "5", ".5"); glue them back."""
    merged = []
    for word in words:
        if merged and word["w"][:1] in "-.,":
            merged[-1] = {**merged[-1], "w": merged[-1]["w"] + word["w"], "e": word["e"]}
        else:
            merged.append(dict(word))
    return merged


def apply_phrases(words, phrases):
    """Correct misheard runs of words, spreading the original timing over the replacement."""
    for wrong, right in phrases.items():
        source, target = wrong.split(), right.split()
        i = 0
        while i <= len(words) - len(source):
            if [w["w"] for w in words[i:i + len(source)]] == source:
                start, end = words[i]["s"], words[i + len(source) - 1]["e"]
                step = (end - start) / len(target)
                words[i:i + len(source)] = [{"w": t, "s": round(start + k * step, 2), "e": round(start + (k + 1) * step, 2)} for k, t in enumerate(target)]
            i += 1
    return words


def chunks(words, max_words=3, max_chars=18, max_gap=0.45):
    group = []
    for word in words:
        text = " ".join(w["w"] for w in group + [word])
        if group and (len(group) >= max_words or len(text) > max_chars or word["s"] - group[-1]["e"] > max_gap or group[-1]["w"][-1] in ".?!,"):
            yield group
            group = []
        group.append(word)
    if group:
        yield group


def caption_image(text, path):
    image = Image.new("RGBA", (W, 200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    # Long lines shrink until they fit inside the frame with a margin.
    for size in range(92, 47, -4):
        font = kit.font(size, "Black")
        box = draw.textbbox((0, 0), text, font=font, stroke_width=9)
        if box[2] - box[0] <= W - 90:
            break
    x = (W - (box[2] - box[0])) // 2 - box[0]
    y = (200 - (box[3] - box[1])) // 2 - box[1]
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255), stroke_width=9, stroke_fill=(0, 0, 0, 255))
    image.save(path)


def caption_overlays(plan, work, timeline, mixed):
    words_path = work / "joined-words.json"
    subprocess.run([sys.executable, str(Path(__file__).with_name("words.py")), str(mixed), str(words_path), "--language", plan["language"]], check=True, capture_output=True)
    words = merge_tokens([w for row in json.loads(words_path.read_text()) for w in row["words"]])
    fixes = plan.get("spelling", {})
    for word in words:
        bare = word["w"].strip(".,!?")
        if bare in fixes:
            word["w"] = word["w"].replace(bare, fixes[bare])
    words = apply_phrases(words, plan.get("phrases", {}))
    # A clip's own sound is not captioned: it may be in another language, and it is not the speaker.
    foreign = [t for t in timeline if t["sound"] == "clip"]
    words = [w for w in words if not any(t["start"] - 0.05 <= w["s"] < t["end"] - 0.05 for t in foreign)]

    caption_dir = work / "captions"
    caption_dir.mkdir(exist_ok=True)
    for old in caption_dir.glob("*.png"):
        old.unlink()
    overlays = []
    for number, group in enumerate(chunks(words)):
        start = group[0]["s"]
        y = next((t["caption_y"] for t in timeline if t["start"] <= start + 0.05 < t["end"]), plan.get("caption_y", {}).get("talk", 1250))
        image = caption_dir / f"{number:03d}.png"
        caption_image(" ".join(w["w"] for w in group).strip(), image)
        overlays.append({"file": str(image), "start": round(start, 2), "end": round(max(group[-1]["e"], start + 0.25), 2), "y": y})
    for current, following in zip(overlays, overlays[1:]):
        if following["start"] - current["end"] < 0.35:
            current["end"] = following["start"]
    return overlays


def main():
    plan_path, plan = kit.load_plan(sys.argv[1])
    work = plan_path.parent / "work"
    work.mkdir(parents=True, exist_ok=True)
    # Everything sits on the frame grid, so picture and sound stay the same length.
    for seg in plan["segments"]:
        length = frame(seg["out"] - seg["in"])
        seg["in"] = frame(seg["in"])
        seg["out"] = round(seg["in"] + length, 4)

    picture = work / "picture.mp4"
    # --graphics-only: keep the cut picture from the last run and redo only overlays and sound.
    reuse = "--graphics-only" in sys.argv and (work / "plain.mp4").exists() and (work / "timeline.json").exists()
    if reuse:
        timeline = json.loads((work / "timeline.json").read_text())
        clock = timeline[-1]["end"]
        (work / "plain.mp4").replace(picture)
    else:
        timeline, clock, listing = [], 0.0, []
        for index, seg in enumerate(plan["segments"]):
            path, length = render_picture(plan, seg, index, work)
            timeline.append({"start": round(clock, 3), "end": round(clock + length, 3), "layout": seg["layout"], "zoom": seg.get("zoom", 1.0),
                             "sound": seg.get("sound", "voice"), "source_in": seg["in"],
                             "caption_y": seg.get("caption_y", plan.get("caption_y", {}).get(seg["layout"], 1250))})
            clock += length
            listing.append(f"file '{path}'")
        (work / "segments.txt").write_text("\n".join(listing) + "\n")
        (work / "timeline.json").write_text(json.dumps(timeline, indent=1))
        run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(work / "segments.txt"), "-c", "copy", str(picture)])
    effects = []
    if plan.get("graphics"):
        (work / "plain.mp4").unlink(missing_ok=True)
        picture.rename(work / "plain.mp4")
        effects = graphics.render(plan, timeline, work / "plain.mp4", picture)
        (work / "effects.json").write_text(json.dumps(effects, indent=1))
    sound, spans = render_sound(plan, work, effects)
    print(f"{len(timeline)} picture segments, {spans} uncut stretches of sound, {clock:.2f}s")

    final = plan_path.parent / plan["output"]
    encode_audio = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-shortest"]
    if not plan.get("captions", False):
        run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(picture), "-i", str(sound), "-map", "0:v", "-map", "1:a", "-c:v", "copy"] + encode_audio + [str(final)])
    else:
        mixed = work / "mixed.mp4"
        run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(picture), "-i", str(sound), "-map", "0:v", "-map", "1:a", "-c:v", "copy"] + encode_audio + [str(mixed)])
        overlays = caption_overlays(plan, work, timeline, mixed)
        cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", str(mixed)]
        graph, last = [], "0:v"
        for number, item in enumerate(overlays, start=1):
            cmd += ["-i", item["file"]]
            graph.append(f"[{last}][{number}:v]overlay=0:{item['y'] - 100}:enable='between(t,{item['start']},{item['end']})'[v{number}]")
            last = f"v{number}"
        run(cmd + ["-filter_complex", ";".join(graph), "-map", f"[{last}]", "-map", "0:a", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                   "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(final)])
    print(f"-> {final}")


if __name__ == "__main__":
    main()
