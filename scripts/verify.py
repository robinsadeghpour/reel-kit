#!/usr/bin/env python3
"""Check a rendered cut and say where a person still has to listen.

Nothing here can hear. What it can do is compare: the words that should be in the cut
(taken from the phrase-by-phrase ledger of the raw recording) against the words a fresh
transcription finds in the finished sound. Where the two differ, a word was clipped,
doubled, or simply misheard, and only a person can tell which. Those places are printed
as a short "listen here" list with timestamps in the finished video.

Also checked: picture and sound are the same length, loudness and peak are in range, no
filler sound or immediately repeated word is heard, and a contact sheet with one still
per segment is written for a visual check.

Usage: reel verify out/<name>/plan.json
"""

import difflib
import json
import re
import subprocess
import sys

import numpy
from faster_whisper import WhisperModel

import kit
from kit import norm

RATE = 16000


def glue(words):
    """“low”, “-key” and “5”, “.5” are one word each; the transcriber splits them differently every time."""
    out = []
    for word in words:
        if out and word[:1] in "-.":
            out[-1] += word
        else:
            out.append(word)
    return out


def same(a, b):
    """Spelling variants of one word (“meant”/“mean”, “an”/“a”) are not worth a listen."""
    a, b = norm(a), norm(b)
    return a == b or (min(len(a), len(b)) >= 3 and difflib.SequenceMatcher(a=a, b=b).ratio() >= 0.72) or a.startswith(b) or b.startswith(a)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return float(out.strip())


def loudness(path):
    log = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    tail = log[log.rfind("Summary"):]
    integrated = re.search(r"I:\s+(-?[\d.]+) LUFS", tail)
    peak = re.search(r"Peak:\s+(-?[\d.]+) dBFS", tail)
    return float(integrated.group(1)), float(peak.group(1))


