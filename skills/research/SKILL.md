---
name: research
description: Find out what works in short-form video for a creator's niche, with numbers - scrape recent Reels and TikToks of accounts they pick, rank every post against its own account's median, have a video model break down how the breakouts are built (hook, structure, editing, what is copyable), find formats that repeat, and turn that into a content plan. Use this when someone asks what to post, which formats or hooks work, wants competitor or reference research, outlier or viral video analysis, a content plan or schedule for Reels, TikTok or Shorts, or wants one of their own edits analysed the same way.
---

# Reel research

The question is "what should I make, and how should it be built", answered from what
actually performed for accounts like this creator's, not from general advice.

The measure that matters: **a video's plays divided by the median plays of the same
account.** A million plays on a ten-million account is an ordinary Tuesday; fifty thousand
on an account that usually gets five thousand is a breakout. Everything here ranks by that
multiple.

`reel` is on the PATH while this plugin is enabled; if the shell does not find it, it is at
`${CLAUDE_PLUGIN_ROOT}/bin/reel`. Run from the project root (see the `setup` skill if there
is no `reel.json`).

## Before spending anything

Two of the steps call paid services with the creator's own keys, kept in the project's
`.env` (never in git; `.env.example` shows the names):

- `APIFY_TOKEN` for `reel scrape`. Apify charges per result returned. The run prints its
  cost when it finishes.
- `GEMINI_API_KEY` for `reel watch`. Charged per video watched.

Say what a step will roughly do (how many accounts, how many posts, how many videos)
before running it, and start small: a first scrape with `--limit 15`, a first watch with
`--top 10`. `reel watch` skips videos it has already analysed, so going wider later costs
only the difference. A scrape fetches everything again each time, so widen it deliberately.

Two more things to say once, plainly. Scraping public posts is subject to the platforms'
terms and to local law, and that judgement is the creator's. And the downloaded videos,
captions and transcripts are other people's work: they are here to understand how a video
is built, not to be reused or published. The project's `.gitignore` keeps them out of git.

## The steps

### 1. Choose the accounts: `research/seeds.json`

Ask who they would like to learn from: accounts in their niche, a size or two above them,
and a few whose style they simply like. Fifteen to forty accounts gives enough to see
patterns. Accounts that post often are more useful than huge ones.

```json
{
  "instagram": [{"handle": "someone", "group": "peers", "lang": "en"}],
  "tiktok":    [{"handle": "someone", "group": "peers", "lang": "en"}]
}
```

`group` and `lang` are free labels (peers, aspirational, german) that stay on every post so
results can be filtered. If they give you only a niche, propose accounts and have them
confirm: do not guess handles, check that each exists.

Also write `research/brief.md`: two or three sentences about the creator for the model
that watches the videos (what they make, how they record, how much editing they can do,
what they will not do). It makes "what to copy" specific.

### 2. Scrape and rank: `reel scrape`

```
reel scrape --limit 25
```

Writes `research/outliers.json`: every post with its plays, its account's median, and the
ratio. Posts under three days old are left out of the median (their counts are still
climbing), pinned posts too, and an account needs five posts to get a median at all.
Accounts that were not found are listed at the end; fix the handle or drop them.

`--platform instagram` runs one platform, `--rank-only` re-ranks from what is stored.

### 3. Watch the breakouts: `reel watch`

```
reel watch --top 20
reel watch --top 20 --group peers --min-ratio 3
```

Downloads the best outliers (at most two per account by default, so one creator does not
fill the list) and has a video model describe each: format, the first frame and first
line, how fast the topic becomes clear, the beats with timestamps, cuts and zooms and
captions, the call to action, whether it is part of a series, and what one person could
copy. Results go to `research/analyses/`, a sheet of stills to `research/frames/`.

Treat the analyses as a careful viewer's notes, not as measurements. Counts of cuts are
approximate, and "why it outperformed" is an informed guess: the model says so itself when
it cannot know. Look at the stills for anything a decision rests on.

`reel watch --file out/<name>/<video>.mp4` analyses one of the creator's own edits the same
way, which is a useful outside view before publishing.

### 4. Measure and lay it out: `reel shape`, `reel wall`

```
reel shape
reel wall
```

`shape` measures length and cuts per minute of every downloaded video (a cheap stand-in
for how much editing a format needs) and writes a strip of six stills each. `wall` builds
`research/wall.html`: every breakout as a card with its numbers, first line, structure and
what is worth copying; downloaded videos play in place. Have the creator open it and tell
you which ones they like and which they would never make. Their reaction matters more than
the ranking: a format they will not enjoy recording does not get made.

### 5. Find formats that repeat: `reel formats`

One breakout is luck until it repeats. Look through the outliers for premises one creator
has used again and again (a numbered series, the same test with a new subject, the same
opening line), and write each down in `research/formats.def.json`:

```json
[{"key": "numbered-mistakes",
  "name": "Mistake number N of 10",
  "handles": ["someone"],
  "match": "^MISTAKE NO\\.",
  "how": "One real mistake per episode, with the number that made it hurt. Desk footage, voice over the top."}]
```

`match` and `exclude` are patterns tested against the caption, `since` a start date.
`reel formats` then counts the episodes, how many beat twice the account's usual, and how
many fell below half. A format worth building on has several episodes, a good share above
2x, and few or none below half. Run `reel wall` again to show them on top of the page.

### 6. Turn it into a plan

Write the plan as a short document in the project (`plan/content-plan.md` is the usual
place) once the creator has reacted to the wall. What it should hold:

- **Positioning** in two sentences: who is talking, to whom, about what. Mark it as a
  proposal until they confirm it.
- **Three or four formats**, each with what it is, the reference that shows it works (who,
  how many episodes, how they did), and what it needs to record. Prefer formats one person
  can make with a phone and a screen.
- **A schedule** for the first two weeks with real dates, and when each batch is recorded.
- **Rules** they agreed to: what is scripted and what is free talk, what gets fact-checked
  before it is said, anything legal for their country.
- **What to measure**, and when to judge: against their own median, after enough posts to
  have one.

The references supply structure, never words. Scripts are the creator's own material in
their own voice; every fact in one is a real fact of theirs. Leave a marked blank where
only they know the number rather than inventing one.

## What the numbers cannot tell you

- A scrape is a snapshot of recent posts. A median from eight posts is rough.
- Plays are not the creator's goal unless they say so. Ask what they want from the channel
  (clients, sales, an audience) and weigh formats by that.
- Two accounts with the same handle on both platforms often perform very differently on
  each. Compare within a platform.
- What worked in one language or market may not carry over. Say when a conclusion rests on
  accounts unlike theirs.
