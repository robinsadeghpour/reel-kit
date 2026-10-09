#!/usr/bin/env python3
"""Listen to a raw recording and write down everything that was said, take by take.

A normal transcript hides the things an edit has to remove: the transcriber smooths over
restarts, doubled words and fillers. So this does not transcribe the recording as a whole.
It finds every stretch of speech from the loudness of the audio, then transcribes each
stretch on its own, with nothing before or after it to lean on. A sentence that was
started three times shows up as three entries.

Output: <outdir>/ledger.json and a printed ledger. Each phrase has exact start and end
times taken from the audio (not from the transcriber), its words with timing, and flags:
  retake    a later phrase starts with the same words: this one was probably abandoned
  fragment  very short, or ends mid-thought
  filler    only a filler sound
  filler-inside  a hesitation sound ("um", "äh") somewhere in the phrase; the line below
            the phrase says which word and when
  unsure    the transcriber was not confident; a person should listen
  restart-inside  a false start with barely a pause, hidden in the phrase's text; the line
            below the phrase says where the real sentence begins

The language comes from --language, else from "language" in the project's reel.json, else
it is detected from the first minute. Hesitation sounds are known for German and English;
for other languages add your own under "fillers" in reel.json (see scripts/kit.py).

Usage: reel analyze RECORDING OUTDIR [--language de] [--model large-v3-turbo]
"""

import argparse
import json
import re
import subprocess
from pathlib import Path

import numpy
from faster_whisper import WhisperModel

import kit
from kit import norm

RATE = 16000
HOP = 160  # 10 ms


def load(path):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-vn", "-map", "0:a:0", "-ar", str(RATE), "-ac", "1", "-f", "f32le", "-"], capture_output=True).stdout
    return numpy.frombuffer(raw, dtype=numpy.float32)


def envelope(audio):
    """Loudness in dB every 10 ms."""
    frames = len(audio) // HOP
    padded = numpy.concatenate([audio, numpy.zeros(HOP * 3, dtype=numpy.float32)])
    energy = numpy.array([numpy.sqrt(numpy.mean(padded[i * HOP:i * HOP + 400] ** 2)) for i in range(frames)])
    return 20 * numpy.log10(numpy.maximum(energy, 1e-6))


