#!/usr/bin/env python3
"""Transcribe a recording with word-level timing, on this machine.

Usage: reel words AUDIO_OR_VIDEO OUT.json [--language de]

Without --language the transcriber decides for itself.
"""

import argparse
import json
import subprocess

import numpy
from faster_whisper import WhisperModel

parser = argparse.ArgumentParser()
parser.add_argument("source")
parser.add_argument("out")
parser.add_argument("--language")
parser.add_argument("--model", default="large-v3-turbo")
args = parser.parse_args()

# Decode with ffmpeg ourselves, so this does not depend on the transcriber's bundled decoder.
raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", args.source, "-vn", "-ar", "16000", "-ac", "1", "-f", "f32le", "-"], capture_output=True).stdout
model = WhisperModel(args.model, device="cpu", compute_type="int8")
# No voice-activity filter and no carry-over between segments: a repeated take must not be
# smoothed away, because finding repeats is the point.
segments, info = model.transcribe(numpy.frombuffer(raw, dtype=numpy.float32), language=args.language, word_timestamps=True, vad_filter=False, condition_on_previous_text=False)
rows = []
for segment in segments:
    rows.append({"start": round(segment.start, 2), "end": round(segment.end, 2), "text": segment.text.strip(),
                 "words": [{"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2), "p": round(w.probability, 2)} for w in segment.words or []]})
json.dump(rows, open(args.out, "w"), indent=1, ensure_ascii=False)
print(len(rows), "segments,", sum(len(r["words"]) for r in rows), "words")
