from nfl_lab.odds_espn import MissingLineError, home_margin_from_odds, parse_scoreboard, total_from_odds
import pytest


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
