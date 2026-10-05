# NFL Lab

One margin model, checked against the line. The 2022–2025 seasons were graded once and came up short: **48.8%** on spreads, **51.0%** on totals. That record stays as history. The live test is the 2026 season, starting week 5 (Thursday, October 8).

Picks are saved with a timestamp before kickoff. The line at that moment is ESPN DraftKings. The line just before kickoff is ESPN DraftKings again. Same book, both times. Scores come from nflverse.

This is a research ledger. It is not betting advice.

The box dump this PR started from is in [`pipeline/`](pipeline/) (branch `nfl-lab/box-pipeline`, commit `1c6993f`): team EPA, the frozen backtest, week-5 previews, and week-4 recaps. Run that copy with `python -m src.run` from `pipeline/`. The live card and the site use `uv run nfl-lab` from the repo root.

## Proof

Locked rule: the model must be at least **2 points** off the spread, or **3 points** off the total. Tuned on 2016–2021 only. Details, including the three-part 2026 bar, are in [PRODUCT.md](PRODUCT.md). Plain-language definitions are in [GLOSSARY.md](GLOSSARY.md).

## Run

```bash
uv sync
uv run nfl-lab refresh
uv run pytest
```

`uv run nfl-lab --help` lists `refresh`, `pick-card`, `line-snapshot`, and `backtest`.

`refresh` writes `output/live/` and `public/api/`. Raw play-by-play stays in `data/` and is not committed. The nightly GitHub Action runs the same command and commits the JSON.

No odds API key. The ESPN scoreboard is a public, unofficial endpoint and can change. The adapter is `src/nfl_lab/odds_espn.py`. If a scheduled game has no DraftKings number, the command exits 1.

## Site

Static files in `public/`. Home is this week's locked-rule picks. Ledger is the spent holdout plus the live card. Teams are EPA and success rate. Freshness is what updated when. Week 4 recaps are plain sentences at `public/recaps/week4.html`. The Jets at Bears page is `public/recaps/week4-nyj-chi.html`. The source copy is [`pipeline/WEEK4_RECAPS.md`](pipeline/WEEK4_RECAPS.md).

## Model, briefly

Opponent-adjusted EPA with prior-season shrinkage, plus home field. For 2026 cards only, a starting-QB adjustment is added. That term was checked on 2016–2021 (margin error 10.50 down to 10.45) and was not applied to the 2022–2025 ledger. When the schedule's quarterback disagrees with the depth chart, the card uses the depth chart and the injury report, and it says so.
