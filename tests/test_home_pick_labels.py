"""Home pick rows show a lean label, not a win percentage; totals are paused."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE_JS = ROOT / "public" / "assets" / "site.js"
PICKS = ROOT / "public" / "api" / "picks.json"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

SCRIPT = r"""
const site = require(process.argv[1]);
const card = require(process.argv[2]);
const now = Date.parse("2026-10-14T12:00:00Z");
const picks = card.games.filter((g) => g.selection.spread_qualifies);
const rows = picks.map((g) => site.gameRow(g, "pre", now));
console.log(JSON.stringify({
  rows,
  labels: picks.map((g) => [g.selection.spread_edge, site.leanLabel(g)]),
  note: site.TOTALS_PAUSED_NOTE,
  official: picks.map((g) => site.officialLine(g, {})),
}));
"""


def _run():
    out = subprocess.run(["node", "-e", SCRIPT, str(SITE_JS), str(PICKS)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_pick_rows_have_lean_label_and_no_percentage():
    data = _run()
    assert data["rows"], "spreads should still be listed"
    for html in data["rows"]:
        text = re.sub(r"<[^>]+>", " ", html)
        assert not re.search(r"\d+(\.\d+)?\s*%", text), text
        assert ("Strong lean" in text) or ("Lean" in text)
        assert "title=" not in html
    for edge, label in data["labels"]:
        assert label == ("Strong lean" if abs(edge) >= 3.5 else "Lean")


def test_totals_paused_note_present_and_totals_not_listed():
    js = SITE_JS.read_text()
    assert "Over/under picks are paused while we fix that model." in js
    assert 'id="totals-paused"' in js
    data = _run()
    for html in data["rows"]:
        assert "Over " not in html and "Under " not in html


def test_spread_picks_still_listed():
    card = json.loads(PICKS.read_text())
    n = sum(1 for g in card["games"] if g["selection"]["spread_qualifies"])
    assert len(_run()["rows"]) == n > 0


def test_previews_use_same_lean_label():
    data = _run()
    for line, (_, label) in zip(data["official"], data["labels"]):
        assert line.endswith(f"({label})")
    js = SITE_JS.read_text()
    assert js.count("STRONG_LEAN_EDGE = ") == 1



def _rows_by_id():
    card = json.loads(PICKS.read_text())
    picks = [g for g in card["games"] if g["selection"]["spread_qualifies"]]
    rows = _run()["rows"]
    out = {}
    for g in picks:
        gid = re.sub(r"[^\w-]", "", str(g["game_id"]))
        match = [h for h in rows if f'id="b-{gid}"' in h]
        assert len(match) == 1, gid
        out[gid] = (g, match[0])
    return out


def _text(html):
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def test_pick_row_starts_with_take_team_line():
    for g, html in _rows_by_id().values():
        text = _text(html)
        team = g["selection"]["spread_pick"]
        signed = -g["pick_time"]["home_margin"] if team == g["home_team"] else g["pick_time"]["home_margin"]
        if signed > 0:
            line = f"+{abs(signed):.1f}"
        elif signed < 0:
            line = f"\u2212{abs(signed):.1f}"
        else:
            line = "(pick'em)"
        assert text.startswith(f"Take {team} {line} "), text
        label = "Strong lean" if abs(g["selection"]["spread_edge"]) >= 3.5 else "Lean"
        assert text.startswith(f"Take {team} {line} {label} "), text
        spoken = {"+": "plus", "\u2212": "minus"}.get(line[0])
        want = f"Take {team} {spoken} {abs(signed):.1f}" if spoken else f"Take {team} pick'em"
        assert f'aria-label="{want}"' in html.replace("&#39;", "'")


def test_underdog_pick_shows_plus():
    dogs = [(g, h) for g, h in _rows_by_id().values()
            if g["selection"]["spread_pick"] != g["home_team"] and g["pick_time"]["home_margin"] > 0]
    assert dogs, "fixture should include an underdog pick (e.g. ARI +13.5)"
    for g, html in dogs:
        assert _text(html).startswith(f"Take {g['selection']['spread_pick']} +"), _text(html)


def test_pickem_line_renders_pickem():
    script = r"""
const site = require(process.argv[1]);
const g = {home_team: "PHI", away_team: "CAR", pick_time: {home_margin: 0}, selection: {spread_pick: "PHI"}};
console.log(site.takeText(g));
"""
    out = subprocess.run(["node", "-e", script, str(SITE_JS)], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "Take PHI (pick'em)"
