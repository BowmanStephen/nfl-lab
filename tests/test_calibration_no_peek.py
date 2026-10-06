"""v2 must use only games before week W, and may only be fit on 2016-2021."""
from __future__ import annotations

import pandas as pd
import pytest

from nfl_lab import calibration


def _sched() -> pd.DataFrame:
    rows = []
    for season in (2017, 2018, 2019):
        rows.append({"season": season, "week": 1, "game_type": "REG", "home_team": "A", "away_team": "B",
                     "home_score": 30, "away_score": 10, "location": "Home"})
    for week, (hs, as_) in {1: (27, 20), 2: (14, 17), 3: (40, 3), 4: (0, 50)}.items():
        rows.append({"season": 2020, "week": week, "game_type": "REG", "home_team": "A", "away_team": "B",
                     "home_score": hs, "away_score": as_, "location": "Home"})
    return pd.DataFrame(rows)


def test_levels_ignore_week_w_and_later() -> None:
    s = _sched()
    tg = calibration.team_games(s)
    base = calibration.scoring_levels(tg, 2020, 3, kg=8, rg=0.5)
    poisoned = s.copy()
    m = (poisoned["season"] == 2020) & (poisoned["week"] >= 3)
    poisoned.loc[m, ["home_score", "away_score"]] = [99, 0]
    again = calibration.scoring_levels(calibration.team_games(poisoned), 2020, 3, kg=8, rg=0.5)
    pd.testing.assert_frame_equal(base, again)
    # Positive control: changing an earlier week must move it.
    ctl = s.copy()
    ctl.loc[(ctl["season"] == 2020) & (ctl["week"] == 1), ["home_score", "away_score"]] = [99, 0]
    assert not base.equals(calibration.scoring_levels(calibration.team_games(ctl), 2020, 3, kg=8, rg=0.5))


def test_week2_uses_week1_scores() -> None:
    """Unlike the EPA opponent adjustment, the scoring levels do not cancel out after one game."""
    s = _sched()
    tg = calibration.team_games(s)
    lv = calibration.scoring_levels(tg, 2020, 2, kg=8, rg=0.5)
    prior_only = calibration.scoring_levels(tg[tg["season"] < 2020], 2020, 2, kg=8, rg=0.5)
    assert not lv.equals(prior_only)


def test_fit_refuses_holdout_seasons() -> None:
    pbp = pd.DataFrame({"season": [2021, 2022]})
    with pytest.raises(AssertionError):
        calibration.fit_v2(pbp, _sched(), pd.DataFrame(), {"prior_regress": 0.3, "prior_plays_equiv": 1200})


def test_applies_only_from_week6() -> None:
    v2 = {"applies_from": {"season": 2026, "week": 6}}
    assert not calibration.applies(v2, 2026, 5)
    assert calibration.applies(v2, 2026, 6)
    assert not calibration.applies(None, 2026, 6)
