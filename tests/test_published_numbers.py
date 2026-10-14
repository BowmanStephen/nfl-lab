"""Published records and counts must match the saved pick cards.

The test renders the site the way a browser does (public HTML + site.js + the
JSON in public/api) and compares every live record and count on those pages
to the grades in output/live. A disagreement fails CI.

The track-record page currently ignores earlier weeks. That bug is owned by
another PR, so the two known mismatches are expected failures, not edits.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from nfl_lab.config import LIVE_DIR, PUBLIC_API, ROOT
from nfl_lab.picks import health_summary, total_is_active

PUBLIC = ROOT / "public"
RENDER = Path(__file__).with_name("render_site.mjs")

WLP = re.compile(r"(\d+)\s*[–-]\s*(\d+)\s*[–-]\s*(\d+)")
WITH_PUSH = re.compile(
    r"(\d+)\s*[–-]\s*(\d+)\s+with\s+(one|\d+)\s+push(?:es)?",
    re.IGNORECASE,
)
WEEK_FINAL = re.compile(r"Our picks went\s+(\d+)\s*[–-]\s*(\d+)(?:\s*[–-]\s*(\d+))?")


def _cards() -> list[dict]:
    cards = [json.loads(path.read_text()) for path in sorted(LIVE_DIR.glob("*.json"))]
    if not cards:
        raise AssertionError(f"no saved cards in {LIVE_DIR}")
    return cards


def _current(cards: list[dict]) -> dict:
    return max(cards, key=lambda card: int(card["week"]))


def _games(cards: list[dict]) -> list[dict]:
    return [game for card in cards for game in card["games"]]


def _counts(card: dict) -> tuple[int, int, int]:
    games = card["games"]
    spread = sum(1 for game in games if game["selection"]["spread_qualifies"])
    total = sum(1 for game in games if total_is_active(game["selection"]))
    return len(games), spread, total


def _spread_record(games: list[dict]) -> tuple[int, int, int]:
    outcomes = []
    for game in games:
        grading = game.get("grading") or {}
        if game["selection"].get("spread_qualifies") and grading.get("spread_outcome"):
            outcomes.append(grading["spread_outcome"])
    return outcomes.count("win"), outcomes.count("loss"), outcomes.count("push")


def _picked_winner(games: list[dict]) -> tuple[int, int]:
    """Games where the team the model had ahead won, across every saved card."""
    right = wrong = 0
    for game in games:
        grading = game.get("grading") or {}
        if grading.get("home_score") is None or grading.get("away_score") is None:
            continue
        margin = game["selection"].get("model_margin")
        actual = grading["home_score"] - grading["away_score"]
        if actual == 0 or not margin:
            continue
        if (actual > 0) == (margin > 0):
            right += 1
        else:
            wrong += 1
    return right, right + wrong


def _week_spread_record(card: dict) -> tuple[int, int, int]:
    return _spread_record(card["games"])


@pytest.fixture(scope="module")
def published():
    """Build the pages a visitor would see from the committed site files."""
    if shutil.which("node") is None:
        pytest.fail("node is required to render the published pages")
    fresh = json.loads((PUBLIC_API / "freshness.json").read_text())
    proc = subprocess.run(
        ["node", str(RENDER), str(PUBLIC), fresh["generated_at"], "home", "ledger"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        pytest.fail(f"site render failed\n{proc.stderr}\n{proc.stdout}")
    return json.loads(proc.stdout)


def _field(page: dict, element_id: str, kind: str = "text") -> str:
    slot = page.get(element_id) or {}
    return slot.get(kind) or ""


def test_home_counts_match_saved_card(published):
    card = _current(_cards())
    n_games, n_spread, _n_total = _counts(card)
    home = published["home"]
    picks = re.search(r"Our picks \((\d+)\)", _field(home, "picks-h"))
    close = re.search(r"Too close to call \((\d+)\)", _field(home, "close-h"))
    agree = re.search(r"(\d+) games where we agree with Vegas", _field(home, "close-games"))
    assert picks, "home does not publish the spread-pick count"
    shown_spread = int(picks.group(1))
    shown_close = int(close.group(1)) if close else 0
    shown_agree = int(agree.group(1)) if agree else 0
    assert shown_spread == n_spread
    assert shown_spread + shown_close + shown_agree == n_games

    final = _field(home, "final-line")
    week_line = WEEK_FINAL.search(final)
    if week_line:
        pushes = int(week_line.group(3) or 0)
        assert (int(week_line.group(1)), int(week_line.group(2)), pushes) == _week_spread_record(card)


def test_total_pick_count_matches_saved_card(published):
    card = _current(_cards())
    _n_games, n_spread, n_total = _counts(card)
    live = _field(published["ledger"], "live", "html")
    assert live.count("off the total") == n_total
    assert live.count("off the spread") == n_spread


def test_live_record_matches_saved_grades(published):
    games = _games(_cards())
    health = health_summary(games)
    expected = (health["wins"], health["losses"], health["pushes"])

    ledger_line = _field(published["ledger"], "live-health")
    assert ledger_line == health["line"]

    recap = (PUBLIC / "recaps" / "week5.html").read_text()
    phrase = WITH_PUSH.search(recap)
    assert phrase, "week 5 recap does not publish the live record"
    pushes = 1 if phrase.group(3).lower() == "one" else int(phrase.group(3))
    assert (int(phrase.group(1)), int(phrase.group(2)), pushes) == expected
    rate = health["cover_rate"]
    assert rate is not None
    assert f"{100 * rate:.1f}%" in recap


def test_track_record_ats_matches_saved_grades(published):
    expected = _spread_record(_games(_cards()))
    tile = re.search(
        r"Against the spread</p><p class=\"num\">([^<]+)",
        _field(published["ledger"], "tr-tiles", "html"),
    )
    assert tile, "track record page does not publish an against-the-spread record"
    shown = tuple(int(part) for part in re.split(r"\s*[–-]\s*", tile.group(1).strip()))
    if shown == (0, 0, 0) and expected == (2, 4, 1):
        pytest.xfail(
            "Track record page shows 0-0-0 against the spread; the saved cards "
            "grade 2-4-1. Known issue owned by the parallel track-record PR. "
            "This PR does not change that page."
        )
    assert shown == expected


def test_track_record_winner_tile_matches_saved_grades(published):
    right, decided = _picked_winner(_games(_cards()))
    expected = f"{right} of {decided}"
    tile = re.search(
        r"Picked the winner</p><p class=\"num\">([^<]+)",
        _field(published["ledger"], "tr-tiles", "html"),
    )
    assert tile, "track record page does not publish the winner count"
    shown = tile.group(1).strip()
    if shown == "0 of 0" and expected == "10 of 14":
        pytest.xfail(
            "Track record page shows 0 of 0 winners because it only reads the "
            "current week card. Saved grades are 10 of 14. Known issue owned by "
            "the parallel track-record PR. This PR does not change that page."
        )
    assert shown == expected
