# NFL Lab

A fast weekly record of one model against the line. Cousin of CFB Model Lab. Not a bet slip.

## Sources
- nflverse: PBP, schedules, historical closes
- ESPN scoreboard (keyless): pick-time + pre-kickoff DraftKings lines; same-book CLV only; fail loud if missing

## Proof
- Pick rule: |edge| ≥ 2 spread or ≥ 3 total
- Tune 2016-2021 only; 2022-2025 is spent baseline (48.8% ATS / 51.0% totals) — do not grind to beat it
- Live proof: 2026 from week 5, timestamped picks in git before kickoff
- After week 18 (≥100 locked-rule picks): ATS >52.4% AND ESPN line moved toward us >55% of time AND average ESPN CLV positive

## Copy
- Code OK: cfb-model-lab, nflreadpy/nflverse, fantasy-football-ai (MIT), nfl4th method rebuilt in Python (MIT)
- Ideas only: nfelo family, unlicensed spread models

## Ship
- PR1: uv-fast CLI, Actions, picks, ledger, freshness, team profiles, EPA/PPA glosses, light visuals, ESPN snapshots
- PR2: drives, box, situations, fourth downs, matchup

## How a live pick is scored

Judged once, after the 2026 regular season (week 18). Only picks that met the locked rule count. Pushes are counted and left out of the cover rate. A line that does not move counts as not moving our way.

The two ESPN numbers are DraftKings both times: the snapshot taken when the pick is saved, and the snapshot taken in the two hours before kickoff. nflverse closing lines stay on the 2022–2025 ledger. They are a different book, so they are not the live comparison.

Cover is graded against the pick-time ESPN line. Final scores come from nflverse.

If a scheduled game is missing either ESPN line, the job exits non-zero and the game stays on the card. It is not dropped.

## What is frozen

- `output/backtest/preregistration.json` — the 2 point / 3 point rule
- `output/backtest/locked_model.json` — shrinkage and point conversion from 2016–2021
- `output/backtest/qb_adjustment_validation.json` — starting-QB term, 2016–2021 only, not applied to the spent holdout
- Each week's `output/live/*` pick and pick-time line, once written

Before that lock, one exploratory pass looked at 2023–2025 margin error only. No lines were graded. Two settings sat on the edge of the search grid. Any retune is a new round, and it would be tested on 2026 live results only.

## Pages

Picks, ledger, teams, freshness. Ratings, the pick card, the ledger, and the line snapshots are the v1 surface.
