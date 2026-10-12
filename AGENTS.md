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

Exit code 3 means nflverse inputs were missing or stale (`check_source_fresh`); nothing was written and nothing is committed. A missing DraftKings line is exit code 1 while the game is still before kickoff and nothing new was saved. Exit code 2 means a partial snapshot was saved and a line is still missing: commit that snapshot, then fail. After kickoff, a missed snapshot may be filled from the nflverse close and must be labeled `nflverse_close`. Do not call that pair CLV. Do not catch a line that is still missing and continue.

## Routine failure alerts

Failed scheduled runs (from `docs/nightly.yml.proposed` once it is copied into `.github/workflows/nightly.yml`) write to one open GitHub issue labeled `routine-failure`. The first failure opens it; later failures add a comment. Close it by hand once runs are green, and the next failure opens a new one. Shannon Sharpe reads this issue and relays it to Stephen's chat.

The issue body and each comment are machine-readable: a marker line `<!-- routine-failure v1 -->`, then one fenced `json` block:

```json
{"run_url": "https://github.com/BowmanStephen/nfl-lab/actions/runs/123", "job": "refresh", "exit_code": "3", "reason": "source data missing or stale; nothing written or committed", "timestamp_utc": "2026-10-12T11:28:43Z"}
```

- `job`: `refresh` (6:15 AM CT run, or manual refresh/pick-card) or `capture` (hourly game-day line-snapshot)
- `exit_code`: string; `1` crash or missing line, `2` partial snapshot committed, `3` stale source data, `0` command passed but validate/commit/push failed, `none` failed before the command ran
- `reason`: one line, plain English
- `timestamp_utc`: ISO 8601, `Z`

Change the fields only by bumping the marker to `v2`.

`line-snapshot` with no pick card yet exits 0 with a log line and writes nothing.

## Do not

- Change the 2 / 3 thresholds, the locked coefficients, or the QB coefficient after seeing 2026 results
- Compare an ESPN line to an nflverse close and call it CLV
- Edit a pick or a pick-time line after it is committed
- Add a paid odds key
- Start fourth-down, props, or a matchup calculator in this pass

You may fill `pre_kickoff` and final scores on a card that already exists.
