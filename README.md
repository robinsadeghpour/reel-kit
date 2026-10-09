# reel-kit

Turn a raw talking-head recording into a finished vertical video (Reels, TikTok, Shorts)
with Claude Code doing the edit: it picks the best take of each sentence, removes fillers,
breaths and dead air, adds zoom cuts and designed overlay cards, levels the sound, and then
tells you exactly which moments to listen to before you post.

It is a Claude Code plugin and a plain command-line toolkit in one repository. Everything
runs on your machine with ffmpeg and a local Whisper model. Editing needs no API keys.

```
footage/launch/recording.mp4      you record one take, with restarts and pauses
        │
        ▼  "edit the launch video"
out/launch/launch-v1.mp4          1080x1920, 30 fps, cut, with graphics, at -15 LUFS
```

## What it does

**Editing** (the `edit` skill, or the `reel` commands by hand)

- Finds every attempt at every sentence. A normal transcript hides restarts and "ums"; the
  analyzer splits the recording by loudness and transcribes each stretch on its own, so
  three attempts show up as three entries.
- Describes the whole edit as one JSON plan: which stretches play, in what order, at what
  zoom, with which graphics. Changing the video means changing that file.
- Cuts sound in one pass, so a zoom cut in the middle of a sentence has no audio edit.
- Removes breaths and closes hesitation pauses from the loudness of the recording.
- Draws a designed overlay layer: browser cards of real pages, number stickers that count
  up, photo prints, a scrolling phone-shaped card, a fan of small cards. Your colours and
  font if you set them.
- Proofs every graphic on one sheet before rendering, and warns about tiny text, content
  against an edge, and graphics sitting on your head.
- Checks the render: lengths, loudness, peak, and a word-by-word comparison of what should
  be in the cut with what a fresh transcription hears.

**Research** (the `research` skill; optional, needs two API keys)

- Scrapes recent posts of accounts you choose and ranks each against its own account's
  median, so you see breakouts and not just big accounts.
- Has a video model break down how the best ones are built, and measures which formats
  keep working when repeated.

## What it does not do

Claude cannot hear your audio or watch your video. It works from transcripts, loudness
measurements and still frames. That is enough for most of an edit and not enough to judge
how a cut sounds, so every edit ends with a short list of timestamps for you to listen to.
Treat that list as part of the result.

## Install

You need macOS or Linux (Windows through WSL), Python 3.10 or newer, and ffmpeg:

```
brew install ffmpeg          # macOS
sudo apt install ffmpeg      # Debian, Ubuntu
```

### As a Claude Code plugin

```
claude plugin marketplace add robinsadeghpour/reel-kit
claude plugin install reel-kit@reel-kit
```

Then, in Claude Code, in the folder where your videos should live:

```
/reel-kit:setup
```

That installs the Python packages into `~/.reel-kit/venv`, creates the project folder, and
asks how you want your videos (language, captions, look, words to keep). Afterwards put a
recording in `footage/<name>/` and say "edit the <name> video".

### As a plain toolkit

```
git clone https://github.com/robinsadeghpour/reel-kit
export PATH="$PWD/reel-kit/bin:$PATH"
reel setup
reel init ~/videos/reels
```

The skills are Markdown files under `skills/`. Any coding agent can follow
`skills/edit/SKILL.md`, and so can a person.

`reel setup` takes a few minutes. The transcription model (about 1.6 GB) downloads the
first time you analyse a recording.

## A project

```
reel.json            standing settings: language, colours, loudness, captions
STYLE.md             how you want your videos, in words; the edit skill reads and keeps it
footage/<name>/      your raw files for one video
out/<name>/          plan.json, the ledger, intermediate files, the renders
research/            seed accounts and what the research commands find
```

`STYLE.md` is what makes the second edit better than the first: when you send a cut back
("too many zooms", "that breath is loud"), the skill writes it down and starts from it next
time.

## Commands

| | |
|---|---|
| `reel setup` | install what the kit needs |
| `reel doctor` | check that everything is there |
| `reel init [folder]` | make a project folder |
| `reel sheet VIDEO OUT.jpg` | stills on one sheet; `--grid` adds a ruler for measuring |
| `reel analyze RECORDING OUTDIR` | the ledger: every phrase, take by take, with flags |
| `reel tighten PLAN` | remove breaths and hesitation pauses, write `plan.tight.json` |
| `reel proof PLAN` | draw and test every graphic, no render needed |
| `reel cut PLAN` | render; `--graphics-only` redoes just overlays and sound |
| `reel verify PLAN` | check the render and list where to listen |
| `reel shots OUTDIR name=url` | screenshot pages for cards |
| `reel words FILE OUT.json` | plain transcript with word times |
| `reel grade RECORDING OUT.jpg` | compare colour grades side by side |
| `reel scrape`, `watch`, `shape`, `formats`, `wall` | research |

`reel <command> --help` explains each. The plan format is documented in
[skills/edit/references/plan-format.md](skills/edit/references/plan-format.md), with a
small example in [examples/plan.json](examples/plan.json).

By hand, an edit is:

```
reel analyze footage/launch/recording.mp4 out/launch/analysis
# read the ledger, write out/launch/plan.json
reel tighten out/launch/plan.json
reel proof   out/launch/plan.tight.json
reel cut     out/launch/plan.tight.json
reel verify  out/launch/plan.tight.json
```

## Make it yours

In `reel.json`:

```json
{
  "language": "en",
  "captions": false,
  "loudness": -15,
  "theme": {"accent": "#C8F53C", "warn": "#FF5C4A", "ink": "#0C0C10", "paper": "#FFFFFF"},
  "font": "brand/YourFont-Variable.ttf"
}
```

Your own sound effects go in the project's `sfx/` folder as `pop`, `pop-small`, `whoosh`
and `tick` (`.wav` or `.mp3`).

## Research, and what it costs

`reel scrape` uses [Apify](https://apify.com) and `reel watch` uses the Gemini API, both
with your own keys in the project's `.env`. Both charge per use; start with small limits.
Scraping public posts is subject to the platforms' terms and your local law, and that call
is yours. The downloaded videos and transcripts are other people's work, kept to understand
how a video is built: the project's `.gitignore` keeps them out of git, and you should keep
them out of anything you publish.

## Limits

- Output is fixed at 1080x1920, 30 fps. Recordings of any shape are cropped upright around
  the speaker.
- Hesitation sounds are known for German and English. Other languages work, with less
  help: add your language's fillers under `"fillers"` in `reel.json`.
- The editing pipeline was built on German talking-head recordings and has been tested end
  to end in English on a synthetic recording. The research commands were run for real
  before they were made generic; the two that call paid APIs (`scrape`, `watch`) have not
  been re-run live since.
- HDR recordings (the default on recent iPhones) are not tone-mapped and may look washed
  out. Record in SDR, or convert first.
- Transcription runs on the CPU and takes about as long as the recording.
- The bundled sound effects are synthesised and plain. Bring your own if you care.

## Credits

Text is set in [Inter](https://rsms.me/inter/) (SIL Open Font License, see
`assets/fonts/OFL.txt`). Transcription is
[faster-whisper](https://github.com/SYSTRAN/faster-whisper), rendering is ffmpeg and
Pillow, screenshots are Playwright.

## Licence

MIT. See [LICENSE](LICENSE).
