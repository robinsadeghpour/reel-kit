#!/usr/bin/env python3
"""Make the kit's four sound effects from nothing, so they carry no licence.

The sounds are plain synthesis: a falling tone for a pop, a short click for a tick, swept
noise for a whoosh. They are generated once and kept in assets/sfx/; run this again only to
change them. To use your own sounds instead, put pop.wav (or .mp3), pop-small, whoosh and
tick in your project's sfx/ folder.

Each file starts with a few milliseconds of silence so its attack survives encoding; the
lead times in graphics.py (SFX) account for that.

Usage: reel make-sfx [OUTDIR]
"""

import sys
import wave
from pathlib import Path

import numpy

RATE = 48000
PEAK = 0.9


def tone(length, pitch, decay, attack=0.002, start=0.0):
    """A sine whose pitch follows pitch(t), fading out at the given rate, after `start` seconds of silence."""
    t = numpy.arange(int(length * RATE)) / RATE
    phase = 2 * numpy.pi * numpy.cumsum(pitch(t)) / RATE
    sound = numpy.sin(phase) * (1 - numpy.exp(-t / attack)) * numpy.exp(-t / decay)
    return numpy.concatenate([numpy.zeros(int(start * RATE)), sound])


def click(length, seed, start=0.0):
    """A few milliseconds of noise: the edge that makes a pop or a tick read as a hit."""
    noise = numpy.random.default_rng(seed).standard_normal(int(length * RATE))
    return numpy.concatenate([numpy.zeros(int(start * RATE)), noise * numpy.hanning(len(noise))])


def mix(*parts):
    out = numpy.zeros(max(len(p) for p in parts))
    for part in parts:
        out[:len(part)] += part
    return out


def swept_noise(length, peak_at, low, high, seed):
    """Noise through a band-pass that opens and closes, loudest at peak_at seconds."""
    n = int(length * RATE)
    t = numpy.arange(n) / RATE
    noise = numpy.random.default_rng(seed).standard_normal(n)
    rise = numpy.clip(t / peak_at, 0, 1)
    fall = numpy.clip((length - t) / (length - peak_at), 0, 1)
    shape = numpy.where(t < peak_at, rise ** 2.2, fall ** 1.6)
    centre = low + (high - low) * numpy.where(t < peak_at, rise ** 1.5, fall ** 0.8)
    out, band, lowpass = numpy.zeros(n), 0.0, 0.0
    for i in range(n):  # a state-variable filter, one sample at a time, so its centre can move
        f = 2 * numpy.sin(numpy.pi * centre[i] / RATE)
        highpass = noise[i] - lowpass - 0.9 * band
        band += f * highpass
        lowpass += f * band
        out[i] = band
    return out * shape


def save(name, sound, folder):
    sound = sound / numpy.abs(sound).max() * PEAK
    fade = int(0.004 * RATE)
    sound[-fade:] *= numpy.linspace(1, 0, fade)
    with wave.open(str(folder / f"{name}.wav"), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(RATE)
        file.writeframes((sound * 32767).astype("<i2").tobytes())
    window = 480
    level = numpy.sqrt(numpy.convolve(sound ** 2, numpy.ones(window) / window, mode="same"))
    print(f"{name:10} {len(sound) / RATE:.3f}s  loudest at {level.argmax() / RATE:.3f}s  level {level.max():.3f}")


def main():
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "assets" / "sfx"
    folder.mkdir(parents=True, exist_ok=True)
    save("pop", mix(tone(0.22, lambda t: 300 + 520 * numpy.exp(-t / 0.02), 0.045, start=0.01), 0.25 * click(0.004, 1, start=0.01)), folder)
    save("pop-small", mix(tone(0.13, lambda t: 700 + 900 * numpy.exp(-t / 0.012), 0.025, attack=0.001, start=0.006), 0.2 * click(0.003, 2, start=0.006)), folder)
    save("tick", mix(tone(0.09, lambda t: 1800 + 0 * t, 0.006, attack=0.0005, start=0.003), 0.7 * tone(0.09, lambda t: 620 + 0 * t, 0.018, attack=0.0005, start=0.003),
                     0.5 * click(0.002, 3, start=0.003)), folder)
    save("whoosh", swept_noise(0.62, 0.24, 250, 1900, 4), folder)


if __name__ == "__main__":
    main()
