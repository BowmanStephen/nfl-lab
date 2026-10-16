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
        timeout=180,
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
@pytest.mark.parametrize("page", ["home", "last_week", "teams", "model", "glossary", "ledger", "ledger_expanded", "freshness", "replay", "preview6"])
def test_page_interaction_contrast(highlight, viewport, scheme, state, page):
    result = (highlight["contrast"][viewport]["screen"][scheme] if page == "home"
              else highlight["linkedContrast"][page.removesuffix("_expanded")][viewport][scheme])
    if page == "ledger_expanded":
        result = result["expanded"]
        assert result["wasClosed"] and result["isOpen"], "Enter must open the bettors section"
    assert result["viewport"] == {"width": 390 if viewport == "mobile" else 1280,
                                  "height": 844 if viewport == "mobile" else 900,
                                  "mobileLayout": viewport == "mobile"}
    assert result["screen"] and not result["print"]
    assert result["dark"] is (scheme == "dark")
    interactions = result["interactions"]
    if page == "preview6":
        assert sum(target["officialPick"] for target in interactions["targets"]) == 14
    if page == "ledger_expanded":
        labels = {target["label"] for target in interactions["targets"]}
        assert {"Holdout record by season", "Live 2026 picks"} <= labels
    elif page == "ledger":
        assert not any(target["label"] == "Live 2026 picks" for target in interactions["targets"])
    targets = {target["index"] for target in interactions["targets"]
               if state == "focus" or target["hoverable"]}
    assert len(targets) >= 10, f"must exercise real {page} controls"
    assert {entry["index"] for entry in interactions[state]} == targets
    for entry in interactions[state]:
        result = entry["result"]
        reached = result["hovered"] if state == "hover" else result["focused"] and result["focusVisible"]
        assert reached, f"{page} {viewport} {scheme} {state} control {entry['index']}: {result['samples']}"
        assert result["samples"], f"control {entry['index']} had no visible text"
        failures = [sample for sample in result["samples"] if sample["ratio"] < 4.5]
        assert not failures, f"{page} {viewport} {scheme} {state} control {entry['index']}: {failures}"
        if state == "focus":
            assert result["outline"]["style"] not in {"none", "hidden"}
            assert result["outline"]["width"] > 0
            assert result["outline"]["ratio"] >= 3, result["outline"]


