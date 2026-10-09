#!/usr/bin/env python3
"""Draw the graphics layer of a video and lay it over the cut picture.

Everything that is not the speaker lives here: floating browser cards, number stickers,
big phone-shaped cards, strips cut out of a page, and a fan of small cards. Each is drawn
frame by frame with Pillow, so it can ease in, drift and ease out, which ffmpeg's own
overlay cannot do well. The frames are piped straight into ffmpeg over the picture.

The plan lists graphics with "from" and "to" in seconds of the main recording, the same
clock the segments use. They are mapped onto the finished timeline here, so moving a cut
does not mean re-timing the graphics.

Kinds (see skills/edit/references/plan-format.md):
  card   a page (or a playing clip) in a browser window, above the speaker's head
  strip  a cut-out piece of a page, no window around it
  photo  a photo or a cut-out as a white-framed print
  big    a tall image as a large rounded card over a dimmed picture
  stat   a number sticker
  deck   several small cards popping in one after another

Colours come from "theme" in reel.json or the plan, the typeface from "font", and each
sound from the project's own sfx/ folder when it has a file of that name.

Used by cut.py; not run on its own.
"""

import math
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import kit
from kit import font

W, H, FPS = 1080, 1920, 30

# The four colours everything is drawn in. "theme" in reel.json or the plan replaces any of them.
THEME = {"ink": (12, 12, 16), "paper": (255, 255, 255), "accent": (200, 245, 60), "warn": (255, 92, 74)}
TONES = {"good": "accent", "neutral": "paper", "bad": "warn", "dark": "ink"}
GROUPING = ","  # between the thousands of a number that counts up
# For each sound: when it should start relative to the moment its graphic appears, so the loud
# part lands on it, and how loud it is mixed (1.0 is the file as it comes, far too loud under a voice).
# These values fit the kit's own files in assets/sfx; for your own files set them under "sfx".
SFX = {"pop": (-0.010, 0.19), "pop-small": (-0.006, 0.24), "whoosh": (-0.20, 0.43), "tick": (-0.003, 0.31)}


def configure(plan):
    """Take colours and number format from the plan."""
    global GROUPING
    for name, value in (plan.get("theme") or {}).items():
        if name not in THEME:
            raise SystemExit(f"theme has no colour called {name!r}; the colours are {', '.join(THEME)}")
        THEME[name] = colour(value)
    GROUPING = kit.thousands(plan)


def tone(name):
    """Background and text colour of a tone: the text is ink or paper, whichever reads better."""
    back = THEME[TONES[name]]
    light = 0.299 * back[0] + 0.587 * back[1] + 0.114 * back[2] > 150
    return back, THEME["ink"] if light else THEME["paper"]


def sound(name, plan):
    """File, lead and level of a sound. A file of that name in the project's sfx/ folder wins;
    "sfx" in the plan or reel.json can set {"file", "lead", "gain"} for any name."""
    lead, gain = SFX.get(name, (0.0, 0.30))
    custom = (plan.get("sfx") or {}).get(name, {})
    file = kit.path(custom["file"]) if custom.get("file") else None
    for folder in (kit.ROOT / "sfx", kit.KIT / "assets" / "sfx"):
        for ending in (".wav", ".mp3", ".m4a", ".ogg"):
            if file is None and (folder / f"{name}{ending}").exists():
                file = folder / f"{name}{ending}"
    if file is None or not file.exists():
        raise SystemExit(f"no sound called {name!r}: put {name}.wav or {name}.mp3 in the project's sfx/ folder, or set \"sfx\": null on the graphic")
    return str(file), custom.get("lead", lead), custom.get("gain", gain)


def clamp(x):
    return max(0.0, min(1.0, x))


def out_cubic(p):
    return 1 - (1 - p) ** 3


def out_back(p, overshoot=1.7):
    p -= 1
    return 1 + (overshoot + 1) * p ** 3 + overshoot * p ** 2


def smooth(p):
    return 3 * p * p - 2 * p ** 3


