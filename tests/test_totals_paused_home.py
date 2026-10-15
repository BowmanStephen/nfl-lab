"""Home and ledger say over/unders are paused, without a second note on a voided card.

The week-6 card's original totals_void_note is preserved in the saved card;
the public note distinguishes the corrected-model replay from the frozen record.
A card with no void note shows the pause line when totals are paused or a total
would otherwise be an active pick.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "tests" / "js" / "render_page.js"
PICKS = ROOT / "public" / "api" / "picks.json"
NOW = "2026-10-15T16:00:00Z"
NOTE = "We're not picking total points (over/under) right now while we fix that part of the model."
VOID_NOTE = (
    "The 6 week-6 over/under picks were voided Oct 15: "
    "the over/under model went 6-18 on weeks 1-4, so we've paused over/unders. "
    "The spread picks stand."
)
CLARIFIED_VOID_NOTE = (
    "The 6 week-6 over/under picks were voided Oct 15, and over/unders are paused. "
    "A replay of weeks 1-4 with the corrected totals formula went 6-18. "
    "The original frozen-model record remains 10-19; the replay does not replace it. "
    "The spread picks stand."
)


def _node():
    node = shutil.which("node")
    if node is None:
        pytest.fail("node is required for site.js rendering tests")
    return node


def _render(page, card, tmp_path):
    path = tmp_path / f"picks-{page}.json"
    path.write_text(json.dumps(card))
    out = subprocess.run(
        [_node(), str(RENDER), str(ROOT / "public"), page, str(path), NOW],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def _live():
    return json.loads(PICKS.read_text())


def test_void_note_is_the_only_home_note(tmp_path):
    card = _live()
    assert card["totals_void_note"] == VOID_NOTE
    out = _render("index.html", card, tmp_path)
    assert out["totals-void-note"]["hidden"] is False
    assert out["totals-void-note"]["text"] == CLARIFIED_VOID_NOTE
    assert out["totals-paused"]["hidden"] is True
    assert NOTE not in out["games"]["html"]
    assert "over 40.5" not in out["games"]["html"].lower()
    assert out["picks-h"]["text"] == "Our picks (4)"


def test_pause_note_shows_when_a_total_would_be_active(tmp_path):
    card = _live()
    card.pop("totals_void_note")
    game = card["games"][0]
    game["selection"]["total_voided"] = False
    game["selection"]["total_qualifies"] = True
    game["selection"]["total_pick"] = "over"
    out = _render("index.html", card, tmp_path)
    note = out["totals-paused"]
    assert note["hidden"] is False and note["text"] == NOTE
    assert "paused" not in out["games"]["html"].lower()
    page = (ROOT / "public" / "index.html").read_text()
    assert page.index('id="totals-paused"') > page.index('id="games"')
    assert re.search(
        r'id="games">.*?</li></ul>\s*<p class="totals-paused" id="totals-paused" hidden>',
        page,
    )


def test_pause_note_shows_on_a_future_card_with_no_locked_totals(tmp_path):
    card = _live()
    card.pop("totals_void_note")
    card["totals_paused"] = True
    for game in card["games"]:
        game["selection"]["total_qualifies"] = False
        game["selection"].pop("total_voided", None)
    out = _render("index.html", card, tmp_path)
    assert out["totals-paused"]["hidden"] is False
    assert out["totals-paused"]["text"] == NOTE
    assert out["totals-void-note"]["hidden"] is True


def test_pause_note_stays_hidden_when_totals_are_not_paused(tmp_path):
    card = _live()
    card.pop("totals_void_note")
    for game in card["games"]:
        game["selection"]["total_qualifies"] = False
        game["selection"].pop("total_voided", None)
    out = _render("index.html", card, tmp_path)
    assert out["totals-paused"]["hidden"] is True


def test_ledger_says_over_under_paused_instead_of_a_live_total(tmp_path):
    card = _live()
    card.pop("totals_void_note")
    game = next(g for g in card["games"] if g["selection"]["spread_qualifies"])
    game["selection"]["total_voided"] = False
    game["selection"]["total_qualifies"] = True
    game["selection"]["total_pick"] = "over"
    game["selection"]["total_edge"] = 4.0
    out = _render("ledger.html", card, tmp_path)
    live = out["live"]["html"]
    row = re.search(
        rf"<tr><td>{game['away_team']} at {game['home_team']}</td><td>([^<]*)</td>",
        live,
    ).group(1)
    assert "over/under paused" in row
    assert "pts off the total" not in live
    assert out["totals-paused"]["hidden"] is False
    assert out["totals-paused"]["text"] == NOTE


def test_ledger_keeps_the_void_note_and_skips_the_pause_line(tmp_path):
    card = _live()
    out = _render("ledger.html", card, tmp_path)
    assert out["totals-void-note"]["text"] == CLARIFIED_VOID_NOTE
    assert out["totals-paused"]["hidden"] is True
    assert "pts off the total" not in out["live"]["html"]
    assert "over/under paused" not in out["live"]["html"]


def test_other_void_notices_are_preserved(tmp_path):
    card = _live()
    card["totals_void_note"] = "A later clarification of the saved card."
    out = _render("index.html", card, tmp_path)
    assert out["totals-void-note"]["text"] == card["totals_void_note"]


def test_static_notices_explain_the_same_records():
    for path in ("public/index.html", "public/ledger.html", "public/model.html",
                 "public/previews/week6.html", "pipeline/WEEK6_PREVIEWS.md"):
        copy = (ROOT / path).read_text()
        assert CLARIFIED_VOID_NOTE in copy
        assert VOID_NOTE not in copy


def test_pause_note_is_grey():
    css = (ROOT / "public" / "assets" / "site.css").read_text()
    rule = re.search(r"\.totals-paused \{([^}]*)\}", css).group(1)
    assert "var(--muted)" in rule
    assert "caution" not in rule
