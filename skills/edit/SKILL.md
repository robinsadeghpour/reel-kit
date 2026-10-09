---
name: edit
description: Edit a raw talking-head recording into a finished vertical short-form video (Reels, TikTok, Shorts). Use this whenever the user drops footage into a folder and asks to edit, cut, clean up or "do the rest" on a video, mentions a recording, a talking head, retakes, fillers, ums, bad cuts, zoom cuts, cutaways, b-roll, callouts, captions, or a new version of an existing cut, even if they do not say "edit". Covers choosing takes, removing fillers and repeats, reordering for watch time, zoom cuts, cutaways to a second clip, designed overlay cards and number stickers, loudness, and checking the result.
---

# Reel edit

Turn a raw recording into a finished 1080x1920 video. The creator records one take with
restarts and pauses; the edit keeps the best version of each sentence and makes it
watchable.

The one fact that shapes everything here: **you cannot hear the audio or watch the video.**
You work from transcripts, loudness measurements and still frames. That is enough to do
most of the edit, and not enough to judge how a cut sounds. So the job has two halves:
do everything measurable carefully, then hand the creator a short, specific list of moments
to listen to. Never tell them a cut "sounds clean". Tell them what you measured.

## Before you start

The tools are one command, `reel`. It is on the PATH while this plugin is enabled; if the
shell does not find it, it is at `${CLAUDE_PLUGIN_ROOT}/bin/reel`. If `reel doctor` reports
something missing, or the project has no `reel.json`, run the `setup` skill first.

Work from the project root. A project looks like this:

| Path | What |
|---|---|
| `footage/<name>/` | The raw files for one video |
| `footage/<name>/assets/` | Screenshots, photos and clips collected for it |
| `out/<name>/plan.json` | The edit, as data. Changing the video means changing this file. |
| `out/<name>/analysis/` | The phrase-by-phrase ledger of the raw recording |
| `out/<name>/work/` | Intermediate files, safe to delete |
| `reel.json` | Standing settings: language, colours, loudness, captions |
| `STYLE.md` | How this creator wants their videos, in words |