def rounded_mask(size, radius):
    """Antialiased rounded rectangle, drawn large and scaled down."""
    big = Image.new("L", (size[0] * 3, size[1] * 3), 0)
    ImageDraw.Draw(big).rounded_rectangle([0, 0, size[0] * 3 - 1, size[1] * 3 - 1], radius * 3, fill=255)
    return big.resize(size, Image.LANCZOS)


def shadow_layer(size, radius, pad, blur=34, drop=24, strength=150):
    layer = Image.new("RGBA", (size[0] + pad * 2, size[1] + pad * 2), (0, 0, 0, 0))
    shape = Image.new("L", layer.size, 0)
    ImageDraw.Draw(shape).rounded_rectangle([pad, pad + drop, pad + size[0], pad + drop + size[1]], radius, fill=strength)
    layer.putalpha(shape.filter(ImageFilter.GaussianBlur(blur)))
    return layer


def place(canvas, layer, cx, cy, scale=1.0, angle=0.0, opacity=1.0):
    """Put a layer on the canvas by its centre, scaled, turned and faded."""
    if opacity <= 0.004:
        return
    img = layer
    if abs(scale - 1) > 0.002:
        img = img.resize((max(2, round(img.width * scale)), max(2, round(img.height * scale))), Image.BICUBIC)
    if abs(angle) > 0.01:
        img = img.rotate(angle, resample=Image.BICUBIC, expand=True)
    if opacity < 0.996:
        img = img.copy() if img is layer else img
        img.putalpha(img.getchannel("A").point(lambda v: int(v * opacity)))
    x, y = round(cx - img.width / 2), round(cy - img.height / 2)
    left, top = max(0, -x), max(0, -y)
    right, bottom = min(img.width, W - x), min(img.height, H - y)
    if right <= left or bottom <= top:
        return
    if (left, top, right, bottom) != (0, 0, img.width, img.height):
        img = img.crop((left, top, right, bottom))
    canvas.alpha_composite(img, (x + left, y + top))


