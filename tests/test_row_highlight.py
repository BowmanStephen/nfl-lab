"""Homepage anchors and contrast across the main navigation in Chrome."""
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


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("media", ["screen", "print"])
@pytest.mark.parametrize("viewport,width,height,mobile_layout", [
    ("mobile", 390, 844, True),
    ("desktop", 1280, 900, False),
])
def test_home_text_meets_wcag_aa(highlight, scheme, media, viewport, width, height, mobile_layout):
    result = highlight["contrast"][viewport][media][scheme]
    assert result["viewport"] == {"width": width, "height": height, "mobileLayout": mobile_layout}
    assert result["print"] is (media == "print")
    assert result["screen"] is (media == "screen")
    assert result["dark"] is (scheme == "dark")
    if media == "print":
        assert result["paper"] == "rgb(255, 255, 255)"
    samples = result["samples"]
    assert any(sample["tag"] == "h1" for sample in samples), "heading must be measured"
    assert any(sample["id"] == "updated" for sample in samples), "muted text must be measured"
    assert len(samples) >= 10, "must measure actual homepage content"
    failures = [sample for sample in samples if sample["ratio"] < 4.5]
    assert failures == [], f"{viewport} {scheme}-scheme {media} contrast below 4.5:1: {failures}"


@pytest.mark.parametrize("viewport", ["mobile", "desktop"])
@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("state", ["hover", "focus"])
@pytest.mark.parametrize("page", ["home", "last_week", "teams"])
def test_page_interaction_contrast(highlight, viewport, scheme, state, page):
    result = (highlight["contrast"][viewport]["screen"][scheme] if page == "home"
              else highlight["linkedContrast"][page][viewport][scheme])
    assert result["viewport"] == {"width": 390 if viewport == "mobile" else 1280,
                                  "height": 844 if viewport == "mobile" else 900,
                                  "mobileLayout": viewport == "mobile"}
    assert result["screen"] and not result["print"]
    assert result["dark"] is (scheme == "dark")
    interactions = result["interactions"]
    targets = {target["index"] for target in interactions["targets"]
               if state == "focus" or target["hoverable"]}
    assert len(targets) >= 10, f"must exercise real {page} controls"
    assert {entry["index"] for entry in interactions[state]} == targets
    for entry in interactions[state]:
        result = entry["result"]
        assert result["hovered"] if state == "hover" else result["focused"] and result["focusVisible"]
        assert result["samples"], f"control {entry['index']} had no visible text"
        failures = [sample for sample in result["samples"] if sample["ratio"] < 4.5]
        assert not failures, f"{page} {viewport} {scheme} {state} control {entry['index']}: {failures}"
        if state == "focus":
            assert result["outline"]["style"] not in {"none", "hidden"}
            assert result["outline"]["width"] > 0
            assert result["outline"]["ratio"] >= 3, result["outline"]


@pytest.mark.parametrize("page", ["last_week", "teams"])
@pytest.mark.parametrize("viewport", ["mobile", "desktop"])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_linked_page_text_contrast(highlight, page, viewport, scheme):
    samples = highlight["linkedContrast"][page][viewport][scheme]["samples"]
    assert any(sample["tag"] == "h1" for sample in samples)
    if page == "teams":
        assert sum(sample["tag"] == "strong" and re.match(r"\d+\. ", sample["text"]) is not None
                   for sample in samples) == 32, "all loaded rankings must be measured"
    else:
        assert any(sample["id"] == "what-mattered-h" for sample in samples)
        assert sum(sample["tag"] == "h2" for sample in samples) >= 10, "recaps must be measured"
    failures = [sample for sample in samples if sample["ratio"] < 4.5]
    assert not failures, f"{page} {viewport} {scheme} contrast below 4.5:1: {failures}"


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


def test_missing_historical_recap_falls_back_to_saved_card(tmp_path):
    public = tmp_path / "public"
    shutil.copytree(PUBLIC, public)
    (public / "recaps" / "week5.html").unlink()
    proc = subprocess.run(
        ["node", str(PROBE), str(public), "--skip-linked-contrast"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"{proc.stderr}\n{proc.stdout}"
    official = json.loads(proc.stdout)["official"]
    assert official
    assert all(href.endswith("/output/live/2026-week-05.json") for href in official)
