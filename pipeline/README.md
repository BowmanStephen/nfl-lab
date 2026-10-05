# NFL Lab

League-wide NFL advanced stats and transparent game model for Stephen Bowman.

## What it does

- Pulls play-by-play and schedules from nflverse (real data only)
- Computes team advanced stats (EPA, success rate, early-down EPA, PROE, explosive rate, QB EPA+CPOE)
- Builds opponent-adjusted team ratings with prior-season shrinkage
- Projects spread, total, and win probability for the upcoming week
- Backtests on recent seasons (Brier, MAE vs final margin)
- Writes preview/recap markdown + JSON under `output/`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m src.run
```

## Outputs

- `output/team_stats.json` / `.md`
- `output/ratings.json` / `.md`
- `output/projections_weekN.json` / `.md`
- `output/previews/*.md` + `previews.json`
- `output/recaps/*.md` + `recaps.json`
- `output/backtest.json` / `.md`
- `output/summary.json`

All numbers come from code on nflverse data — never invented.

## Backtest protocol (pre-registered)

- Rule locked in `output/backtest/preregistration.json` before grading: spread edge >= 2.0, total edge >= 3.0 vs nflverse closing lines.
- Strict walk-forward: week-W ratings use only weeks < W; priors only from seasons S-3..S-1.
- Tuning (shrinkage, prior regression, HFA, coefficients) on 2016-2021 only; frozen in `locked_model.json`.
- 2022-2025 holdout graded once -> `backtest_results.json` (HEADLINE), `ledger.json` / `ledger.csv`.
- Buckets and per-season splits are descriptive only.
- `python -m src.run` reuses the frozen result; re-grading requires the explicit `--regrade-holdout` flag.

## Starting-QB adjustment (secondary)

`src/qb_adjust.py`: shrunk EPA/dropback of the projected starter vs the team's dropback-weighted QB mix
in its rating window. Validated on 2016-2021 only (`qb_adjustment_validation.json`); NOT graded on the
holdout. Starters come from the nflverse schedules, cross-checked with depth charts + injury reports.
