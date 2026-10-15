"""An official-pick anchor tints and focuses the row a visitor lands on."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from nfl_lab.config import ROOT

PUBLIC = ROOT / "public"
PROBE = Path(__file__).with_name("highlight_browser.mjs")
CSS = (PUBLIC / "assets" / "site.css").read_text()
JS = (PUBLIC / "assets" / "site.js").read_text()


def _transparent(color: str) -> bool:
    return color in {"transparent", "rgba(0, 0, 0, 0)"}


@pytest.fixture(scope="module")
def highlight():
    if shutil.which("node") is None:
        pytest.fail("node is required to open the published page")
    proc = subprocess.run(
        ["node", str(PROBE), str(PUBLIC)],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        pytest.fail(f"highlight browser check failed\n{proc.stderr}\n{proc.stdout}")
    return json.loads(proc.stdout)


def test_target_style_is_scoped_to_game_lists():
    assert ".games li:target" in CSS
    assert "box-shadow: inset 3px 0 0 var(--accent)" in CSS
    assert re.search(r"(?<!\.games )li:target", CSS) is None
    assert 'tabindex="-1"' in JS
    assert "el.focus({ preventScroll: true })" in JS
    assert "That pick was from week" in JS
    assert "pinScroll" not in JS
    assert 'scrollIntoView({ block: "center", behavior: reduced ? "auto" : "smooth" })' in JS
    assert 'setAttribute("role", "status")' in JS


def test_anchored_row_is_tinted_and_focused(highlight):
    row = highlight["row"]
    assert row["id"] == highlight["pickId"]
    assert row["activeId"] == row["id"]
    assert row["tabIndex"] == -1
    assert row["animationName"] == "target-row-fade"
    assert "inset" in row["boxShadow"]
    assert "3px" in row["boxShadow"]
    assert not _transparent(row["background"])
    assert row["inView"] is True
    assert row["scrollY"] > 40


def test_reduced_motion_scrolls_the_row_into_view(highlight):
    row = highlight["reduced"]
    assert row["activeId"] == row["id"]
    assert row["tabIndex"] == -1
    assert row["animationName"] == "none"
    assert "inset" in row["boxShadow"]
    assert "3px" in row["boxShadow"]
    assert not _transparent(row["background"])
    assert row["inView"] is True
    assert row["scrollY"] > 40


def test_missing_hash_points_at_that_weeks_recap(highlight):
    missed = highlight["missed"]
    week = highlight["week"]
    assert f"That pick was from week {week}" in missed["text"]
    assert missed["href"].endswith(f"recaps/week{week}.html")
    assert "see the recap" in missed["text"]
    assert missed["role"] == "status"


def test_past_week_official_links_go_to_the_recap(highlight):
    week = highlight["week"]
    assert highlight["official"]
    for href in highlight["official"]:
        assert href.endswith(f"../recaps/week{week}.html")


@pytest.mark.parametrize("qualifies, expected_id", [
    ([False, True, False], "2027_01_B_B"),
    ([False, False, False], "2027_01_C_C"),
])
def test_target_selection_allows_cards_without_spread_picks(tmp_path, qualifies, expected_id):
    (tmp_path / "api").mkdir()
    (tmp_path / "previews").mkdir()
    games = [
        {"game_id": f"2027_01_{team}_{team}", "selection": {"spread_qualifies": active}}
        for team, active in zip(["A", "B", "C"], qualifies)
    ]
    (tmp_path / "api" / "picks.json").write_text(json.dumps({"games": games}))
    (tmp_path / "previews" / "week5.html").write_text('<p data-game="2026_05_TB_DAL"></p>')
    proc = subprocess.run(
        ["node", str(PROBE), str(tmp_path), "--targets-only"],
        check=True, capture_output=True, text=True,
    )
    assert json.loads(proc.stdout)["pickId"] == f"b-{expected_id}"
