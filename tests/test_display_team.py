"""Published pages show one abbreviation per team. Rams are LAR; Chargers stay LAC.

Checks rendered HTML only. Stored cards keep the nflverse code LA.
"""
import html
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
RENDER = ROOT / "tests" / "render_display_team.js"
FIXTURE = ROOT / "tests" / "fixtures" / "rams_card.json"
PICKS = PUBLIC / "api" / "picks.json"

# Same franchise, two spellings. A rendered page must not use both.
ALIAS_GROUPS = (
    {"LA", "LAR"},
)
TEAM_TOKEN = re.compile(r"\b[A-Z]{2,3}\b")


def _visible(source: str) -> str:
    labels = " ".join(re.findall(r'(?:aria-label|title)="([^"]*)"', source))
    body = re.sub(r"<script\b[^>]*>.*?</script>", " ", source, flags=re.I | re.S)
    body = re.sub(r"<style\b[^>]*>.*?</style>", " ", body, flags=re.I | re.S)
    body = re.sub(r"<[^>]+>", " ", body)
    return html.unescape(f"{labels} {body}")


def _tokens(text: str) -> list[str]:
    return TEAM_TOKEN.findall(text)


def _rams_label(text: str) -> str | None:
    return "LA" if re.search(r"\bLA\b", text) else None


def _render() -> dict:
    if shutil.which("node") is None:
        pytest.fail("node is required to render the published pages")
    proc = subprocess.run(
        ["node", str(RENDER), str(FIXTURE)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        pytest.fail(f"site render failed\n{proc.stderr}\n{proc.stdout}")
    return json.loads(proc.stdout)


def _rams_games(card: dict) -> list[dict]:
    return [g for g in card.get("games") or [] if "LA" in (g.get("home_team"), g.get("away_team"))]


def _shown_spread(game: dict) -> str:
    """Vegas line as the page prints it: a leading LA becomes LAR."""
    raw = str((game.get("pick_time") or {}).get("spread_display") or "")
    team, sep, rest = raw.partition(" ")
    shown = "LAR" if team == "LA" else team
    return f"{shown}{sep}{rest}" if sep else shown


def _game_html(source: str, game_id: str) -> str:
    marker = f"b-{game_id}"
    start = source.find(marker)
    assert start >= 0, f"rendered page is missing {game_id}"
    nxt = source.find('class="game-row', start + len(marker))
    return source[start:] if nxt < 0 else source[start:nxt]


def _static_pages() -> dict[str, str]:
    pages = {}
    for path in sorted(PUBLIC.rglob("*.html")):
        pages[str(path.relative_to(PUBLIC))] = path.read_text()
    return pages


def test_display_team_maps_rams_and_keeps_chargers():
    helper = _render()["helper"]
    assert helper["LA"] == "LAR"
    assert helper["LAR"] == "LAR"
    assert helper["LAC"] == "LAC"
    assert helper["ari"] == "ARI"
    assert helper["ramsName"] == "Los Angeles Rams"
    assert helper["chargersName"] == "Los Angeles Chargers"
    assert "LAR Chargers" not in helper.values()


def _blocks(source: str) -> list[str]:
    """One visible block per game row, team card, or table row, tags included."""
    return re.findall(
        r"<(?:div class=\"game-row|article class=\"team|tr)\b[^>]*>.*?(?=<(?:div class=\"game-row|article class=\"team|tr)\b|$)",
        source,
        flags=re.S,
    )


def _assert_rams_row(source: str, game: dict) -> None:
    """The row for this stored LA game shows LAR, including the Vegas line."""
    block = _game_html(source, game["game_id"])
    visible = _visible(block)
    assert _rams_label(visible) is None, visible
    chips = re.findall(r'class="chip">([^<]+)<', block)
    if chips:
        assert "LAR" in chips, block
        assert "LA" not in chips, block
    shown = _shown_spread(game)
    if shown:
        assert shown in visible, visible


def test_rendered_pages_use_lar_for_the_rams():
    rendered = _render()
    pages = dict(rendered["pages"])
    pages.update(_static_pages())
    assert pages["home"], "home page did not render"
    assert "couldn't load" not in pages["home"]

    card = json.loads(PICKS.read_text())
    rams = _rams_games(card)
    if rams:
        for game in rams:
            _assert_rams_row(pages["home"], game)
    else:
        assert "fixture" in pages, "bye week needs the fixture card"

    fixture_card = json.loads(FIXTURE.read_text())
    fixture_games = _rams_games(fixture_card)
    assert fixture_games, "fixture card must include an LA game"
    for game in fixture_games:
        _assert_rams_row(pages["fixture"], game)

    visible = {name: _visible(source) for name, source in pages.items()}
    for name, text in visible.items():
        assert _rams_label(text) is None, f"{name} shows a Rams abbreviation other than LAR"
        for group in ALIAS_GROUPS:
            found = group.intersection(_tokens(text))
            assert len(found) <= 1, f"{name} mixes {sorted(found)} for one team"

    assert "LAR" in _tokens(visible["fixture"])
    if rams:
        assert "LAR" in _tokens(visible["home"])
    assert "LAC" in _tokens(visible["teams"])
    assert "LAC" in _tokens(visible["model"])
    assert "Los Angeles Chargers" in visible["model"]
    assert "LAR Chargers" not in visible["model"]
    assert "Los Angeles Rams" in visible["model"]

    for name, source in pages.items():
        for block in _blocks(source):
            found = set()
            for group in ALIAS_GROUPS:
                found |= group.intersection(_tokens(_visible(block)))
            assert len(found) <= 1, f"{name} mixes {sorted(found)} in one label"
