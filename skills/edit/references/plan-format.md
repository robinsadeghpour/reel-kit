# Plan format

`out/<name>/plan.json` describes the whole edit. `reel cut` renders it; `reel verify` checks
the result against it. All times are seconds in the source file. All file paths start at
the project root (the folder with `reel.json`).

```json
{
  "output": "launch-v4.mp4",
  "main": {"file": "footage/launch/recording.mp4", "focus": [0.45, 0.75], "head_top": 0.36},
  "clips": {
    "demo": {"file": "footage/launch/screen.mp4", "crop": [292, 121, 726, 408]},
    "page": {"file": "footage/launch/assets/page.png"}
  },
  "looks": { ... },
  "segments": [ ... ],
  "graphics": [ ... ]
}
```

- `output`: the file name of the render, written next to the plan.
- `main.file`: the recording. Its size is measured for you. Any shape works: the speaker
  fills an upright 9:16 frame, the largest such piece of the recording.
- `main.focus`: where the face is, as `[x, y]` from 0 to 1. It decides which part of the
  recording stays in frame, both when a wide recording is cropped upright and when a zoom
  crops further. `[0.5, 0.5]` is the centre; `[0.45, 0.75]` keeps a face that sits low and
  slightly left. Read it off `reel sheet ... --at <second> --grid`.
- `main.head_top`: optional, the top of the speaker's head or hat as a share of the
  recording's height. `reel proof` uses it to warn when a graphic sits on them.
- `clips`: second sources. A `.png` or `.jpg` is held as a still. `crop` is
  `[x, y, width, height]` in the clip's own pixels, optional. Measure it on a full-size
  frame.

Anything in the project's `reel.json` applies to every plan and can be set again here for
one video: `language`, `captions`, `loudness` (target in LUFS, -15), `theme`, `font`,
`sfx_volume`, `sfx`, `thousands`.

- `grade`: optional and normally absent. A name from `GRADES` in `scripts/cut.py`, or an
  ffmpeg filter chain. Only when the creator asks for one.

## Segments

Segments play in the order listed. Each one is a stretch of the main recording, `in` to
`out`, plus how it looks and what is heard.

| Field | Meaning |
|---|---|
| `in`, `out` | Source times in the main recording. Their difference is the segment's length. |
| `layout` | `talk` for the speaker, `backdrop` for a clip's own moment. `panel` and `full` are plainer alternatives, below. |
| `zoom` | Punch-in for `talk`. 1.0 wide, about 1.12 mid, about 1.32 tight. |
| `zoom_to` | Optional. The zoom moves evenly from `zoom` to this over the segment (a slow push in, or out). `reel tighten` carries it through its cuts. |
| `focus` | Optional. Overrides `main.focus` for this segment. |
| `look` | Optional. The name of an entry in `looks`, instead of repeating zoom and focus. |
| `tighten` | `false` keeps this segment's pauses exactly as written (a reaction, a beat before a punchline). |
| `clip`, `clip_in` | For `backdrop`, `panel` and `full`: which clip, and where in it to start |
| `sound` | Omit for the voice. `"clip"` plays the clip's own sound instead. |
| `clip_volume` | Level of the clip's sound when `sound` is `"clip"` |
| `fade_in`, `fade_out` | Override the audio fades (seconds) at this segment's edges |
| `line` | Optional, ignored by the renderer. A good place to note what is said, so the plan can be read. |

Looks are defined once at the top of the plan:

```json
"looks": {
  "wide":  {"zoom": 1.0},
  "card":  {"zoom": 1.0},
  "cardB": {"zoom": 1.08, "focus": [1.0, 0.0]},
  "mid":   {"zoom": 1.15, "focus": [0.85, 0.55]},
  "tight": {"zoom": 1.3,  "focus": [0.85, 0.5]}
}
```

`card` and `cardB` are for stretches with a card above the speaker's head: at zoom 1.0
nothing is cropped, and 1.08 anchored to the top pushes the head lower, so both leave the
top third free. Switch between the two to mark a cut under a card. The focus values above
are one person's framing: work yours out from three stills with a grid.

## Two rules the renderer relies on

**Segments that touch are not cut in the sound.** If one segment's `out` equals the next
one's `in`, the audio runs through untouched. Use this for zoom cuts and for switching
layout in the middle of a sentence:

```json
{"in": 101.38, "out": 102.94, "layout": "talk", "zoom": 1.0},
{"in": 102.94, "out": 104.59, "layout": "talk", "zoom": 1.32}
```