**Read `STYLE.md` before every edit.** It holds this creator's preferences and what they
have sent back before. It overrides the defaults in this skill, and what they ask for in
the moment overrides both. When they react to a cut ("too many zooms", "why is that breath
so loud", "I love the cards"), add a dated line under "Learned from feedback" with what
they said, so the next edit starts from it.

## The steps

### 1. Look at what you were given

Probe every file (`ffprobe`), and make a sheet of stills of each so you know what is in the
frame: where the face sits, what a screen recording shows, where the usable part of a clip
is.

```
reel sheet footage/<name>/<recording> out/<name>/work/raw.jpg
reel sheet footage/<name>/<recording> out/<name>/work/grid.jpg --at 12 --grid
```

The second form is one large still with a ruler across it. Read `main.focus` (where the
face is) and `main.head_top` (the top of the head or hat, as a share of the height) off it,
and measure crops the same way. Decide crops from full-size frames, not from guesses.

Look at stills of any footage you plan to show while the speaker is *not* talking. Quiet
moments between takes look usable in a transcript and often are not (looking away, touching
their face).

Read what is on screen in any second clip. A news ticker or headline that is fine in its
own context can be wrong for a light video.

### 2. Listen properly: `reel analyze`

```
reel analyze footage/<name>/<recording> out/<name>/analysis
```

This is the step that makes the edit trustworthy, so do not replace it with a plain
transcript. A normal transcription smooths over restarts, doubled words and fillers: it
will report a recording as clean that contains an "um" and a sentence started twice. The
analyzer finds each stretch of speech from the loudness of the audio and transcribes it on
its own, so three attempts at a sentence show up as three entries, with exact start and
end times and the pauses inside each phrase. It takes about as long as the recording.

Read the whole ledger. The flags (`retake`, `fragment`, `filler`, `filler-inside`,
`restart-inside`, `unsure`) are hints, not verdicts. Short scraps are often misheard; when
a phrase matters and looks odd, transcribe that exact stretch again on its own, or with its
neighbour, and compare (`reel words` on a piece cut out with ffmpeg).

### 3. Choose takes

For each sentence the speaker meant to say, pick one version:

- Prefer a take that is complete in one go over stitching two halves together.
- When takes are otherwise equal, prefer the one where a key word is clearest. If the
  transcriber hears a word differently on every pass, that word is unclear in the audio.
- Take a later attempt over an earlier one only if it is actually better. Last is not
  automatically best.
- Remove hesitation sounds. Remove a phrase said twice in a row ("all the shows and the
  bigger shows" becomes "the bigger shows").
- Leave style words alone ("basically", "honestly", "like") unless `STYLE.md` or the
  creator says otherwise. They are how the person talks. Mention them once so they can
  decide.
- Do not rewrite what they say. If a sentence is factually off, tell them; do not cut
  around it to change its meaning.

**Order.** When someone talks freely rather than from a script, the best order is rarely
the order they said it in. If `STYLE.md` allows reordering for watch time (the default),
segments in the plan play in the order listed, wherever they come from in the recording.
A shape that works for an explainer:

1. The hook, as it was said.
2. What it is, in one sentence. Do not make people wait to learn the subject.
3. What they get: the money, the number, the result. This is the reason to keep watching.
4. What can go wrong. Tension in the middle holds better than a list of steps.
5. The steps, in the order someone would do them.
6. The closing line and the follow prompt.

Before moving a sentence, read the new sequence through: pronouns and words like "this",
"then", "because" and "also" point back at something, and that something must now come
before them. Drop sentences that repeat a point. List every sentence you dropped in the
handover so they can ask for one back.

### 4. Place the cuts

Where a cut lands decides whether it is audible.

- **Between phrases:** cut in the silence, and leave about a tenth of a second of room on
  each side. Cutting exactly at the first and last sound makes a cut feel abrupt.
- **Inside a phrase** (taking out a filler or a doubled word): use the pauses listed in the
  ledger (`islands`) or print the loudness around the spot (`analysis/envelope.npy`, one
  value per 10 ms) and cut at the quietest point. Give these cuts very short fades
  (`"fade_in": 0.012`, `"fade_out": 0.012`), because a normal fade would eat the word.
- Put inner cut points on the frame grid (multiples of 1/30 s). The renderer snaps to it,
  and a quiet gap is often only 20 ms wide.
- Every picture change should hide or mark something. Change the zoom level at each cut so
  a jump in the speaker's position reads as a deliberate cut.
- A false start with almost no pause ("And that... And the amount") reads as one clean
  sentence in a transcript. The analyzer flags these as `restart-inside` and prints where
  the real sentence begins; start the segment there.

### 5. Collect the visuals

Unless `STYLE.md` says the creator wants only their face, a cut that is just a talking head
with zooms is not finished. Go through the chosen sentences and give each named thing
something to look at:

- A product, project or site they name: its real page, captured with `reel shots`
  (`--tall` for a page worth scrolling, `--mobile` for a phone-shaped view, a narrower
  `--width` to make a text page larger). Look at every capture before using it. Loading
  screens, cookie notices, discount pop-ups and empty scroll-animation sections all turn
  up. For a game or a map, zoom in until the thing itself is visible. Do not redraw
  someone's logo.
- A number they say: a `stat` sticker.
- A list of stations: a counter tag on each ("3/7"), and a `deck` of all of them where the
  list is announced.
- A clip they supply: play it in a card (`video`), and give it its own moment with sound on
  a `backdrop` segment.
- Their own product: look in its project folder for finished store images or press shots
  first. They beat a screenshot.
- A thing with no page (a device, a place): a real photo as a `photo` card. Wikimedia
  Commons has freely licensed ones; search it through its API, prefer cut-outs with a
  transparent background, and write author and licence into
  `footage/<name>/assets/CREDITS.md` with a ready caption line, because most of those
  licences ask for the author to be named. A photo beats a text sticker.
- A repository: GitHub's own preview card
  (`https://opengraph.githubassets.com/1/<owner>/<repo>`), which shows name, description
  and stars at a glance. A cropped piece of the repository page is not recognisable.

For any page crop, ask what someone should recognise in one second (the name, the headline,
the number) and crop to that with room around it.

When the video is about something in the news or someone else's project, research it before
choosing visuals: find the primary source (the repository, the project page, the
announcement) and read it, not only articles about it. Compare what the speaker says with
what the source says. Where they differ, still edit what was said, but pick visuals that
show the real state, do not put a figure the source contradicts on a sticker, and list the
differences in the handover so a line can be re-recorded.

Check `STYLE.md` for anything that must never appear on screen before using a capture of
the creator's own screens.

### 6. Leave the colour alone

Do not grade the footage unless asked. A grade that looks good on a still easily reads as a
cheap filter in motion, and most creators would rather have what the camera recorded. Plans
have no `"grade"` by default.

If they do ask: `reel grade <recording> out/<name>/work/grades.jpg` writes a
before-and-after sheet for every grade the renderer knows. Start gentle, leave out the
vignette and the sharpening (those are what read as a filter), show them the sheet and let
them choose before rendering anything.

### 7. Write the plan

The plan format is in [references/plan-format.md](references/plan-format.md). Read it
before writing a plan. A small example is in `${CLAUDE_PLUGIN_ROOT}/examples/plan.json`.

### 8. Proof the graphics: `reel proof`

```
reel proof out/<name>/plan.json
```

Run this after writing the plan and before every render. It takes seconds, needs no
rendered video, and gives two things: a list of warnings, and `work/proof.jpg`, a single
sheet with every graphic drawn as it will appear. Read the warnings, then look at the
sheet. That one image is the whole visual check of the overlays, so never skip it.

The warnings cover the usual failures: a crop squeezed until its text is tiny, content
running into a card's edge, a graphic sitting on the speaker's head, a graphic on screen
too briefly. They are hints. A full-bleed picture (a map, an illustration) trips the edge
test; set `"check": false` on it once you have looked. The head test needs
`main.head_top` in the plan and is skipped without it.

On the sheet, check each graphic for: is the thing recognisable, is the text readable at
this size, does anything touch an edge or get cut, does the label say something true.

### 9. Take out breaths and hesitations: `reel tighten`

```
reel tighten out/<name>/plan.json
```

People speak with pauses and audible inhales, and they hear both in a cut. Choosing
complete takes is not enough. This step works on the loudness of the recording: inside
every stretch the plan keeps it removes bursts that are only a breath, closes pauses longer
than a natural one, and writes `plan.tight.json`. From here on, proof, render and verify
**that** file; keep editing `plan.json` and run `reel tighten` again after each change.

What it cannot do is hear a stutter inside a word, and neither can the transcriber, which
returns a clean sentence either way. So:

- List the small sounds between words yourself (bursts of 0.1 to 0.6 s that a separate
  transcription cannot name) and decide each one. Before putting one in `"tighten":
  {"drop": [[from, to]]}`, check the ledger's word times: a burst straight after a word is
  often the next word.
- After rendering, read the whole transcript `reel verify` heard and compare it sentence by
  sentence with what was said. A missing or changed word means a drop or a cut took it.
- Tell the creator plainly which hesitations you could not judge, with timestamps.

### 10. Render: `reel cut`

```
reel cut out/<name>/plan.tight.json
reel cut out/<name>/plan.tight.json --graphics-only
```

The second form keeps the cut picture from the last run and redoes only the graphics and
the sound. Use it whenever only the `graphics` list changed.

Picture and sound are built separately. Sound is cut in one pass, so two segments that
follow each other in the recording have no audio edit between them. That is what lets a
zoom cut land in the middle of a sentence without a click.

### 11. Check: `reel verify`

```
reel verify out/<name>/plan.tight.json
reel sheet out/<name>/<output>.mp4 out/<name>/work/final.jpg --every 0.5
```

`verify` confirms picture and sound are the same length, measures loudness and peak,
compares the words that should be in the cut with what a fresh transcription hears, and
writes a contact sheet. Look at the contact sheet yourself.

The dense sheet (two stills a second) is for finding moments where the speaker looks down
at notes or away. Hide those under a `big` card or move a cut; a glance at a sentence end
can stay.

Read the "listen here" list critically. Most entries are the transcriber disagreeing with
itself about spelling. The ones that matter are a word that went missing or appeared twice,
especially next to a cut you made inside a phrase. Pass those on.

### 12. Hand over

Tell the creator: where the file is, what you removed (every dropped sentence), what you
measured (length, loudness, peak), which sounds play where, and the specific timestamps
they should listen to and why. Keep the version number going (`<name>-v5.mp4`) and delete
the previous one once the new one is checked.

## Defaults when `STYLE.md` is silent

These came from one creator's reactions to real cuts, so they are a sensible starting point
and nothing more.

- **Captions off.** Many creators add them in the app. The renderer can burn them in
  (`"captions": true`); turn them on only if asked.
- **The voice and a clip's own sound never play together.** A clip running under a voice is
  tiring even when quiet. They take turns: the clip is silent while the person talks, and
  gets its own moment with sound.
- **When the video is about something you can watch, let it play.** A clip that is the
  subject should run for several seconds with its own sound. Two seconds read as not
  impressive.
- **Something changes on screen by about three seconds in**, and regularly after.
- **Zoom cuts for emphasis.** Punch in on the phrase that carries the point: a number, a
  name, the surprising part.
- **One look, used consistently.** The graphics kinds in the plan format are a system:
  browser cards that spring in and drift, number stickers, a dark tag with a counter, big
  phone-shaped cards over a dimmed picture, a fan of small cards for a list. Keep to it
  rather than inventing a new look per video. Colours and typeface come from `reel.json`.
- **The head stays in view where possible.** Prefer a card above the speaker to replacing
  them, except when the clip is the moment. Keep graphics above the eyes; captions added
  later sit lower in the frame.
- **Sound effects are quiet and short**, tied to a graphic appearing, and mixed after the
  voice is levelled.
- **Sound must not overdrive.** Peak at or below -2 dBFS, loudness around -15 LUFS.
- **Clips from films or shows:** a couple of seconds at most, and say once that the
  platform may flag it, more so with sound.

## Things that go wrong

- Trusting one transcript. It hides fillers and repeats. Use the analyzer.
- Rendering without looking at the overlays first. Run `reel proof` and look at its sheet.
- Checking the finished audio with a loudness threshold taken from the finished audio.
  Compressed sound has a high floor, so phrases split in odd places and scraps get
  misheard. Re-listen to a suspicious stretch as one wider window before believing it.
- A caption or clip chosen for one layout hanging over into the next.
- Using a clip's on-screen content without reading it.
- Dropping a "breath" that was a word. Check word times before every manual drop.
- Assuming ffmpeg can draw text. Many builds cannot, so the kit never asks it to: all text
  is drawn as images. If you need a one-off label, draw it with Pillow.

## Limits to be honest about

The scripts measure; the judgement in steps 3 and 4 is where mistakes come from. When a cut
is a guess, say so. The analyzer knows hesitation sounds for German and English; for other
languages it still separates takes, but add the language's fillers under `"fillers"` in
`reel.json` and expect to read the ledger more carefully.
