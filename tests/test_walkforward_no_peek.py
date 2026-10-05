"""Future games must not change this week's ratings.

The approach follows the leakage check in cbratkovics/fantasy-football-ai
(MIT): perturb the target week and later weeks, then assert the features
for that week stay put. Adapted to this lab's walk-forward ratings.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from nfl_lab.walkforward import features, precompute


def _plays(rows: list[tuple]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["season", "week", "posteam", "defteam", "epa"])
    frame["season_type"] = "REG"
    frame["pass"] = 1
    frame["rush"] = 0
    frame["qb_kneel"] = 0
    frame["qb_spike"] = 0
    frame["success"] = frame["epa"] > 0
    return frame


def _schedule() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "game_id": "2020_02_A_B",
            "season": 2020,
            "week": 2,
            "game_type": "REG",
            "home_team": "B",
            "away_team": "A",
            "home_score": 24,
            "away_score": 17,
            "location": "Home",
        }
    ])


def _base_pbp() -> pd.DataFrame:
    rows = []
    # 2019 prior: A is the better offense.
    for i in range(8):
        rows.append((2019, 1, "A", "B", 0.4))
        rows.append((2019, 1, "B", "A", -0.2))
    # 2020 week 1, the only current-season input for a week-2 projection.
    for i in range(6):
        rows.append((2020, 1, "A", "B", 0.3))
        rows.append((2020, 1, "B", "A", -0.1))
    # Week 2 and week 3 are the future, relative to a week-2 card.
    for i in range(6):
        rows.append((2020, 2, "A", "B", 0.05))
        rows.append((2020, 2, "B", "A", 0.05))
        rows.append((2020, 3, "A", "B", 0.05))
    return _plays(rows)


def _week2_diff(pbp: pd.DataFrame) -> float:
    pre = precompute(pbp, _schedule(), [2020])
    feat = features(pre, regress=0.3, plays_equiv=50)
    row = feat[(feat["season"] == 2020) & (feat["week"] == 2)].iloc[0]
    return float(row["rating_diff"])


def test_future_weeks_do_not_change_this_weeks_rating():
    base = _week2_diff(_base_pbp())
    poisoned = _base_pbp()
    future = poisoned["week"] >= 2
    poisoned.loc[future, "epa"] = np.where(poisoned.loc[future, "posteam"] == "B", 5.0, -5.0)
    assert _week2_diff(poisoned) == base


def test_past_weeks_do_change_this_weeks_rating():
    base = _week2_diff(_base_pbp())
    shifted = _base_pbp()
    past = (shifted["season"] == 2020) & (shifted["week"] == 1)
    shifted.loc[past & (shifted["posteam"] == "B"), "epa"] = 4.0
    shifted.loc[past & (shifted["posteam"] == "A"), "epa"] = -4.0
    assert _week2_diff(shifted) != base
