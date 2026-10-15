"""The historical report must not adopt subsequent totals corrections."""
import json

import pandas as pd
import pytest

from nfl_lab import report_card
from nfl_lab.config import OUTPUT_DIR, PUBLIC_API
from nfl_lab.walkforward import apply_coefs, features


def test_report_uses_original_coefficients_and_original_defense_sign(monkeypatch):
    locked, _ = report_card._locked()
    original = json.loads((OUTPUT_DIR / "backtest" / "locked_model.json").read_text())["locked_model"]
    assert locked == original
    prior = pd.DataFrame([
        {"team": "H", "adj_off_epa": 0.2, "adj_def_epa": -0.1},
        {"team": "A", "adj_off_epa": 0.1, "adj_def_epa": -0.2},
    ])
    current = prior.assign(off_plays=0, def_plays=0)
    games = pd.DataFrame([{
        "season": 2026, "week": 1, "home_team": "H", "away_team": "A",
        "home_score": 20, "away_score": 10, "location": "Home",
    }])
    pre = {"priors": {2026: prior}, "current": {(2026, 1): current}, "games": games}
    monkeypatch.setattr(report_card, "precompute", lambda *args: pre)

    frozen, _ = report_card.project(pd.DataFrame(), games, locked)
    reg = locked["prior_regress"]
    # Original environment = offense - EPA allowed, even though that sign is wrong.
    expected_env = reg * (0.2 + 0.1 - (-0.1) - (-0.2))
    assert frozen.iloc[0]["proj_total"] == pytest.approx(
        locked["base_total"] + locked["points_per_combined_off"] * expected_env)

    corrected = apply_coefs(features(pre, reg, locked["prior_plays_equiv"]), locked)
    assert corrected.iloc[0]["proj_total"] == pytest.approx(locked["base_total"])
    assert frozen.iloc[0]["proj_margin"] == corrected.iloc[0]["proj_margin"]


def test_published_historical_report_preserves_original_totals_record():
    report = json.loads((PUBLIC_API / "report_card.json").read_text())
    archive = json.loads((OUTPUT_DIR / "report_card" / "2026_wk01_04.json").read_text())
    assert report == archive
    assert report["total"]["wins"] == 10
    assert report["total"]["losses"] == 19
    assert report["total"]["bets"] == 29
    assert sum(game["total_bet_locked_rule"] for game in report["games"]) == 29
    assert report["base_total"] == 46.15196331795182
    assert report["points_per_combined_off"] == 19.41067783178249