def speech_phrases(db, min_len=0.08, join_gap=0.32):
    """Stretches louder than the room, joined across the short pauses inside a sentence."""
    floor = float(numpy.percentile(db, 15))
    threshold = max(floor + 11, -48)
    loud = db > threshold
    islands, start = [], None
    for i, on in enumerate(loud):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if (i - start) * HOP / RATE >= min_len:
                islands.append([start * HOP / RATE, i * HOP / RATE])
            start = None
    if start is not None:
        islands.append([start * HOP / RATE, len(loud) * HOP / RATE])
    phrases = []
    for island in islands:
        if phrases and island[0] - phrases[-1]["end"] < join_gap:
            phrases[-1]["end"] = island[1]
            phrases[-1]["islands"].append(island)
        else:
            phrases.append({"start": island[0], "end": island[1], "islands": [island]})
    return phrases, threshold


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("outdir")
    parser.add_argument("--language")
    parser.add_argument("--model")
    args = parser.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    kit.find_project()
    project = kit.settings()

    audio = load(args.source)
    if not len(audio):
        raise SystemExit(f"no sound could be read from {args.source}")
    db = envelope(audio)
    numpy.save(out / "envelope.npy", db.astype(numpy.float32))
    phrases, threshold = speech_phrases(db)
    model = WhisperModel(args.model or project.get("whisper_model", "large-v3-turbo"), device="cpu", compute_type="int8")
    language = args.language or project.get("language")
    if not language:
        # Short stretches on their own are too little to tell a language from, so decide once.
        _, info = model.transcribe(audio[:RATE * 60], vad_filter=True)
        language = info.language
        print(f"language detected: {language} ({info.language_probability:.0%}). Set \"language\" in reel.json to fix it.")
    hesitation, filler_phrase, prompt = kit.fillers(language, project.get("fillers"))

    for phrase in phrases:
        pad = 0.18
        a, b = max(phrase["start"] - pad, 0), min(phrase["end"] + pad, len(audio) / RATE)
        segments, _ = model.transcribe(audio[int(a * RATE):int(b * RATE)], language=language, word_timestamps=True, vad_filter=False,
                                       condition_on_previous_text=False, initial_prompt=prompt)
        segments = list(segments)
        phrase["words"] = [{"w": w.word.strip(), "s": round(a + w.start, 2), "e": round(a + w.end, 2), "p": round(w.probability, 2)} for s in segments for w in s.words or []]
        phrase["text"] = " ".join(s.text.strip() for s in segments).strip()
        phrase["confidence"] = round(float(numpy.mean([w["p"] for w in phrase["words"]])) if phrase["words"] else 0.0, 2)
        phrase["no_speech"] = round(max((s.no_speech_prob for s in segments), default=1.0), 2)
        phrase["start"], phrase["end"] = round(phrase["start"], 2), round(phrase["end"], 2)
        phrase["islands"] = [[round(x, 2), round(y, 2)] for x, y in phrase["islands"]]

    # A restart with almost no pause hides inside a phrase: "And that... And the amount" comes back
    # as one clean "And the amount". So listen to every short stretch that is followed by a small
    # pause on its own, and to what follows; if both open with the same word, it was a false start.
    def hear(start, end):
        segments, _ = model.transcribe(audio[int(max(start - 0.1, 0) * RATE):int((end + 0.1) * RATE)], language=language, vad_filter=False, condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segments)

    for phrase in phrases:
        phrase["restarts"] = []
        for first, following in zip(phrase["islands"], phrase["islands"][1:]):
            if 0.2 < first[1] - first[0] < 1.3 and following[0] - first[1] >= 0.15:
                alone, after = hear(first[0], first[1]), hear(following[0], min(following[0] + 2.0, phrase["end"]))
                a, b = [norm(w) for w in alone.split() if norm(w)], [norm(w) for w in after.split() if norm(w)]
                if a and b and a[0] == b[0]:
                    phrase["restarts"].append({"from": first[0], "until": following[0], "heard": alone, "then": after})

    for index, phrase in enumerate(phrases):
        flags = ["restart-inside"] if phrase["restarts"] else []
        tokens = [norm(w["w"]) for w in phrase["words"] if norm(w["w"])]
        length = phrase["end"] - phrase["start"]
        if not tokens or all(filler_phrase.match(token) for token in tokens):
            flags.append("filler")
        elif any(hesitation.match(token) for token in tokens):
            flags.append("filler-inside")
        if phrase["confidence"] < 0.55 or (length < 0.5 and phrase["no_speech"] > 0.5):
            flags.append("unsure")
        if tokens and (length < 0.6 or not re.search(r"[.!?]$", phrase["text"])):
            flags.append("fragment")
        # A retake: a later phrase, soon after, opens with the same two or three words.
        for later in phrases[index + 1:index + 6]:
            later_tokens = [norm(w["w"]) for w in later["words"] if norm(w["w"])]
            if later["start"] - phrase["end"] > 25 or len(tokens) < 2 or len(later_tokens) < 2:
                continue
            shared = sum(1 for x, y in zip(tokens, later_tokens) if x == y)
            overlap = len(set(tokens[:6]) & set(later_tokens[:6]))
            if (tokens[:2] == later_tokens[:2]) or (shared >= 2) or (overlap >= 3 and len(tokens) <= 8):
                flags.append("retake")
                phrase["retaken_at"] = later["start"]
                break
        phrase["flags"] = flags

    (out / "ledger.json").write_text(json.dumps({"source": args.source, "language": language, "threshold_db": round(threshold, 1), "phrases": phrases}, indent=1, ensure_ascii=False))
    print(f"{len(phrases)} phrases, speech threshold {threshold:.1f} dB")
    for index, phrase in enumerate(phrases):
        flags = (" [" + ", ".join(phrase["flags"]) + "]") if phrase["flags"] else ""
        print(f"{index:3d}  {phrase['start']:7.2f}-{phrase['end']:7.2f} ({phrase['end'] - phrase['start']:4.1f}s){flags}  {phrase['text']}")
        if "filler-inside" in phrase["flags"]:
            print("       hesitation: " + ", ".join(f"“{w['w']}” {w['s']:.2f}-{w['e']:.2f}" for w in phrase["words"] if hesitation.match(norm(w["w"]))))
        for restart in phrase["restarts"]:
            print(f"       false start {restart['from']:.2f}-{restart['until']:.2f}: “{restart['heard']}” then “{restart['then']}”. Start the segment at {restart['until'] - 0.07:.2f} or later.")


if __name__ == "__main__":
    main()
