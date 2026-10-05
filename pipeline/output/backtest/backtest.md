# NFL Lab — Walk-forward Backtest

Rule locked at 2026-10-05T00:23:40.782808-05:00 (before grading). Graded at 2026-10-05T00:26:16.182966-05:00.

## Pre-registered rule
- Spread: bet model side when |model margin − closing spread| ≥ 2.0 pts
- Total: bet model side when |model total − closing total| ≥ 3.0 pts
- Tuning: 2016–2021 only. Holdout: 2022–2025 (graded once).
- Break-even at -110: 52.38%

## HEADLINE: holdout 2022–2025
- Spread bets (locked rule): 268-281-20 · 48.8% (95% CI 44.7–53.0%) · units @-110 -37.4 · p(>52.4%)=0.957
- Total bets (locked rule): 277-266-5 · 51.0% (95% CI 46.8–55.2%) · units @-110 -14.2 · p(>52.4%)=0.752

### Accuracy (no betting lines used)
- Games: 1087
- MAE vs final margin: model 10.10 vs closing spread 9.49
- MAE vs final total: model 10.82 vs closing total 10.19
- Brier (home win): model 0.2265 vs spread-implied 0.2105
- Straight-up accuracy: 63.1%

## Locked model
```json
{
  "locked_at": "2026-10-05T00:25:49.092267-05:00",
  "fit_on_seasons": [
    2016,
    2017,
    2018,
    2019,
    2020,
    2021
  ],
  "prior_regress": 0.3,
  "prior_plays_equiv": 1200,
  "prior_seasons_weighting": "S-3:S-2:S-1 = 1:2:3",
  "points_per_net_epa": 81.22071383225719,
  "hfa": 1.4703715732185563,
  "margin_sigma": 13.50392487843858,
  "points_per_combined_off": 19.41067783178249,
  "base_total": 46.15196331795182,
  "total_sigma": 13.973237205269175,
  "n_fit_games": 1550
}
```

## Descriptive only (NOT used to pick the rule)

### Holdout spread edge buckets
| edge_bucket | bets | wins | losses | pushes | win_rate | units_at_minus_110 |
| --- | --- | --- | --- | --- | --- | --- |
| 0-1 | 279 | 139 | 135 | 5 | 0.507 | -8.6 |
| 1-2 | 239 | 111 | 124 | 4 | 0.472 | -23.1 |
| 2-3 | 199 | 95 | 94 | 10 | 0.503 | -7.6 |
| 3+ | 370 | 173 | 187 | 10 | 0.481 | -29.7 |

### Holdout total edge buckets
| edge_bucket | bets | wins | losses | pushes | win_rate | units_at_minus_110 |
| --- | --- | --- | --- | --- | --- | --- |
| 0-1 | 178 | 85 | 92 | 1 | 0.480 | -14.7 |
| 1-2 | 188 | 87 | 99 | 2 | 0.468 | -19.9 |
| 2-3 | 173 | 83 | 90 | 0 | 0.480 | -14.5 |
| 3-5 | 250 | 127 | 121 | 2 | 0.512 | -5.5 |
| 5+ | 298 | 150 | 145 | 3 | 0.508 | -8.6 |

### Per season (holdout + tuning window)

| season | window | games | model MAE | market MAE | spread (locked) | total (locked) |
| --- | --- | --- | --- | --- | --- | --- |
| 2016 | tuning (in-sample) | 256 | 9.68 | 9.02 | 60-70-1 (46.2%) | 56-61-0 (47.9%) |
| 2017 | tuning (in-sample) | 254 | 10.78 | 10.09 | 64-77-3 (45.4%) | 70-62-0 (53.0%) |
| 2018 | tuning (in-sample) | 256 | 10.24 | 9.98 | 68-56-5 (54.8%) | 67-63-1 (51.5%) |
| 2019 | tuning (in-sample) | 256 | 10.63 | 10.21 | 67-60-3 (52.8%) | 61-53-0 (53.5%) |
| 2020 | tuning (in-sample) | 256 | 10.26 | 9.83 | 81-68-0 (54.4%) | 60-70-3 (46.2%) |
| 2021 | tuning (in-sample) | 272 | 11.25 | 10.78 | 70-66-1 (51.5%) | 58-55-2 (51.3%) |
| 2022 | holdout | 271 | 9.24 | 8.74 | 62-67-6 (48.1%) | 71-77-2 (48.0%) |
| 2023 | holdout | 272 | 10.59 | 9.90 | 72-72-10 (50.0%) | 83-76-2 (52.2%) |
| 2024 | holdout | 272 | 10.15 | 9.61 | 73-69-3 (51.4%) | 66-54-1 (55.0%) |
| 2025 | holdout | 272 | 10.43 | 9.72 | 61-73-1 (45.5%) | 57-59-0 (49.1%) |

Tuning-window locked rule (in-sample coefficients, descriptive): spread 410-397-13 · 50.8% (95% CI 47.4–54.2%) · units @-110 -24.3 · p(>52.4%)=0.824; total 372-364-6 · 50.5% (95% CI 46.9–54.1%) · units @-110 -25.8 · p(>52.4%)=0.850
