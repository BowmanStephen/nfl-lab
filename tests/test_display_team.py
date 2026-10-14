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

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

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
    out = subprocess.run(
        ["node", str(RENDER)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(out.stdout)


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


def test_rendered_pages_use_lar_for_the_rams():
    rendered = _render()
    pages = dict(rendered["pages"])
    pages.update(_static_pages())
    assert pages["home"], "home page did not render"
    assert "couldn't load" not in pages["home"]
    assert "LAR -13.5" in _visible(pages["home"])
    rams_row = next(block for block in _blocks(pages["home"]) if "LAR -13.5" in _visible(block))
    assert re.search(r'class="chip">LAR<', rams_row)
    assert not re.search(r'class="chip">LA<', rams_row)

    visible = {name: _visible(source) for name, source in pages.items()}
    for name, text in visible.items():
        assert _rams_label(text) is None, f"{name} shows a Rams abbreviation other than LAR"
        for group in ALIAS_GROUPS:
            found = group.intersection(_tokens(text))
            assert len(found) <= 1, f"{name} mixes {sorted(found)} for one team"

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
