"""A stingier defense must lower the projected total, never raise it."""
from __future__ import annotations

import pandas as pd

from nfl_lab.model import ModelParams, project_games


def _ratings(home_def: float) -> pd.DataFrame:
    # Defense numbers are EPA allowed per play: lower = stingier.
    return pd.DataFrame([
        {"team": "H", "rating": 0.0 - home_def, "shrunk_off_epa": 0.0, "shrunk_def_epa": home_def},
        {"team": "A", "rating": 0.0, "shrunk_off_epa": 0.0, "shrunk_def_epa": 0.0},
    ])


def test_stingy_defense_lowers_total() -> None:
    slate = pd.DataFrame([{"game_id": "g", "season": 2026, "week": 6, "gameday": "2026-10-11", "gametime": "13:00",
                           "home_team": "H", "away_team": "A", "location": "Home"}])
    params = ModelParams(points_per_net_epa=80.0, hfa=1.5, margin_sigma=13.5, base_total=46.0, points_per_combined_off=36.0)
    stingy = project_games(slate, _ratings(-0.10), params)["proj_total"].iloc[0]
    leaky = project_games(slate, _ratings(+0.10), params)["proj_total"].iloc[0]
    assert stingy < 46.0 < leaky
