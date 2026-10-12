from datetime import datetime, timezone

import pytest

from nfl_lab.odds_espn import (
    MissingLineError,
    fill_missing_from_summaries,
    home_margin_from_odds,
    home_margin_from_pickcenter,
    parse_scoreboard,
    total_from_odds,
)


def _event(away, home, home_close, total, provider="DraftKings"):
    return {
        "id": "1",
        "date": "2026-10-11T17:00Z",
        "competitions": [{
            "competitors": [
                {"homeAway": "away", "team": {"abbreviation": away}},
                {"homeAway": "home", "team": {"abbreviation": home}},
            ],
            "odds": [{
                "provider": {"name": provider},
                "details": f"{home} {home_close}",
                "overUnder": total,
                "pointSpread": {"home": {"close": {"line": home_close}}},
            }],
        }],
    }


def test_home_margin_matches_lab_convention():
    # ESPN "-10" means home is favored. Lab home margin is +10.
    odds = _event("TB", "DAL", "-10", 47.5)["competitions"][0]["odds"][0]
    assert home_margin_from_odds(odds) == 10
    assert total_from_odds(odds) == 47.5
    # Home dog: "+2.5" -> home margin -2.5.
    dog = _event("CHI", "GB", "+2.5", 44.5)["competitions"][0]["odds"][0]
    assert home_margin_from_odds(dog) == -2.5


def test_parse_maps_espn_abbreviations_and_requires_draftkings():
    payload = {"events": [
        _event("NYG", "WSH", "-3", 43.5),
        _event("BUF", "LAR", "-2.5", 53.5, provider="SomeOtherBook"),
    ]}
    # Second event has no DraftKings block, so it is flagged missing rather than borrowed.
    lines = parse_scoreboard(payload)
    assert lines[0]["away_team"] == "NYG"
    assert lines[0]["home_team"] == "WAS"
    assert lines[0]["home_margin"] == 3
    assert lines[1]["home_team"] == "LA"
    assert lines[1]["missing"] is True


def test_unreadable_spread_raises():
    with pytest.raises(MissingLineError):
        home_margin_from_odds({"pointSpread": {"home": {"close": {"line": ""}}}})


def test_pickcenter_uses_the_scoreboard_spread_field():
    odds = {
        "provider": {"name": "DraftKings"},
        "details": "JAX -3",
        "overUnder": 43.5,
        "spread": -3.0,
        "homeTeamOdds": {"favorite": True},
        "pointSpread": {"home": {"close": {"line": "-3"}}},
    }
    assert home_margin_from_pickcenter(odds) == 3
    assert total_from_odds(odds) == 43.5


def test_pickcenter_without_point_spread_uses_the_favorite_flag():
    # Away favored by 1.5. Lab home margin is -1.5.
    odds = {
        "spread": 1.5,
        "overUnder": 46.5,
        "homeTeamOdds": {"favorite": False},
    }
    assert home_margin_from_pickcenter(odds) == -1.5


def test_summary_fills_a_missing_scoreboard_line_only_before_kickoff():
    stub = {
        "espn_id": "401872996",
        "away_team": "HOU",
        "home_team": "JAX",
        "kickoff_utc": "2026-10-18T13:30:00+00:00",
        "missing": True,
        "home_margin": None,
        "total": None,
        "provider": None,
    }

    def fetch(_espn_id):
        return {"pickcenter": [{
            "provider": {"name": "DraftKings"},
            "details": "JAX -3",
            "overUnder": 43.5,
            "pointSpread": {"home": {"close": {"line": "-3"}}},
        }]}

    before = datetime(2026, 10, 18, 12, 15, tzinfo=timezone.utc)
    filled = fill_missing_from_summaries([dict(stub)], fetch, before)
    assert filled[0]["missing"] is False
    assert filled[0]["home_margin"] == 3
    assert filled[0]["source"] == "espn_summary"
    assert filled[0]["total"] == 43.5

    after = datetime(2026, 10, 18, 13, 31, tzinfo=timezone.utc)
    skipped = fill_missing_from_summaries([dict(stub)], fetch, after)
    assert skipped[0]["missing"] is True
    assert skipped[0]["home_margin"] is None