**Everything is rounded to the frame grid** (1/30 s) so picture and sound stay the same
length. For a cut inside a phrase, choose a value already on the grid at the quietest
point, and keep its fades short:

```json
{"in": 74.62, "out": 75.80, "layout": "talk", "zoom": 1.12},
{"in": 76.4333, "out": 78.2333, "layout": "talk", "zoom": 1.0, "fade_in": 0.012, "fade_out": 0.012},
{"in": 79.10, "out": 80.10, "layout": "talk", "zoom": 1.32, "fade_in": 0.012}
```

That example removes an "um" (75.80 to 76.43) and a doubled phrase (78.23 to 79.10).

## Tighten

`reel tighten` reads optional settings under `"tighten"`:

```json
"tighten": {"max_pause": 0.22, "pause": 0.11, "breath_peak": -30, "drop": [[41.20, 41.52]]}
```

| Field | Meaning | Default |
|---|---|---|
| `max_pause` | Pauses longer than this are shortened | 0.22 s |
| `pause` | What a shortened pause is left at | 0.11 s |
| `breath_peak` | A burst that never gets louder than this is a breath and is removed | -30 dB |
| `drop` | Spans of the recording to remove whatever sounds in them (a stutter, a click) | none |

## Graphics

The `graphics` list is the designed layer on top of the picture. Each entry has a `kind`,
and `from` and `to` in seconds of the main recording (the same clock as the segments), so
graphics follow the words even when cuts move. A time that falls in a removed stretch snaps
to the nearest kept moment.

```json
{"kind": "card", "image": "footage/launch/assets/agency.png", "url": "example.agency", "tilt": -2,
 "motion": {"kind": "push", "anchor": [0.25, 0.3]},
 "label": {"n": "1/7", "title": "The agency"}, "from": 24.05, "to": 30.70}
```

| Kind | What it is | Fields |
|---|---|---|
| `card` | A page or a playing clip in a browser window above the speaker's head | `image` or `video`, `url`, `theme` (`dark` for dark pages), `width` (900), `x`, `y` (top, 190), `ratio` (height of the page area as a share of width, 0.52), `crop`, `tilt`, `motion`, `label` |
| `photo` | A photo or cut-out as a white-framed print | `image`, `width`, `ratio`, `x`, `y`, `tilt`, `label`; shows the whole picture (`"fit": "cover"` to fill instead); a transparent cut-out is trimmed and laid on `background` |
| `strip` | A piece cut out of a page, no window | `image`, `crop`, `width`, `y`, `tilt` |
| `big` | A tall image as a large card, picture dimmed behind | `image`, `pan` `[from, to]` as shares of the scrollable height, `width` (860), `label` |
| `stat` | A number sticker | `value`, `caption`, `tone` (`good` accent colour, `neutral` white, `bad` warning colour, `dark`), `size`, `x`, `y`, `tilt`, `count` (false to stop it counting up) |
| `deck` | Small cards popping in one after another | `images` (paths, or `{"image", "crop"}`) |

Positions are pixels in the 1080x1920 frame; `x` is a centre, `y` a top edge (for `stat`,
its centre). Every `crop` is `[x, y, width, height]` in the image's own pixels.

A `card` can play a clip instead of showing a still: give `video`, `video_in` (seconds
into the clip) and optionally `crop`. For a clip's own moment with its sound, make the
segment `"layout": "backdrop"` (the clip blurred and darkened, with `"sound": "clip"`), and
put the card on it with `"segment": <index>` instead of `from` and `to`, since that moment
has no place on the main recording's clock. `in` and `out` of such a segment only set its
length:

```json
{"in": 0, "out": 5.4, "layout": "backdrop", "clip": "demo", "clip_in": 3.32, "sound": "clip", "clip_volume": 0.9}

{"kind": "card", "video": "footage/launch/screen.mp4", "crop": [292, 121, 726, 408], "video_in": 3.32,
 "url": "example.com", "width": 1000, "y": 620, "tilt": 0,
 "label": {"n": "LIVE", "title": "example.com"}, "sfx": "whoosh", "segment": 3}
```

Start `clip_in` at a pause in the clip's sound, so it does not open mid-word. Run
`reel analyze` on the clip to get its pauses. The index in `"segment"` counts the segments of
`plan.json` from 0; `reel tighten` keeps it pointing at the same segment when it splits others.

