---
name: setup
description: Set up reel-kit on this machine and start a video project - install the tools, create the project folder, and record how this creator wants their videos (language, captions, look, words to keep, things that must never appear). Use this the first time someone wants to edit a reel or short with reel-kit, when `reel` reports something missing or is not set up, when they start a new channel or project folder, or when they want to change their standing preferences, brand colours, font or sounds.
---

# Set up reel-kit

Three things, in this order: the tools work, a project folder exists, and the creator's
preferences are written down. Each is skipped if it is already done, so check before doing.

`reel` is on the PATH while this plugin is enabled; if the shell does not find it, it is at
`${CLAUDE_PLUGIN_ROOT}/bin/reel`.

## 1. The tools

```
reel doctor
```

Read what it prints. Anything marked `missing` has its fix next to it.

- **ffmpeg missing:** the kit does not install it. Tell the user the one command for their
  system (macOS: `brew install ffmpeg`, Debian/Ubuntu: `sudo apt install ffmpeg`) and let
  them run it, since it may ask for a password.
- **Python environment or a package missing:** run `reel setup`. It creates
  `~/.reel-kit/venv`, installs the packages, and downloads a browser for screenshots only
  if there is no Google Chrome. It takes a few minutes the first time; say so before
  starting.
- **Transcription model not downloaded:** fine. It downloads (about 1.6 GB) the first time
  a recording is analysed. Mention it so a slow first run is not a surprise, or fetch it
  now with `reel setup --model`.

Run `reel doctor` again and carry on only when it ends with "Ready."

The research keys (`APIFY_TOKEN`, `GEMINI_API_KEY`) are optional and only matter for the
`research` skill. Do not ask for them here.

Windows is not supported directly; use WSL.

## 2. The project folder

One folder holds all of a creator's videos. If the current folder already has a
`reel.json`, this step is done. Otherwise ask where the project should live (the current
folder is the usual answer) and run:

```
reel init                # here
reel init ~/videos/reels # or somewhere else
```

It creates `footage/`, `out/`, `research/`, `reel.json`, `STYLE.md`, `.gitignore` and
`.env.example`, and never overwrites a file that is already there.

## 3. How they want their videos

This is the part that makes later edits good on the first try. Ask, do not assume, and keep
it short: a handful of questions, most with an obvious default. Where they have no opinion,
keep the default and move on. If they have a finished video they like (their own or
someone else's), look at stills of it (`reel sheet`) before asking: it answers half of
these.

What to find out:

1. **Language** they speak in the videos, and whether pages they show should be captured in
   that language. Sets `language` and `locale` in `reel.json`.
2. **Captions:** burned in by the edit, or added later in the app (the default)?
3. **Words:** which filler-like words are just how they talk and should stay ("honestly",
   "like", "basically")? Should the edit reorder and drop sentences for watch time, or keep
   everything in the order it was said?
4. **Look:** the kit's colours (a lime accent, coral for bad numbers), or their brand's?
   If they name colours or a font, set `theme` and `font` in `reel.json`.
5. **Sound:** are short sound effects on graphics welcome? Their own sound files?
6. **Off limits:** anything that must never be shown or said: internal numbers, a client's
   name, a screen with private data.
7. **Where it goes and how they record:** which platforms, one take with restarts or
   scripted, phone or camera.

Then write it down:

- `reel.json` gets the settings a script needs: `language`, `locale`, `captions`,
  `loudness`, `theme`, `font`, `sfx_volume`. Change only what they answered.
- `STYLE.md` gets everything in words. Fill in the blanks in the template, change or delete
  the lines marked (default) that they disagreed with, and remove the placeholder text.
  Keep their own phrasing where they gave it.

`reel.json`, complete:

```json
{
  "language": "en",
  "locale": "en-US",
  "captions": false,
  "loudness": -15,
  "sfx_volume": 1.0,
  "theme": {"accent": "#C8F53C", "warn": "#FF5C4A", "ink": "#0C0C10", "paper": "#FFFFFF"},
  "font": "brand/YourFont-Variable.ttf",
  "thousands": ",",
  "fillers": {"sounds": ["eeh"], "words": ["basically"], "prompt": "Um, eeh, so, basically."},
  "sfx": {"pop": {"lead": -0.03, "gain": 0.3}},
  "whisper_model": "large-v3-turbo"
}
```

Everything after `theme` is optional and normally absent. `fillers` matters for languages
other than German and English, where the kit does not know the hesitation sounds: `sounds`
are removed as hesitations, `words` make a phrase a filler when it is nothing else, and
`prompt` is a sample line that gets the transcriber to write hesitations down.

Check a changed theme before the first real edit: put one `stat` and one `card` in a
scratch plan and run `reel proof`, then look at the sheet with them.

## 4. Say what happens next

Tell them how a video gets made from here: put the raw recording (and any screen
recordings or clips) in `footage/<name>/`, then ask for an edit. If they already have a
recording, offer to start now with the `edit` skill. If they want to know what to make
videos about, that is the `research` skill, which needs two API keys and costs a little
per run.
