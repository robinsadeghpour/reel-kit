#!/usr/bin/env python3
"""Take the breaths and the hesitation pauses out of a plan's chosen takes.

Works from the loudness of the recording, not from a transcript: inside every stretch the
plan keeps, it finds each burst of sound, drops the ones that are only a breath (quiet,
with no speech-level peak), drops any spans listed by hand, and closes every pause longer
than a natural one. The result is written next to the plan as plan.tight.json, with the
same looks and graphics, and is what you render, proof and verify.

What it cannot do: tell a stutter inside a word from the word. Sounds it cannot classify
are left in. Name them in "drop" once someone has listened.

Plan options (all optional), under "tighten":
  max_pause    pauses longer than this are shortened            (0.22 s)
  pause        what a shortened pause is left at                (0.11 s)
  breath_peak  a burst that never gets louder than this is a breath  (-30 dB)
  drop         [[from, to], ...] in seconds of the recording: remove whatever sounds in there

A segment with "tighten": false is left exactly as written, for a moment whose pauses are
the point (a reaction, a beat before a punchline).

Usage: reel tighten out/<name>/plan.json
"""

import json
import sys

import numpy

import kit

FLOOR = -44   # anything above this counts as sound
LEAD, TAIL = 0.06, 0.05  # room kept before and after a stretch of speech


def bursts(db, start, end):
    """Every burst of sound in [start, end], with its loudest level."""
    found, begin = [], None
    first, last = int(start * 100), min(int(end * 100), len(db))
    for i in range(first, last + 1):
        on = i < last and db[i] > FLOOR
        if on and begin is None:
            begin = i
        elif not on and begin is not None:
            if i - begin >= 4:
                found.append({"start": begin / 100, "end": i / 100, "peak": float(db[begin:i].max())})
            begin = None
    return found


def main():
    plan_path, plan = kit.read_plan(sys.argv[1])
    options = plan.get("tighten", {})
    max_pause, pause = options.get("max_pause", 0.22), options.get("pause", 0.11)
    breath_peak, drops = options.get("breath_peak", -30), options.get("drop", [])
    envelope = plan_path.parent / "analysis" / "envelope.npy"
    if not envelope.exists():
        raise SystemExit(f"{envelope} is missing: run `reel analyze` on the recording first, with out/<name>/analysis as its folder")
    db = numpy.load(envelope)
    looks = plan.get("looks", {})

    # Stretches of the recording the plan plays without a cut.
    runs = []
    for number, seg in enumerate(plan["segments"]):
        seg["_was"] = number
        if seg.get("sound") == "clip" or seg["layout"] != "talk":
            runs.append([seg])
        elif runs and runs[-1][-1]["layout"] == "talk" and abs(runs[-1][-1]["out"] - seg["in"]) < 1e-3:
            runs[-1].append(seg)
        else:
            runs.append([seg])

    tightened, removed_breaths, closed, saved = [], 0, 0, 0.0
    for run in runs:
        if run[0].get("sound") == "clip" or run[0]["layout"] != "talk" or any(seg.get("tighten") is False for seg in run):
            tightened += run
            continue
        start, end = run[0]["in"], run[-1]["out"]
        groups, pending_break = [], False
        for burst in bursts(db, start, end):
            dropped = any(a <= burst["start"] and burst["end"] <= b for a, b in drops)
            if dropped or burst["peak"] < breath_peak:
                if dropped or burst["end"] - burst["start"] >= 0.1:
                    pending_break = True
                    removed_breaths += 0 if dropped else 1
                continue
            if groups and not pending_break and burst["start"] - groups[-1][1] <= max_pause:
                groups[-1][1] = burst["end"]
            else:
                groups.append([burst["start"], burst["end"]])
            pending_break = False
        if not groups:
            tightened += run
            continue
        closed += len(groups) - 1
        for number, (a, b) in enumerate(groups):
            # Leave a little room around the speech, but never reach into what was removed.
            lead = min(LEAD, pause / 2) if number else LEAD
            tail = min(TAIL, pause / 2) if number < len(groups) - 1 else TAIL
            a, b = max(a - lead, start), min(b + tail, end)
            pieces = []
            for seg in run:
                lo, hi = max(a, seg["in"]), min(b, seg["out"])
                if hi - lo > 0.001:
                    piece = {**seg, "in": round(lo, 4), "out": round(hi, 4)}
                    if "zoom_to" in seg:
                        # A slow push carries on through the cut: each piece gets its share of it.
                        first = seg.get("zoom", looks.get(seg.get("look"), {}).get("zoom", 1.0))
                        rate = (seg["zoom_to"] - first) / (seg["out"] - seg["in"])
                        piece["zoom"] = round(first + rate * (lo - seg["in"]), 4)
                        piece["zoom_to"] = round(first + rate * (hi - seg["in"]), 4)
                    pieces.append(piece)
            # A sliver of a segment is not worth a picture change: give it to its neighbour.
            merged = []
            for piece in pieces:
                if merged and (piece["out"] - piece["in"] < 0.12 or merged[-1]["out"] - merged[-1]["in"] < 0.12):
                    keep = merged[-1] if merged[-1]["out"] - merged[-1]["in"] >= piece["out"] - piece["in"] else piece
                    merged[-1] = {**keep, "in": merged[-1]["in"], "out": piece["out"]}
                else:
                    merged.append(piece)
            for index, piece in enumerate(merged):
                piece.pop("fade_in", None)
                piece.pop("fade_out", None)
                if index == 0:
                    piece["fade_in"] = run[0].get("fade_in", 0.045) if number == 0 else 0.02
                if index == len(merged) - 1:
                    piece["fade_out"] = run[-1].get("fade_out", 0.07) if number == len(groups) - 1 else 0.03
            tightened += merged
            saved -= b - a
        saved += end - start

    # A graphic tied to a segment by its number follows that segment to its new place.
    moved = {}
    for number, seg in enumerate(tightened):
        moved.setdefault(seg.pop("_was"), number)
    for graphic in plan.get("graphics", []):
        if "segment" in graphic:
            graphic["segment"] = moved[graphic["segment"]]
    plan["segments"] = tightened
    out = plan_path.with_name("plan.tight.json")
    out.write_text(json.dumps(plan, indent=1, ensure_ascii=False))
    total = sum(s["out"] - s["in"] for s in tightened)
    print(f"{removed_breaths} breaths removed, {closed} cuts added, {saved:.1f}s shorter, {total:.1f}s -> {out}")


if __name__ == "__main__":
    main()
