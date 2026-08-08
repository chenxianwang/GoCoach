---
name: tsumego
description: Solve or review a Go problem (tsumego) step by step, especially 101weiqi Skill Test problems. Use when the user shows a Go problem position, asks how to solve one, gives a 101weiqi Q-number, asks why they got a problem wrong, or wants to drill a category of failure (traps, reading depth, off-book moves, timeouts).
---

# Solving a tsumego, step by step

Two jobs, and they need different handling:

- **Review** — the user names a problem they already attempted (a `Q-xxxxx` number, or
  "the one I got wrong yesterday"). Their own attempt and the crowd's move tree are cached
  locally. **Always start with the data, never with the picture.**
- **Coach** — the user shows a live position and wants to be walked through it. Run the
  protocol below with them, one step at a time. Do not give the answer first.

## Review: use the cache, not your eyes

```bash
cd ~/Desktop/ClaudeCode-Go && python3 -m tsumego explain 453591
```

The argument is the `Q-` number the site shows next to the board. This prints the correct
line, the move where the problem is actually decided, what the user played, and where they
went wrong — all from real data, so it is exact.

Reading stones off a screenshot is unreliable and you will sometimes be wrong about a
stone. When a Q-number is visible in the image, **use it** and treat the screenshot only as
a picture of a position you already know from the data. If there is no Q-number, say
plainly that you are reading the board by eye and may misread a stone.

Other useful commands:

```bash
python3 -m tsumego report --open        # the whole dashboard
python3 -m tsumego fetch --limit 10     # pull newer runs (slow: the site throttles hard)
```

The dashboard is also a page in the web app at `http://localhost:8765/tsumego`, where each
failure card opens a drill list with an "Understood" button.

## The protocol

There is a **~45 second clock per problem** in the Skill Test. The protocol is built for
that budget. Give the steps one at a time and wait for an answer — the point is to make the
user do the reading, not to watch you do it.

**1. State the goal in one sentence (5s).**
Whose group is at stake, and are you killing or living? "Black kills the white corner." If
the user cannot say this sentence, they are not reading yet, they are staring.

**2. Count the eyespace and name the shape (10s).**
How many points does the surrounded group actually enclose, and what standard shape is it?
This is the single highest-value step — see the vocabulary below. Naming the shape usually
hands you the vital point for free.

**3. Name up to three candidate moves — do not pick one yet.**
Almost every killing move in a 3-kyu problem is one of six ideas:

| | Idea | When |
|---|---|---|
| 点 | placement on the vital point | the eyespace has a centre |
| 扑 | throw-in sacrifice | to break a would-be eye into a false one |
| 挖 | wedge | between two stones that want to connect |
| 立 | descent to the first line | to steal the space underneath |
| 断 | cut | when the shape depends on a connection |
| 板 | hane | to reduce the space by one before placing |

Living is the mirror: expand the space, make the bulge, or take the vital point *first*
so the opponent cannot.

**4. For each candidate, read the opponent's *best resistance* — not their natural reply.**
This is the step that is actually being skipped. The opponent's best answer is usually the
move that makes your move look silly. Ask out loud: "if this is wrong, how does White
refute it?"

**5. Read to a terminal word.**
Not "that looks dead". Finish at one of: **dead / alive / ko / seki**. If you cannot say
one of those four words, the line is not finished and you may not play it.

**6. The veto, 3 seconds before you click.**
"What is the opponent's answer to this move?" If you cannot name it instantly, you have not
read it. Go back to step 4 with the next candidate.

**Clock rule.** If you reach ~35s with no terminal word, stop reading and play the vital
point of the shape you named in step 2. Burning the last 10 seconds has never once helped
(see the numbers below) and it costs you the next problem too.

## Shape vocabulary — the part that pays

Most misses are shape-recognition failures wearing a reading-failure costume. These should
be recall, not calculation:

- 直三 straight three — vital point is the centre. Dead.
- 曲三 bent three — vital point is the bend. Dead.
- 方四 square four — dead as it stands, no vital point needed.
- 丁四 T-shape four — vital point is the centre. Dead.
- 刀把五 (刀五) hammer-handle five — vital point is the 丁四 centre inside it. Dead.
- 梅花五 flower five — vital point is the centre. Dead.
- 板六 flat six — **alive**.
- 花六 rabbitty six — vital point is the centre. Dead.
- 直四 / 曲四 straight or bent four in a row — **alive**.
- 角上曲四 bent four in the corner — dead (the corner is special; know this one cold).
- The 2-2 point in the corner, the 1-2 placement, and the throw-in at 1-1 are corner-specific
  and worth drilling on their own.

When the user misses a problem, ask which of these the shape was. If they cannot name it,
that is the lesson — not the specific move.

## The user's own diagnosis

Snapshot from 500 attempted questions across 50 runs at 3级 (as of 2026-08-03). Re-run
`python3 -m tsumego report` for current numbers rather than quoting these as fact.

- **29% accuracy.** Best run ever 6/10; the mode is 3/10.
- **Traps are the biggest bucket (158 of 355 misses).** In **143 of those 158** the correct
  move was also the *most popular* move — so these are not clever traps that fool everyone,
  they are the second-most-obvious move being played without checking. Step 6 is aimed
  squarely at this.
- **Of the reading-depth misses, 60 of 96 go wrong on the user's *second* move** — the reply
  to the opponent's first resistance. Step 4 is aimed squarely at this.
- **132 of 355 misses** are on problems where over 60% of players found the first move.
- **Time buys nothing right now:** 45% accuracy when answering in under 10s, 31% at 10–20s,
  29% at 20–40s, **20% at 40–70s**. That is a selection effect (easy problems are fast), but
  it also means the long attempts are not converting — running to the buzzer is the
  signature of having no method, not of deep reading.
- 75% of the problems are Life & Death, so shape vocabulary is where the leverage is.

Because the test needs **8 of 10**, accuracy has to move a long way before the pass rate
does: 29% → 0.1%, 50% → 5%, 70% → 38%, 80% → 68%. Tell the user the honest number rather
than encouraging another attempt at the test.

## Tone

Do not hand over the answer at the first question. Ask the step, wait, react to what they
say. When they get it wrong, name **which step** they skipped — that is the transferable
lesson, and it is the whole reason the failure taxonomy exists.
