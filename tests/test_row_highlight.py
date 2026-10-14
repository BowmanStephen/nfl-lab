"""An official-pick anchor tints the row, then the tint fades."""
from __future__ import annotations

from nfl_lab.config import ROOT

CSS = (ROOT / "public" / "assets" / "site.css").read_text()
JS = (ROOT / "public" / "assets" / "site.js").read_text()


def test_pick_rows_are_anchored_list_items():
    assert '<li class="game-row ${cls}" id="b-${id}">' in JS
    assert 'href = `../index.html#b-${id}`' in JS
    # Rows exist only after the card loads, so the hash has to be applied again or :target never matches.
    assert "location.replace(location.pathname + location.search + location.hash)" in JS


def test_target_tint_uses_accent_and_fades():
    assert "li:target" in CSS
    assert "var(--accent)" in CSS
    assert "@keyframes target-row-fade" in CSS
    assert "animation: target-row-fade 2.5s ease forwards" in CSS


def test_reduced_motion_keeps_a_static_tint():
    block = CSS.split("@media (prefers-reduced-motion: reduce)")[-1]
    assert "li:target" in block
    assert "animation: none" in block
    assert "var(--accent)" in block