Any card, strip or photo takes `"pad": 0.05` (or `[sideways, upright]`, as shares of the
picture) to put room in the page's own background colour around a crop, so text does not
sit against the edge. `"check": false` silences `reel proof` for one graphic.

Two photos with an arrow between them (this thing becomes that thing):

```json
{"kind": "photo", "image": ".../console.png", "width": 380, "ratio": 1.2, "x": 290, "y": 190, "tilt": -4, "label": {"title": "Console"}, "from": 2.0, "to": 4.02},
{"kind": "stat", "value": "→", "tone": "good", "size": 64, "x": 540, "y": 420, "count": false, "sfx": null, "from": 2.45, "to": 4.02},
{"kind": "photo", "image": ".../laptop.jpg", "fit": "cover", "pad": 0, "width": 380, "ratio": 1.2, "x": 790, "y": 190, "tilt": 4, "label": {"title": "Your laptop"}, "from": 2.75, "to": 4.02}
```

`motion` is `{"kind": "push", "anchor": [x, y], "to": 1.07}` (slow push in towards a point)
or `{"kind": "scroll", "from": 0.0, "to": 0.4}` (scroll down a tall screenshot; make those
with `reel shots --tall`). `label` is the dark tag on a card: `n` is the counter in the
accent colour ("3/7"), `title` the name, `sub` a quieter note.

A `stat` whose figure is 100 or more counts up as it lands. Write the figure the way the
viewer reads it ("2,500", "2.500 €"); the thousands separator follows the plan's language,
or `"thousands"`.

Placement that works when the speaker's head starts about a third of the way down:

- A full-width card at the default position ends just above the head. Two small cards side
  by side: about 480 wide at `x` 300 and 765, the second 130 lower.
- A number on its own: `y` about 460. A number on the corner of a card: `x` 250, `y` 700,
  `size` 70, `tilt` -5.
- Keep graphics above the eyes. Captions added later sit lower in the frame.
- Under a `big` card the speaker is hidden, which also hides a jump cut. Good place to
  join two takes.

If the speaker sits higher in the frame, there is less room above: use narrower cards, the
`card`/`cardB` looks, or `big`. Let `reel proof` tell you.

### Sounds

Each graphic brings its own quiet sound: `pop` for a card, `whoosh` for a big card, `tick`
for a number, rising `pop-small` for a deck. Set `"sfx": null` on one to silence it, name
another (`"sfx": "whoosh"`), or set `"sfx_volume": 0.6` at the top of the plan to turn them
all down.

The kit's sounds are synthesised. To use your own, put `pop.wav` (or `.mp3`),
`pop-small`, `whoosh` and `tick` in the project's `sfx/` folder; any other name there can
be used too. A sound's timing and level are set under `"sfx"` in `reel.json`:

```json
"sfx": {"pop": {"lead": -0.03, "gain": 0.3}}
```

`lead` is when the file starts relative to the graphic appearing (negative: earlier, so its
loud part lands on the moment), `gain` how loud it is mixed (1.0 is the file as it is,
which is far too loud under a voice).

### Colours and type

`"theme"` sets the four colours everything is drawn in: `accent` (good numbers, counters),
`warn` (bad numbers), `ink` (dark tags, text on light), `paper` (text on dark, neutral
stickers). Text on a coloured sticker turns dark or light by itself. `"font"` is a path to
a font file; one with a weight axis (a variable font) gives the full range of weights.

### Trying a design

Draw one test frame of a new design before a full render: `reel proof` does this for every
graphic in the plan. A full render takes minutes; proof takes seconds.

## Plainer layouts

`panel`, `full` and `sticker` came before the graphics layer and are still there for a
quick cutaway. They have no motion and no design; prefer `graphics`.

- **panel**: the speaker, with the clip in a white-edged box above their head.
  `"box": {"width": 1000, "y": 120}` places it. Silent unless `sound` is `"clip"`.
- **full**: the clip fills the width over a blurred copy of itself. With `"sound": "clip"`
  this is the clip's own moment.
- `"sticker": {"file": "...png", "y": 250}` on any segment lays a ready-made image over it.

## Captions

`"captions": true` transcribes the finished sound and burns in short chunks of two or three
words. `"caption_y": {"talk": 1250}` sets the height per layout (the centre of the line, in
pixels from the top). `"spelling": {"heard": "Right"}` corrects single words the
transcriber gets wrong, `"phrases": {"two words heard": "TwoWords"}` runs of them. A clip's
own sound is never captioned. Off by default because many creators add captions in the app.
