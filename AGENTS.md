# Agents

Fetch `origin/main` before editing. This file and `PRODUCT.md` are the rules. Do not retune them after week 5 picks exist.

## Where things live

- Frozen holdout: `output/backtest/` (do not regrade, do not edit the ledger to improve 48.8% / 51.0%)
- Live cards: `output/live/{season}-week-{nn}.json` — pick and pick-time line are immutable
- Site JSON: `public/api/`
- Model code: `src/nfl_lab/`

## Commands

```bash
uv run nfl-lab refresh        # nightly: data, ratings, card, site
uv run nfl-lab pick-card      # same path; creates the card if it is missing
uv run nfl-lab line-snapshot  # pre-kickoff ESPN DraftKings only
uv run nfl-lab backtest       # prints the spent holdout; does not recompute it
uv run nfl-lab report-card    # 2026 wk1-4 walk-forward backtest -> public/api/report_card.json (not official picks)
```

A missing DraftKings line is exit code 1. Do not catch that and continue.

## Do not

- Change the 2 / 3 thresholds, the locked coefficients, or the QB coefficient after seeing 2026 results
- Compare an ESPN line to an nflverse close and call it CLV
- Edit a pick or a pick-time line after it is committed
- Add a paid odds key
- Start fourth-down, props, or a matchup calculator in this pass

You may fill `pre_kickoff` and final scores on a card that already exists.