@pytest.mark.parametrize("page", ["last_week", "teams", "model", "glossary", "ledger", "ledger_expanded", "freshness", "replay", "preview6"])
@pytest.mark.parametrize("viewport", ["mobile", "desktop"])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_linked_page_text_contrast(highlight, page, viewport, scheme):
    result = highlight["linkedContrast"][page.removesuffix("_expanded")][viewport][scheme]
    if page == "ledger_expanded":
        result = result["expanded"]
    samples = result["samples"]
    assert any(sample["tag"] == "h1" for sample in samples)
    if page == "teams":
        assert sum(sample["tag"] == "strong" and re.match(r"\d+\. ", sample["text"]) is not None
                   for sample in samples) == 32, "all loaded rankings must be measured"
    elif page == "last_week":
        assert any(sample["id"] == "what-mattered-h" for sample in samples)
        assert sum(sample["tag"] == "h2" for sample in samples) >= 10, "recaps must be measured"
    elif page == "model":
        for caption in ["ratings-caption", "week5-caption", "live-label"]:
            assert any(sample["id"] == caption for sample in samples)
        assert sum(sample["tag"] == "span" and sample["text"] in {"SF", "LAR", "JAX"}
                   for sample in samples) >= 3, "loaded rating labels must be measured"
    elif page == "glossary":
        assert sum(sample["tag"] == "h2" for sample in samples) >= 12, "definitions must be measured"
        assert any(sample["tag"] == "td" and "EPA per play" in sample["text"] for sample in samples)
    elif page.startswith("ledger"):
        assert any(sample["id"] == "tr-scope" and sample["text"] != "…" for sample in samples)
        assert sum(sample["tag"] == "h3" and sample["text"].startswith("Week ") for sample in samples) >= 5
        assert any(sample["tag"] == "summary" and sample["text"] == "For bettors" for sample in samples)
        if page == "ledger_expanded":
            for element in ["spread-rec", "total-rec", "live-health"]:
                assert any(sample["id"] == element and sample["text"] != "…" for sample in samples)
            assert sum(sample["tag"] == "td" and sample["text"] in {"2022", "2023", "2024", "2025"}
                       for sample in samples) == 4, "holdout table must be measured"
    elif page == "freshness":
        assert any(sample["id"] == "when" and sample["text"].startswith("Updated ")
                   and "…" not in sample["text"] for sample in samples), "loaded timestamp must be measured"
    elif page == "replay":
        assert any(sample["id"] == "rec-caption" and "games graded" in sample["text"] for sample in samples)
        assert any(sample["id"] == "rc-foot" and sample["text"].startswith("Backtest generated ") for sample in samples)
        assert sum(sample["tag"] == "h3" for sample in samples) == 3, "all lessons must be measured"
        for week in range(1, 5):
            assert any(sample["tag"] == "span" and sample["text"] == f"Week {week}" for sample in samples)
    else:
        assert any(sample["tag"] == "h1" and sample["text"] == "Week 6 previews" for sample in samples)
        assert sum(sample["tag"] == "h2" for sample in samples) == 14, "all game previews must be measured"
        assert any(sample["tag"] == "p" and sample["text"].startswith("These previews do not change") for sample in samples)
    failures = [sample for sample in samples if sample["ratio"] < 4.5]
    assert not failures, f"{page} {viewport} {scheme} contrast below 4.5:1: {failures}"


@pytest.mark.parametrize("viewport", ["mobile", "desktop"])
@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("page,charts", [
    ("model", {"winrate-chart": 7, "mae-chart": 5}),
    ("replay", {"rc-winrate": 7, "rc-context": 5}),
])
def test_svg_chart_text_contrast(highlight, viewport, scheme, page, charts):
    result = highlight["linkedContrast"][page][viewport][scheme]
    assert result["viewport"]["width"] == (390 if viewport == "mobile" else 1280)
    assert result["dark"] is (scheme == "dark")
    svg = result["svgContrast"]
    assert result["svgOcclusionError"].startswith("Later SVG paint overlaps text:"), \
        "a rectangle painted over the labels must fail the probe"
    assert svg["charts"] == len(charts)
    for chart, count in charts.items():
        labels = [sample for sample in svg["samples"] if sample["chart"] == chart]
        assert len(labels) == count, f"{chart}: every rendered label must be measured"
        values = [sample for sample in labels if sample["className"] == "val"]
        assert len(values) == 2
        assert all(all(bg["source"] in {"bar-fill", "bar-miss"} for bg in sample["backgrounds"])
                   for sample in values), "values must be measured against the bars"
        axes = [sample for sample in labels if sample["className"] in {"axis", "label"}]
        assert all(all(bg["source"] == "paper" for bg in sample["backgrounds"]) for sample in axes)
    failures = [sample for sample in svg["samples"] if sample["ratio"] < 4.5]
    assert not failures, f"{page} {viewport} {scheme} SVG text below 4.5:1: {failures}"


@pytest.mark.parametrize("viewport", ["mobile", "desktop"])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_model_game_row_hover_contrast(highlight, viewport, scheme):
    interactions = highlight["linkedContrast"]["model"][viewport][scheme]["rowInteractions"]
    assert len(interactions["targets"]) >= 10, "loaded game rows must be exercised"
    assert {entry["index"] for entry in interactions["hover"]} == {
        target["index"] for target in interactions["targets"]}
    for entry in interactions["hover"]:
        result = entry["result"]
        assert result["hovered"], entry
        assert result["samples"], entry
        failures = [sample for sample in result["samples"] if sample["ratio"] < 4.5]
        assert not failures, f"model {viewport} {scheme} row {entry['index']}: {failures}"


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