def main():
    plan_path, plan = kit.load_plan(sys.argv[1])
    hesitation, _, prompt = kit.fillers(plan["language"], plan.get("fillers"))
    base = plan_path.parent
    work = base / "work"
    timeline = json.loads((work / "timeline.json").read_text())
    final = base / plan["output"]
    problems, listen = [], []

    lengths = {name: duration(path) for name, path in [("picture", work / "picture.mp4"), ("sound", work / "sound.wav"), ("final", final)]}
    if max(lengths.values()) - min(lengths.values()) > 0.05:
        problems.append(f"picture and sound differ in length: {lengths}")
    integrated, peak = loudness(final)
    if peak > -1.0:
        problems.append(f"peak is {peak} dBFS: too hot, will sound overdriven")
    target = plan.get("loudness", -15)
    if not target - 3 <= integrated <= target + 2:
        problems.append(f"loudness is {integrated} LUFS, outside {target - 3} to {target + 2}")

    # The words that should be there: ledger words inside each voice segment, in play order.
    ledger_path = base / "analysis" / "ledger.json"
    ledger_words = [w for p in json.loads(ledger_path.read_text())["phrases"] for w in p["words"]] if ledger_path.exists() else []
    stretches = []  # uncut runs of voice in the finished video
    for seg, plan_seg in zip(timeline, plan["segments"]):
        if seg["sound"] != "voice":
            continue
        source_in, source_out = seg["source_in"], seg["source_in"] + (seg["end"] - seg["start"])
        expected = [w["w"] for w in ledger_words if source_in - 0.02 <= (w["s"] + w["e"]) / 2 < source_out + 0.02]
        if stretches and abs(stretches[-1]["end"] - seg["start"]) < 0.001 and abs(stretches[-1]["source_out"] - source_in) < 0.001:
            stretches[-1]["end"], stretches[-1]["source_out"] = seg["end"], source_out
            stretches[-1]["expected"] += expected
        else:
            stretches.append({"start": seg["start"], "end": seg["end"], "source_out": source_out, "expected": expected})

    # Listen to the voice on its own when there is one: sound effects confuse the transcriber.
    voice = work / "voice.wav" if (work / "voice.wav").exists() else work / "sound.wav"
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(voice), "-ar", str(RATE), "-ac", "1", "-f", "f32le", "-"], capture_output=True).stdout
    audio = numpy.frombuffer(raw, dtype=numpy.float32)
    model = WhisperModel(plan.get("whisper_model", "large-v3-turbo"), device="cpu", compute_type="int8")
    # Listen across each join with some of both sides, so a doubled or clipped word at the join is in view.
    voice = [s for s in stretches]
    heard_all, expected_all = [], []
    blocks, current = [], None
    for stretch in voice:
        if current and stretch["start"] - current["end"] < 0.01:
            current["end"] = stretch["end"]
            current["expected"] += stretch["expected"]
            current["joins"].append(stretch["start"])
        else:
            current = {"start": stretch["start"], "end": stretch["end"], "expected": list(stretch["expected"]), "joins": []}
            blocks.append(current)
    for block in blocks:
        a, b = max(block["start"] - 0.1, 0), block["end"] + 0.1
        segments, _ = model.transcribe(audio[int(a * RATE):int(b * RATE)], language=plan["language"], word_timestamps=True, vad_filter=False,
                                       condition_on_previous_text=False, initial_prompt=prompt)
        heard = []
        for s in segments:
            for w in s.words or []:
                if heard and w.word.strip()[:1] in "-.":
                    heard[-1]["w"] += w.word.strip()
                else:
                    heard.append({"w": w.word.strip(), "t": round(a + w.start, 2)})
        block["expected"] = glue(block["expected"])
        heard_tokens = [norm(h["w"]) for h in heard]
        expected_tokens = [norm(w) for w in block["expected"]]
        for h in heard:
            if hesitation.match(norm(h["w"])):
                listen.append((h["t"], f"a filler sound is heard: “{h['w']}”"))
        for first, second in zip(heard, heard[1:]):
            if norm(first["w"]) and norm(first["w"]) == norm(second["w"]) and len(norm(first["w"])) > 2:
                listen.append((second["t"], f"the word “{second['w']}” is heard twice in a row"))
        if expected_tokens:
            matcher = difflib.SequenceMatcher(a=[t for t in expected_tokens if t], b=[t for t in heard_tokens if t], autojunk=False)
            heard_clean = [h for h in heard if norm(h["w"])]
            expected_clean = [w for w in block["expected"] if norm(w)]
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == "equal":
                    continue
                want, got = expected_clean[i1:i2], [h["w"] for h in heard_clean[j1:j2]]
                if "".join(norm(x) for x in want) == "".join(norm(x) for x in got):
                    continue
                if len(want) == len(got) and all(same(x, y) for x, y in zip(want, got)):
                    continue
                when = heard_clean[min(j1, len(heard_clean) - 1)]["t"] if heard_clean else block["start"]
                listen.append((when, f"expected “{' '.join(expected_clean[i1:i2]) or '(nothing)'}”, heard “{' '.join(h['w'] for h in heard_clean[j1:j2]) or '(nothing)'}”"))
        heard_all.append(" ".join(h["w"] for h in heard))
        expected_all.append(" ".join(block["expected"]))

    # One still per segment, for looking at.
    stills = []
    for index, seg in enumerate(timeline):
        still = work / f"verify-{index:02d}.jpg"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{(seg['start'] + seg['end']) / 2:.2f}", "-i", str(final), "-frames:v", "1", "-vf", "scale=216:-2", "-q:v", "5", str(still)])
        stills.append(still)
    columns = min(len(stills), 9)
    rows = -(-len(stills) // columns)
    sheet = work / "verify-sheet.jpg"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-pattern_type", "glob", "-i", str(work / "verify-*.jpg"), "-vf", f"tile={columns}x{rows}", "-frames:v", "1", "-q:v", "4", str(sheet)])
    for still in stills:
        still.unlink(missing_ok=True)

    listen.sort()
    report = {"lengths": lengths, "loudness_lufs": integrated, "peak_dbfs": peak, "problems": problems,
              "listen": [{"at": t, "why": why} for t, why in listen], "heard": heard_all, "contact_sheet": str(sheet)}
    (work / "verify.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"length {lengths['final']:.2f}s | loudness {integrated} LUFS | peak {peak} dBFS | {len(timeline)} segments")
    print("PROBLEMS:" if problems else "no measurable problems")
    for problem in problems:
        print("  -", problem)
    print(f"LISTEN HERE ({len(listen)}):" if listen else "nothing flagged for listening")
    for t, why in listen:
        print(f"  {t:6.2f}s  {why}")
    print("contact sheet:", sheet)


if __name__ == "__main__":
    main()