def chip(label):
    """The small dark tag on a card: a counter in the accent colour, a name, an optional quieter note."""
    s = 2
    name, counter, note = label.get("title", ""), label.get("n"), label.get("sub")
    name_font, note_font, count_font = font(27 * s, "Semibold"), font(24 * s, "Medium"), font(21 * s, "Heavy")
    height, x = 58 * s, 10 * s
    width = x
    if counter:
        badge_w = round(count_font.getlength(counter)) + 26 * s
        width += badge_w + 14 * s
    else:
        width += 14 * s
    width += round(name_font.getlength(name))
    if note:
        width += 16 * s + round(note_font.getlength(note))
    width += 24 * s
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, width - 1, height - 1], height // 2, fill=THEME["ink"] + (255,), outline=(255, 255, 255, 46), width=2 * s)
    if counter:
        badge, badge_text = tone("good")
        draw.rounded_rectangle([x, 10 * s, x + badge_w, height - 10 * s], (height - 20 * s) // 2, fill=badge)
        draw.text((x + badge_w / 2, height / 2), counter, font=count_font, fill=badge_text, anchor="mm")
        x += badge_w + 14 * s
    else:
        x += 14 * s
    draw.text((x, height / 2), name, font=name_font, fill=tone("dark")[1], anchor="lm")
    x += round(name_font.getlength(name))
    if note:
        draw.text((x + 16 * s, height / 2 + s), note, font=note_font, fill=(165, 165, 176), anchor="lm")
    return img.resize((width // s, height // s), Image.LANCZOS)


def window_chrome(width, bar, body, url, dark):
    """The browser window around a page: title bar with three dots and an address pill."""
    img = Image.new("RGBA", (width, bar + body), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if bar:
        k = bar / 50  # small cards get a proportionally smaller bar
        draw.rectangle([0, 0, width, bar], fill=(32, 32, 36, 255) if dark else (240, 240, 243, 255))
        for i, colour in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
            draw.ellipse([round((22 + i * 22) * k), bar // 2 - round(7 * k), round((36 + i * 22) * k), bar // 2 + round(7 * k)], fill=colour)
        if url:
            face = font(round(20 * k), "Medium")
            pill = round(face.getlength(url) + 56 * k)
            draw.rounded_rectangle([(width - pill) // 2, round(10 * k), (width + pill) // 2, bar - round(10 * k)], (bar - round(20 * k)) // 2,
                                   fill=(54, 54, 60, 255) if dark else (255, 255, 255, 255))
            draw.text((width // 2, bar // 2), url, font=face, fill=(190, 190, 200) if dark else (96, 96, 104), anchor="mm")
        draw.line([0, bar, width, bar], fill=(0, 0, 0, 40), width=1)
    return img


def colour(value):
    return tuple(int(value.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) if isinstance(value, str) else tuple(value)


def load_picture(spec, ratio=None):
    """Open a picture for a card: crop it, flatten a cut-out onto a background, fit and pad it."""
    img = Image.open(kit.path(spec["image"]))
    if spec.get("crop"):
        x, y, w, h = spec["crop"]
        img = img.crop((x, y, x + w, y + h))
    back = colour(spec["background"]) if spec.get("background") else None
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        if img.getchannel("A").getextrema()[0] < 255:
            # A cut-out: trim the empty margin, then lay it on a plain background.
            img = img.crop(img.getchannel("A").getbbox())
            flat = Image.new("RGB", img.size, back or (244, 241, 234))
            flat.paste(img, mask=img.getchannel("A"))
            img, back = flat, back or (244, 241, 234)
    img = img.convert("RGB")
    back = back or img.getpixel((3, 3))
    if spec.get("fit") == "contain" and ratio:
        # Show the whole picture inside the card's shape instead of filling and cropping.
        w, h = img.size
        if h / w > ratio:
            w = round(h / ratio)
        else:
            h = round(w * ratio)
        canvas = Image.new("RGB", (w, h), back)
        canvas.paste(img, ((w - img.width) // 2, (h - img.height) // 2))
        img = canvas
    if spec.get("pad"):
        # Breathing room, so nothing sits against the card's edge.
        px, py = (spec["pad"], spec["pad"]) if isinstance(spec["pad"], (int, float)) else spec["pad"]
        px, py = round(img.width * px), round(img.height * py)
        canvas = Image.new("RGB", (img.width + 2 * px, img.height + 2 * py), back)
        canvas.paste(img, (px, py))
        img = canvas
    return img


class Element:
    sound = None
    grow, leave = 0.32, 0.16

    def __init__(self, spec, start, end):
        self.spec, self.start, self.end = spec, start, end
        self.tilt = spec.get("tilt", 0)

    def motion(self, t, overshoot=1.7, rise=60):
        """Shared entrance and exit: spring up into place, shrink away slightly."""
        tin, tout = clamp((t - self.start) / self.grow), clamp((self.end - t) / self.leave)
        scale = (0.8 + 0.2 * out_back(tin, overshoot)) * (0.94 + 0.06 * tout)
        opacity = clamp(tin * 3.5) * tout
        lift = (1 - out_cubic(tin)) * rise
        return scale, opacity, lift

    def sounds(self):
        return [(self.spec.get("sfx", self.sound), self.start, 1.0)] if self.spec.get("sfx", self.sound) else []


class Card(Element):
    """A page inside a window (or a bare cut-out strip), drifting slowly inside its frame."""
    sound = "pop"
    pad = 110

    def __init__(self, spec, start, end, bare=False):
        super().__init__(spec, start, end)
        self.cw = spec.get("width", 900)
        self.bar = 0 if bare or not spec.get("bar", True) else round(50 * max(0.66, min(self.cw / 900, 1)))
        self.frames = None
        if spec.get("video"):
            # A clip playing inside the window: its frames are read once, at the size they are shown.
            x, y, w, h = spec["crop"] if spec.get("crop") else (0, 0, *kit.probe(kit.path(spec["video"])))
            self.ch = round(self.cw * h / w) // 2 * 2
            raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{spec.get('video_in', 0):.3f}", "-t", f"{end - start + 0.2:.3f}", "-i", str(kit.path(spec["video"])),
                                  "-vf", f"crop={w}:{h}:{x}:{y},scale={self.cw}:{self.ch},fps={FPS}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
            size = self.cw * self.ch * 3
            self.frames = [Image.frombytes("RGB", (self.cw, self.ch), raw[i:i + size]) for i in range(0, len(raw) - size + 1, size)]
            if not self.frames:
                raise SystemExit(f"no frames could be read from {spec['video']} at {spec.get('video_in', 0)}s")
            source = self.frames[0]
            self.move = {"kind": "video"}
        else:
            source = load_picture(spec, spec.get("ratio"))
            self.ch = round(self.cw * spec["ratio"]) if spec.get("ratio") else round(self.cw * source.height / source.width) if bare else round(self.cw * 0.52)
            self.move = spec.get("motion", {"kind": "push"})
        self.shown = (source.width, source.height)
        if self.move["kind"] == "video":
            self.source = source
        elif self.move["kind"] == "scroll":
            self.source = source.resize((self.cw, round(source.height * self.cw / source.width)), Image.LANCZOS)
        else:
            # Push in: the page starts fitted to the frame and grows a little.
            cover = max(self.cw / source.width, self.ch / source.height) * self.move.get("to", 1.07)
            self.source = source.resize((math.ceil(source.width * cover), math.ceil(source.height * cover)), Image.LANCZOS)
        radius = spec.get("radius", 22 if bare else 30)
        size = (self.cw, self.bar + self.ch)
        self.chrome = window_chrome(self.cw, self.bar, self.ch, spec.get("url"), spec.get("theme") == "dark")
        edge = Image.new("RGBA", size, (0, 0, 0, 0))
        frame = spec.get("frame", 0)
        ImageDraw.Draw(edge).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius, outline=(255, 255, 255, 255 if frame else 70), width=frame or 2)
        self.chrome.alpha_composite(edge)
        self.mask = rounded_mask(size, radius)
        self.shadow = shadow_layer(size, radius, self.pad)
        self.chip = chip(spec["label"]) if spec.get("label") else None
        self.cx = spec.get("x", W // 2)
        self.cy = spec.get("y", 190) + size[1] / 2

    def content(self, life):
        if self.frames:
            return self.frames[min(int(life * (self.end - self.start) * FPS + 0.5), len(self.frames) - 1)]
        if self.move["kind"] == "scroll":
            span = max(self.source.height - self.ch, 0)
            y = round(span * (self.move.get("from", 0) + (self.move.get("to", 0.4) - self.move.get("from", 0)) * smooth(life)))
            return self.source.crop((0, y, self.cw, y + self.ch))
        zoom_to = self.move.get("to", 1.07)
        zoom = self.move.get("from", 1.0) + (zoom_to - self.move.get("from", 1.0)) * life
        ax, ay = self.move.get("anchor", [0.5, 0.35])
        w, h = self.cw * zoom_to / zoom, self.ch * zoom_to / zoom
        x, y = (self.source.width - w) * ax, (self.source.height - h) * ay
        return self.source.resize((self.cw, self.ch), Image.BICUBIC, box=(x, y, x + w, y + h))

    def layer(self, life):
        card = Image.new("RGBA", (self.cw, self.bar + self.ch), (0, 0, 0, 255))
        card.paste(self.content(life), (0, self.bar))
        card.alpha_composite(self.chrome)
        card.putalpha(self.mask)
        layer = self.shadow.copy()
        layer.alpha_composite(card, (self.pad, self.pad))
        if self.chip:
            layer.alpha_composite(self.chip, (self.pad + 22, self.pad - 50))
        return layer

    def draw(self, canvas, t):
        scale, opacity, lift = self.motion(t)
        life = clamp((t - self.start) / (self.end - self.start))
        drift = 5 * math.sin(2 * math.pi * t / 3.4)
        place(canvas, self.layer(life), self.cx, self.cy + lift + drift, scale, self.tilt + 0.3 * math.sin(2 * math.pi * t / 4.3), opacity)


class Strip(Card):
    """A piece cut out of a page, shown on its own."""

    def __init__(self, spec, start, end):
        super().__init__({"motion": {"kind": "push", "to": 1.0}, "y": 330, **spec}, start, end, bare=True)


class Photo(Card):
    """A photo or a cut-out as a white-framed print. Shows the whole picture unless told to fill."""

    def __init__(self, spec, start, end):
        super().__init__({"motion": {"kind": "push", "to": 1.04, "anchor": [0.5, 0.5]}, "frame": 7, "radius": 26, "fit": "contain", "pad": 0.06, "y": 200, **spec}, start, end, bare=True)


class Big(Element):
    """A tall image as a large rounded card, the picture behind it dimmed."""
    sound = "whoosh"
    pad = 120

    def __init__(self, spec, start, end):
        super().__init__(spec, start, end)
        source = Image.open(kit.path(spec["image"])).convert("RGB")
        if spec.get("crop"):
            x, y, w, h = spec["crop"]
            source = source.crop((x, y, x + w, y + h))
        self.cw = spec.get("width", 860)
        self.source = source.resize((self.cw, round(source.height * self.cw / source.width)), Image.LANCZOS)
        self.ch = min(spec.get("height", 1590), self.source.height)
        self.pan = spec.get("pan", [0.0, 0.6])
        radius = 46
        self.mask = rounded_mask((self.cw, self.ch), radius)
        self.edge = Image.new("RGBA", (self.cw, self.ch), (0, 0, 0, 0))
        ImageDraw.Draw(self.edge).rounded_rectangle([0, 0, self.cw - 1, self.ch - 1], radius, outline=(255, 255, 255, 80), width=3)
        self.shadow = shadow_layer((self.cw, self.ch), radius, self.pad, blur=44, drop=30, strength=190)
        self.chip = chip(spec["label"]) if spec.get("label") else None
        self.cy = spec.get("y", 170) + self.ch / 2
        self.dim = spec.get("dim", 0.55)

    def draw(self, canvas, t):
        scale, opacity, lift = self.motion(t, overshoot=1.2, rise=90)
        life = clamp((t - self.start) / (self.end - self.start))
        canvas.alpha_composite(Image.new("RGBA", (W, H), (6, 6, 10, int(255 * self.dim * opacity))))
        y = round(max(self.source.height - self.ch, 0) * (self.pan[0] + (self.pan[1] - self.pan[0]) * smooth(life)))
        card = self.source.crop((0, y, self.cw, y + self.ch)).convert("RGBA")
        card.alpha_composite(self.edge)
        card.putalpha(self.mask)
        layer = self.shadow.copy()
        layer.alpha_composite(card, (self.pad, self.pad))
        if self.chip:
            layer.alpha_composite(self.chip, (self.pad + 30, self.pad - 30))
        place(canvas, layer, W / 2, self.cy + lift, scale, self.tilt, opacity)


class Stat(Element):
    """A number sticker: small caps caption over a heavy figure, counting up as it lands."""
    sound = "tick"
    grow = 0.26

    def __init__(self, spec, start, end):
        super().__init__(spec, start, end)
        self.value, self.caption = spec["value"], spec.get("caption")
        self.bg, self.fg = tone(spec.get("tone", "neutral"))
        self.size = spec.get("size", 84)
        self.cx, self.cy = spec.get("x", W // 2), spec.get("y", 470)
        # The figure inside the text ("2,500" in "$2,500 a month"), with its thousands grouped the local way.
        number = re.search(rf"\d(?:[\d{re.escape(GROUPING)}]*\d)?", self.value)
        self.target = int(number.group().replace(GROUPING, "")) if number else 0
        self.grouped = bool(number) and GROUPING in number.group()
        self.count = spec.get("count", True) and self.target >= 100
        self.number = number
        self.final = self.sprite(self.value)

    def sprite(self, text):
        s = 2
        value_font, cap_font = font(self.size * s, "Heavy"), font(22 * s, "Bold")
        value_w = round(font(self.size * s, "Heavy").getlength(self.value))
        cap_w = sum(round(cap_font.getlength(c)) + 3 * s for c in self.caption.upper()) if self.caption else 0
        width = max(value_w, cap_w) + 68 * s
        height = (self.size + 46 + (34 if self.caption else 0)) * s
        pad = 60 * s
        img = Image.new("RGBA", (width + pad * 2, height + pad * 2), (0, 0, 0, 0))
        shape = Image.new("L", img.size, 0)
        ImageDraw.Draw(shape).rounded_rectangle([pad, pad + 14 * s, pad + width, pad + 14 * s + height], 30 * s, fill=140)
        img.putalpha(shape.filter(ImageFilter.GaussianBlur(20 * s)))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([pad, pad, pad + width, pad + height], 30 * s, fill=self.bg + (255,))
        y = pad + 22 * s
        if self.caption:
            x = pad + 34 * s
            for c in self.caption.upper():
                draw.text((x, y), c, font=cap_font, fill=self.fg + (150,))
                x += round(cap_font.getlength(c)) + 3 * s
            y += 34 * s
        draw.text((pad + 34 * s, y + (self.size * s) * 0.54), text, font=value_font, fill=self.fg, anchor="lm")
        return img.resize((img.width // s, img.height // s), Image.LANCZOS)

    def draw(self, canvas, t):
        scale, opacity, lift = self.motion(t, overshoot=2.4, rise=30)
        layer = self.final
        progress = (t - self.start) / 0.5
        if self.count and progress < 1:
            now = int(self.target * out_cubic(clamp(progress)))
            shown = f"{now:,}".replace(",", GROUPING) if self.grouped else str(now)
            layer = self.sprite(self.value[:self.number.start()] + shown + self.value[self.number.end():])
        place(canvas, layer, self.cx, self.cy + lift, scale, self.tilt, opacity)


class Deck(Element):
    """Small cards popping in one after another, like photos dropped on a table."""
    spots = [(215, 300, -6), (540, 285, 3), (865, 305, -3), (180, 520, 5), (420, 535, -4), (660, 515, 2), (900, 530, 6), (540, 410, -2)]
    step = 0.075

    def __init__(self, spec, start, end):
        super().__init__(spec, start, end)
        self.cards = []
        size, radius, pad = (290, 182), 20, 50
        mask = rounded_mask(size, radius)
        for item in spec["images"]:
            item = {"image": item} if isinstance(item, str) else item
            source = Image.open(kit.path(item["image"])).convert("RGB")
            if item.get("crop"):
                x, y, w, h = item["crop"]
                source = source.crop((x, y, x + w, y + h))
            cover = max(size[0] / source.width, size[1] / source.height)
            source = source.resize((math.ceil(source.width * cover), math.ceil(source.height * cover)), Image.LANCZOS)
            left = (source.width - size[0]) // 2
            card = source.crop((left, 0, left + size[0], size[1])).convert("RGBA")
            ImageDraw.Draw(card).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius, outline=(255, 255, 255, 255), width=5)
            card.putalpha(mask)
            layer = shadow_layer(size, radius, pad, blur=18, drop=14, strength=170)
            layer.alpha_composite(card, (pad, pad))
            self.cards.append(layer)

    def draw(self, canvas, t):
        tout = clamp((self.end - t) / self.leave)
        for i, layer in enumerate(self.cards):
            x, y, tilt = self.spots[i % len(self.spots)]
            tin = clamp((t - self.start - i * self.step) / 0.26)
            if tin <= 0:
                continue
            scale = (0.6 + 0.4 * out_back(tin, 2.0)) * (0.94 + 0.06 * tout)
            place(canvas, layer, x, y + 4 * math.sin(2 * math.pi * (t + i) / 3.1), scale, tilt + (1 - out_cubic(tin)) * 10, clamp(tin * 4) * tout)

    def sounds(self):
        # Each card gets a pop, pitched a little higher than the one before.
        return [("pop-small", self.start + i * self.step, 1.0 + 0.045 * i) for i in range(len(self.cards))]


KINDS = {"card": Card, "strip": Strip, "photo": Photo, "big": Big, "stat": Stat, "deck": Deck}


def plan_timeline(plan):
    """Where each segment lands, worked out from the plan alone (no rendering needed)."""
    looks, clock, timeline = plan.get("looks", {}), 0.0, []
    for seg in plan["segments"]:
        seg = {**looks.get(seg.get("look"), {}), **seg}
        length = round((seg["out"] - seg["in"]) * FPS) / FPS
        timeline.append({"start": round(clock, 3), "end": round(clock + length, 3), "zoom": seg.get("zoom", 1.0), "focus": seg.get("focus"), "layout": seg["layout"]})
        clock += length
    return timeline


def build(plan, timeline):
    configure(plan)
    elements = []
    for spec in plan.get("graphics", []):
        if "segment" in spec:
            # Tied to one segment (a clip's own moment has no place on the main recording's clock).
            start, end = timeline[spec["segment"]]["start"] + spec.get("after", 0), timeline[spec["segment"]]["end"]
        else:
            start = to_output(spec["from"], plan, timeline)
            end = to_output(spec["to"], plan, timeline, end=True)
        if end - start < 0.2:
            raise SystemExit(f"graphic {spec.get('kind')} {spec.get('image', spec.get('value', ''))} lasts {end - start:.2f}s; check its from/to against the segments")
        elements.append(KINDS[spec["kind"]](spec, start, end))
    return elements


def name_of(spec):
    return f"{spec['kind']} {Path(spec.get('image', spec.get('video', ''))).name or spec.get('value', '')}".strip()


def busy_edge(strip, along):
    """Is something cut off at this edge? True when a good part of the strip differs from its
    usual colour and the changes are sharp (text, interface), not the soft change of a photo."""
    grey = strip.convert("L")
    # One value per position along the edge: the strongest departure across the strip's thickness.
    lines = grey.resize((1, grey.height) if along == "y" else (grey.width, 1), Image.BOX)
    values = list(lines.getdata())
    usual = sorted(values)[len(values) // 2]
    odd = sum(abs(v - usual) > 30 for v in values) / len(values)
    sharp = sum(abs(a - b) > 14 for a, b in zip(values, values[1:])) / len(values)
    return odd > 0.08 and sharp > 0.02


def check(plan, timeline, elements):
    """Cheap tests that catch a bad overlay without anyone looking. Returns warnings as text."""
    warnings = []
    main = plan["main"]
    for number, element in enumerate(elements):
        spec, what = element.spec, f"#{number} {name_of(element.spec)}"
        length = element.end - element.start
        if length < 1.0 and spec["kind"] != "stat":
            warnings.append(f"{what}: on screen for only {length:.1f}s")
        if isinstance(element, Card) and not element.frames and spec.get("check", True) and spec.get("fit") != "cover":
            # 1. Is the picture squeezed so far that its text turns tiny? (screenshots are taken at double size)
            squeeze = element.shown[0] / element.cw
            # Only for a deliberate crop: that is a piece meant to be read. A whole page is there for its look.
            if spec["kind"] in ("card", "strip") and spec.get("crop") and squeeze > 2.4:
                warnings.append(f"{what}: {element.shown[0]}px of page squeezed into {element.cw}px, text will be about {round(32 / squeeze)}px tall. Crop tighter.")
            # 2. Does something run into the card's edge? A window may cut a page at the bottom; nothing else should be cut.
            for life in (0.0, 1.0):
                view = element.content(life)
                m = 20  # the clear margin a card should keep, in pixels
                sides = {"left": (view.crop((2, 0, m, view.height)), "y"), "right": (view.crop((view.width - m, 0, view.width - 2, view.height)), "y"),
                         "top": (view.crop((0, 2, view.width, m)), "x")}
                if not element.bar:
                    sides["bottom"] = (view.crop((0, view.height - m, view.width, view.height - 2)), "x")
                if element.move["kind"] == "scroll":
                    sides.pop("top")  # a scrolling page cuts whatever passes the top
                cut = [side for side, (strip, along) in sides.items() if busy_edge(strip, along)]
                if cut:
                    warnings.append(f"{what}: content runs into the {', '.join(cut)} edge{'s' if len(cut) > 1 else ''} ({'start' if life == 0 else 'end'} of its motion). Add \"pad\" or crop wider.")
                    break
        # 3. Does it sit on the speaker's head? Needs main.head_top: the top of their head (or hat) in the
        # recording, as a share of its height.
        if main.get("head_top") and spec["kind"] != "big":
            canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            middle = (element.start + element.end) / 2
            element.draw(canvas, middle)
            box = canvas.getchannel("A").point(lambda v: 255 if v > 200 else 0).getbbox()
            for slot in timeline:
                if slot["layout"] == "talk" and slot["start"] < element.end and slot["end"] > element.start and box:
                    zoom, focus = slot["zoom"], slot["focus"] or main["focus"]
                    crop_h = kit.window(main)[1] / zoom
                    head = (main["head_top"] * main["height"] - (main["height"] - crop_h) * focus[1]) / crop_h * H
                    if box[3] - head > 45:
                        warnings.append(f"{what}: reaches {round(box[3] - head)}px below the top of the speaker's head during {slot['start']:.1f}-{slot['end']:.1f}s. Move it up or use a look that leaves room.")
                        break
    return warnings


def proof(plan, out):
    """One image with every graphic as it will look, for a single glance before rendering."""
    timeline = plan_timeline(plan)
    elements = build(plan, timeline)
    tiles = []
    for number, element in enumerate(elements):
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        element.draw(canvas, element.start + min(1.2, (element.end - element.start) * 0.6))
        box = canvas.getbbox() or (0, 0, W, 200)
        box = (max(box[0] - 20, 0), max(box[1] - 20, 0), min(box[2] + 20, W), min(box[3] + 20, H))
        cut = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), (92, 84, 110))
        cut.paste(canvas.crop(box), mask=canvas.crop(box).getchannel("A"))
        scale = min(520 / cut.width, 520 / cut.height, 1)
        cut = cut.resize((round(cut.width * scale), round(cut.height * scale)), Image.LANCZOS)
        tile = Image.new("RGB", (cut.width, cut.height + 30), (40, 38, 48))
        tile.paste(cut, (0, 30))
        ImageDraw.Draw(tile).text((4, 3), f"#{number}  {element.start:.1f}-{element.end:.1f}s", font=font(19, "Bold"), fill=(255, 255, 255))
        tiles.append(tile)
    columns = 4
    rows = [tiles[i:i + columns] for i in range(0, len(tiles), columns)]
    sheet = Image.new("RGB", (columns * 540, sum(max(t.height for t in row) + 20 for row in rows)), (40, 38, 48))
    y = 0
    for row in rows:
        for i, tile in enumerate(row):
            sheet.paste(tile, (i * 540 + 10, y + 10))
        y += max(t.height for t in row) + 20
    sheet.save(out, quality=86)
    return check(plan, timeline, elements)


def to_output(source_time, plan, timeline, end=False):
    """Where a moment of the main recording lands in the finished video."""
    best = None
    for seg, slot in zip(plan["segments"], timeline):
        if seg["in"] - 0.02 <= source_time <= seg["out"] + 0.02:
            return min(max(slot["start"] + source_time - seg["in"], slot["start"]), slot["end"])
        # Not in the cut: an end snaps back to the previous kept moment, a start forward to the next.
        if end and seg["out"] < source_time:
            best = slot["end"]
        if not end and seg["in"] > source_time and best is None:
            best = slot["start"]
    return best if best is not None else (timeline[-1]["end"] if end else 0.0)


def render(plan, timeline, picture, out):
    """Overlay all graphics on the picture. Returns the sound effects to mix: (file, start, pitch)."""
    elements = build(plan, timeline)
    for warning in check(plan, [{**slot, "focus": seg.get("focus")} for slot, seg in zip(timeline, plan["segments"])], elements):
        print("  check:", warning)
    total = round(timeline[-1]["end"] * FPS)
    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(picture), "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[v]", "-map", "[v]", "-frames:v", str(total),
         "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)],
        stdin=subprocess.PIPE)
    blank = bytes(W * H * 4)
    for n in range(total):
        t = n / FPS
        active = [e for e in elements if e.start <= t < e.end]
        if not active:
            ffmpeg.stdin.write(blank)
            continue
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for element in active:
            element.draw(canvas, t)
        ffmpeg.stdin.write(canvas.tobytes())
    ffmpeg.stdin.close()
    if ffmpeg.wait() != 0:
        raise SystemExit("ffmpeg failed while laying the graphics over the picture")
    events = []
    for element in elements:
        for name, when, pitch in element.sounds():
            file, lead, gain = sound(name, plan)
            events.append({"file": file, "at": round(max(when + lead, 0), 3), "pitch": pitch, "gain": round(gain * plan.get("sfx_volume", 1.0), 3)})
    return events
