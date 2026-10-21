import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from nfl_lab.publish import publish_card, saved_weeks_payload

ROOT = Path(__file__).resolve().parents[1]


def _outcomes(games):
    return [g["spread_outcome"] for g in games if g["spread_qualifies"]]


def test_saved_weeks_keep_week5_record_and_week6_slate():
    payload = saved_weeks_payload()
    by_week = {week["week"]: week["games"] for week in payload["weeks"]}
    assert payload["season"] == 2026
    assert payload["current_week"] == 7
    week5 = _outcomes(by_week[5])
    assert week5.count("win") == 2
    assert week5.count("loss") == 4
    assert week5.count("push") == 1
    assert len(week5) == 7
    assert all(game["total_active"] is False for game in by_week[5])
    assert len(by_week[6]) == 14
    assert sum(game["spread_qualifies"] for game in by_week[6]) == 4
    # Main voided the six week-6 totals; saved weeks must reflect that card.
    assert sum(game["total_active"] for game in by_week[6]) == 0
    assert next(week for week in payload["weeks"] if week["week"] == 6)["totals_paused"] is True


def test_published_card_replaces_only_its_week(monkeypatch, tmp_path):
    monkeypatch.setattr("nfl_lab.publish.PUBLIC_API", tmp_path)
    card = {
        "week": 6,
        "health": {"line": "test"},
        "games": [{
            "week": 6,
            "gameday": "2026-10-18",
            "away_team": "SEA",
            "home_team": "DEN",
            "selection": {
                "model_margin": -1.5,
                "spread_qualifies": True,
                "total_qualifies": True,
                "total_voided": True,
            },
            "grading": None,
        }],
    }
    publish_card(card, datetime(2026, 10, 14, tzinfo=ZoneInfo("America/Chicago")))
    saved = json.loads((tmp_path / "saved_weeks.json").read_text())
    assert saved["current_week"] == 6
    by_week = {week["week"]: week["games"] for week in saved["weeks"]}
    assert len(by_week[6]) == 1
    assert by_week[6][0]["spread_qualifies"] is True
    assert by_week[6][0]["total_active"] is False
    assert next(week for week in saved["weeks"] if week["week"] == 6)["totals_paused"] is True
    assert _outcomes(by_week[5]).count("win") == 2


def test_saved_weeks_preserve_future_pause_without_any_total_picks():
    card = {"week": 7, "totals_paused": True, "games": []}
    payload = saved_weeks_payload(card)
    week = next(week for week in payload["weeks"] if week["week"] == 7)
    assert week["totals_paused"] is True
    assert week["games"] == []
    card["totals_paused"] = False
    unpaused = next(week for week in saved_weeks_payload(card)["weeks"] if week["week"] == 7)
    assert unpaused["totals_paused"] is False


def test_track_record_page_script():
    proc = subprocess.run(
        ["node", "--test", str(ROOT / "tests" / "test_track_record.js")],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
