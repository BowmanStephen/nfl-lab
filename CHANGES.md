# Changes

## Proposed: margin calibration v2 (would apply from 2026 week 6)

Not live until this PR is merged. Week 1–5 cards, the locked week-5 picks, and the
2022–2025 ledger are not touched. Every setting below was chosen on 2016–2021 only,
by average miss (MAE) and calibration. Betting results were never used to choose.

**What was wrong**

- **Totals sign bug.** The totals formula counted a stingy defense as *adding* points.
  Fixed in its own commit, with the two totals numbers refit on 2016–2021.
- **Margins squeezed in mid-season.** One points-per-EPA number was used for every week.
  On 2016–2021, a 1-point model edge in weeks 5–8 was really worth about 1.24 points,
  so week-5 projections were too close to zero. Easing the shrinkage did not help.
- **Totals ignored real scoring.** They used one EPA number and nothing about how many
  points each team scores and allows, so every total landed near 46.

**What changes from week 6**

- Margins come from a scoring-margin rating (points for minus points against, pulled
  toward the last three seasons), with its own scale for weeks 1–4, 5–8 and 9+.
  It beat the EPA rating on 2016–2021, and EPA added nothing once it was in.
- Totals use each team's points-scored and points-allowed levels plus the fixed EPA term.
- The starting-QB adjustment is refit alongside (still 2016–2021 only).

**2016–2021, each season predicted by a model fit on the other five**

| | Margin MAE | Margin spread (SD) | Total MAE | Total spread (SD) |
|---|---|---|---|---|
| Current | 10.50 | 5.14 | 11.10 | 1.30 |
| Totals sign fix only | — | — | 11.05 | 2.18 |
| v2 | 10.35 | 5.63 | 10.92 | 2.90 |
| Betting market | 9.99 | 6.25 | 10.58 | 4.35 |

Weeks 5–8 calibration: a 1-point projected margin was worth 1.24 real points before, 0.97 after.

**What it does not fix.** The model still knows less than the betting line, so its numbers
stay a bit narrower than the line and most edges still land on underdogs. On week 5 it would
have made 5 spread picks (1 favorite, 4 underdogs) instead of 7 underdogs, and 1 total pick
(an under) instead of 8.

**Rule conflict to decide.** `AGENTS.md` says not to change the locked coefficients after week-5
picks exist. This PR leaves `output/backtest/` alone and adds v2 beside it, but merging it is
still a choice to change the model from week 6. Not a call for one bot to make alone.

Rebuild: `uv run nfl-lab refit-totals-signfix` and `uv run nfl-lab calibrate`
(writes `output/calibration/`). Not changed here: the box mirror under `pipeline/`, and the
power-ratings page, which still shows EPA ratings.
