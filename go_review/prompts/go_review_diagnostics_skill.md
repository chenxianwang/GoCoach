---
name: go-review-diagnostics
description: Turn a Go (围棋) player's review notes into a cumulative, structured weakness-diagnosis archive. Use this whenever the user submits Go mistakes for analysis — a KataGo/AI review screenshot, a batch of positions with their own commentary, dictated/voice-transcribed review notes, or aggregate stats from a game-review report — and wants root-cause analysis rather than move-by-move commentary. Also use when they ask to append a new batch to an existing archive, update cumulative counts, or re-derive training priorities. Trigger on phrases like 复盘, 诊断档案, "review my mistakes", "add this batch", "错题本", "KataGo 复盘", or when they paste a position plus "what I was thinking was...". Do NOT use for teaching a single joseki/tesuji in isolation, or for questions with no review-notes input.
---

# Go Review Diagnostics

Build and maintain a **cumulative diagnosis archive** from a player's own review notes. The value is not commenting on individual moves — it is collapsing many scattered mistakes into a small number of recurring root causes, so training gets more focused every batch.

## Core principle

**Diagnose the root cause, not the symptom.** The player already knows *what* went wrong ("I didn't see the net"). The job is to find *why the search failed* and whether it is the same failure as last time.

A useful test: if two mistakes look different on the board but fail for the same reason, they belong in the same category. Say so explicitly — cross-batch recurrence is the single most valuable output of this skill.

## Weakness taxonomy (six categories)

Classify every mistake into one. If something genuinely fits none, open a new numbered category and say why.

| # | Category | Root cause | Typical symptom |
|---|---|---|---|
| ① | Calculation interruption / insufficient depth | Reading stops early — either at an unfavorable signal, or by not extending a favorable line | Missed push-cut-capture; stopped reading when atari'd; can't-live so gave up |
| ② | Missing technique (search gap) | A tesuji is not in the candidate library at all | Never considered net (枷), snapback, throw-in, ladder variants |
| ③ | Decision error (hope-based play) | Judgment rests on the opponent erring | Saw the weakness, didn't defend, "he probably won't notice" |
| ④ | Value misjudgment (gray zone) | Mis-values stones that are neither clearly alive nor clearly dead | Abandoned dead stones before extracting forcing moves; missed splitting/reduction fights |
| ⑤ | Attacking blindness | Defensive lens only; no proactive-offense search | Played a safe connecting slow move where a splitting attack was available; small point loss, large win-rate drop |
| ⑥ | Mode-switching failure (whole-game, highest priority) | Doesn't change style with the score | Ahead but still fighting/maximizing; leads get reversed |

**Category ⑥ outranks the others.** It is game-level, not move-level, and usually costs the most games. When aggregate stats show low 守成率 (lead-holding) with high 逆转率 (comeback), lead ⑥ in the analysis regardless of what the individual moves show.

## Workflow

### 1. Read the input

Inputs arrive in several forms — handle whichever appears:

- **Position screenshot with AI eval** — read the loss figure and win-rate delta. These separate error types: large point loss = blunder (usually ① or ④); small point loss with large win-rate drop = slow move (usually ⑤).
- **The player's own commentary** — this is the primary evidence. Their phrasing names the failure mode. "I stopped calculating" = ①. "I thought he wouldn't find it" = ③. "I gave up on those stones" = ④.
- **Dictated / voice-transcribed notes** — expect garbled repetition, misheard Go terms, and several distinct mistakes run together in one paragraph. Split them into separate rows. Decode terms by context (征子/飞罩/劫争/腾挪 are common victims of transcription). Do not ask the user to clean it up first.
- **Aggregate report stats** — per-move loss by phase, blunder rate, hold/comeback rates, game-shape classification.

### 2. Split and classify

One row per distinct mistake. Preserve the player's own wording in the "their read" column — it is data, and it lets them recognize the entry later.

For each row record: the position, their stated thinking/misjudgment, the root cause (your analysis, one line), the category, and the training target.

### 3. Separate principles from mistakes

Players often state a **general lesson** alongside specific errors ("absolute sente should be played first", "when a capture wins the game, capture early and thicken"). These are not mistakes — file them in a separate "principle-level conclusions" list under the batch. They are usually the player's own most valuable output; often a principle they derived is really the ground-level action for category ⑥.

### 4. Count, then compare across batches

Give a per-batch distribution, then update cumulative totals. **Explicitly name any category appearing in two or more consecutive batches** — recurrence proves it is structural rather than incidental, and this is what redirects training.

### 5. Re-derive training priorities

Order by cumulative frequency, except category ⑥ which stays near the top whenever it is in evidence. Each priority names a concrete drill, not a general aspiration.

## Output format

A single markdown document, appended to across sessions. Structure:

```
# 围棋复盘诊断档案

> Living document. Append a batch per submission; update cumulative counts at the end.

## Weakness taxonomy (six categories)     <- the table above, stated once

## Batch N · date
| # | Position | Their read / misjudgment | Root cause | Category | Training target |

### Principle-level conclusions from this batch
### This batch's distribution
### Cross-batch recurrence signal      <- only when something repeats

## Cumulative totals
| Category | Cumulative count |

## Training priorities (rolling)
```

Number rows `N-1`, `N-2` by batch so entries stay referenceable across sessions.

`references/worked_example.md` is a real two-batch archive in this format. Read it when creating a new archive or when unsure how much analysis a row warrants.

## When appending a new batch

Read the existing archive first. Then: add the new batch section, update cumulative totals, and re-check whether priorities have shifted. Never rewrite past batches — the history of what was diagnosed when is itself the record of progress.

## Analysis quality bar

- **Do not stop at the player's own diagnosis.** If they say "I need more life-and-death practice", check whether the real failure was reading depth, a missing tesuji, or a decision habit. Frequently the stated cause is one level too shallow.
- **Connect batches.** "This is the third time ④ has appeared" is worth more than any single-move explanation.
- **Distinguish ability from habit.** Errors of ability (can't read it) need drilling; errors of habit (③ and ⑥) can be fixed immediately and are far higher leverage. Say which one you're looking at.
- **Read the numbers honestly.** Small samples do not support trend claims. If two reports differ by a few percent across 30–70 games, say the difference is not statistically meaningful rather than narrating it as progress or decline.
- **Note the score context when available.** Whether a mistake happened while ahead or behind determines whether it belongs to ⑥. Ask the player to tag this going forward if they aren't already.

## Optional additions the player may ask for

- A pre-move checklist derived from their accumulated categories (e.g. "any stone in atari? does this move fill my own liberty? is that eye real? if I'm being atari'd, am I also atari-ing?").
- A rolling per-batch chart of category distribution once several batches exist.
- Translation of aggregate report stats into a phase-by-phase priority (per-move loss identifies where points bleed; win-rate impact identifies where games are actually decided — these often disagree, and win-rate impact wins).
