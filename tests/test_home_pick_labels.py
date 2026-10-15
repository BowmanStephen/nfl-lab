"""Home pick rows show a lean label and the plain pick, not a win percentage.

Live-data tests derive every expected value from public/api/picks.json, so they
stay green whatever week it is, including graded picks and weeks with no
qualifying picks.
Underdog '+', strong lean, and pick'em are checked against a fixed fixture card.
"""
from copy import deepcopy
import html as htmllib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE_JS = ROOT / "public" / "assets" / "site.js"
PICKS = ROOT / "public" / "api" / "picks.json"
STRONG = float(re.search(r"STRONG_LEAN_EDGE = ([\d.]+)", SITE_JS.read_text()).group(1))
NOW = "2026-01-01T00:00:00Z"  # before kickoff; scored games still render as final

SCRIPT = r"""
const site = require(process.argv[1]);
const card = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));
const now = Date.parse(process.argv[3]);
const picks = card.games.filter((g) => g.selection.spread_qualifies);
console.log(JSON.stringify({
  rows: picks.map((g) => site.gameRow(g, "pre", now)),
  labels: picks.map((g) => [g.selection.spread_edge, site.leanLabel(g)]),
  official: picks.map((g) => site.officialLine(g, {})),
}));
"""


def _game(gid, away, home, home_margin, pick, edge, kickoff="2026-12-06T18:00Z"):
    return {
        "game_id": gid, "season": 2026, "week": 14, "kickoff_utc": kickoff,
        "away_team": away, "home_team": home,
        "pick_time": {"captured_at_ct": "2026-12-01T06:00:00-06:00", "provider": "DraftKings",
                      "home_margin": home_margin, "total": 44.5,
                      "spread_display": f"{home if home_margin >= 0 else away} -{abs(home_margin)}" if home_margin else "PK",
                      "kickoff_utc": kickoff},
        "selection": {"model_margin": home_margin + (edge if pick == home else -edge),
                      "model_total": 45.0, "spread_edge": edge if pick == home else -edge,
                      "spread_pick": pick, "spread_qualifies": True,
                      "total_edge": 0.5, "total_pick": "over", "total_qualifies": False,
                      "away_qb": "QB A", "home_qb": "QB H", "qb_notes": []},
        "grading": None,
    }


FIXTURE = {"season": 2026, "week": 14, "games": [
    _game("FX_FAV", "AAA", "BBB", 3.0, "BBB", STRONG + 0.5),     # favorite, strong lean
    _game("FX_DOG", "CCC", "DDD", 10.5, "CCC", STRONG - 1.0),    # away underdog, lean
    _game("FX_PK", "EEE", "FFF", 0.0, "FFF", 2.0),               # pick'em
]}


def _node():
    node = shutil.which("node")
    if node is None:
        pytest.fail("node is required for site.js rendering tests")
    return node


def _run(card_path):
    out = subprocess.run([_node(), "-e", SCRIPT, str(SITE_JS), str(card_path), NOW],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@pytest.fixture
def fixture_card(tmp_path):
    p = tmp_path / "card.json"
    p.write_text(json.dumps(FIXTURE))
    return p


def _gid(g):
    return re.sub(r"[^\w-]", "", str(g["game_id"]))


def _rows_by_id(card, rows):
    picks = [g for g in card["games"] if g["selection"]["spread_qualifies"]]
    out = {}
    for g in picks:
        match = [h for h in rows if f'id="b-{_gid(g)}"' in h]
        assert len(match) == 1, _gid(g)
        out[_gid(g)] = (g, match[0])
    return out


def _text(html):
    """Visible text only (screen-reader-only spans removed)."""
    html = re.sub(r'<span class="sr-only">[^<]*</span>', " ", html)
    return htmllib.unescape(" ".join(re.sub(r"<[^>]+>", " ", html).split()))


def _expected(g):
    team = g["selection"]["spread_pick"]
    hm = g["pick_time"]["home_margin"]
    signed = -hm if team == g["home_team"] else hm
    if signed > 0:
        shown, spoken = f"+{abs(signed):.1f}", f"plus {abs(signed):.1f}"
    elif signed < 0:
        shown, spoken = f"\u2212{abs(signed):.1f}", f"minus {abs(signed):.1f}"
    else:
        shown, spoken = "(pick'em)", "pick'em"
    label = "Strong lean" if abs(g["selection"]["spread_edge"]) >= STRONG else "Lean"
    display_team = "LAR" if team == "LA" else team
    return f"Take {display_team} {shown}", f"Take {display_team} {spoken}", label


def _check_rows(card, rows):
    by_id = _rows_by_id(card, rows)
    assert len(by_id) == len(rows)
    for g, html in by_id.values():
        text = _text(html)
        grading = g.get("grading") or {}
        if grading.get("home_score") is not None and grading.get("away_score") is not None:
            assert 'class="game-row pick-row final"' in html
            assert f"Final: {g['away_team']} {grading['away_score']} · {g['home_team']} {grading['home_score']}" in text
            assert f"We had {g['selection']['spread_pick']} " in text
            assert 'class="take num"' not in html
            assert 'class="lean' not in html
            continue
        shown, spoken, label = _expected(g)
        assert text.startswith(f"{shown} "), text
        h = html.replace("&#39;", "'")
        assert f'<span class="take-pick" aria-hidden="true">{shown}</span>' in h
        assert f'<span class="sr-only">{spoken}</span>' in h
        take = re.search(r'<span class="take num">(.*?)\n', h).group(1)
        assert "aria-label" not in take and 'class="lean' not in take
        assert re.search(r'<span class="when">.*?<span class="lean(?: strong)?">'
                         + re.escape(label) + r'</span></span>', h)
        assert not re.search(r"\d+(\.\d+)?\s*%", text), text
        vegas = re.search(r"Vegas says ([^.]*(?:\.\d)?)\.", text).group(1)
        assert "-" not in vegas and vegas == re.sub(r"^LA\b", "LAR", g["pick_time"]["spread_display"]).replace("-", "\u2212"), vegas
        assert "title=" not in html
    return by_id


# ---- live data: expectations derived from picks.json (any week, any count) ----

def test_live_rows_match_picks_data():
    card = json.loads(PICKS.read_text())
    data = _run(PICKS)
    n = sum(1 for g in card["games"] if g["selection"]["spread_qualifies"])
    assert len(data["rows"]) == n
    _check_rows(card, data["rows"])
    for edge, label in data["labels"]:
        assert label == ("Strong lean" if abs(edge) >= STRONG else "Lean")
    for line, (_, label) in zip(data["official"], data["labels"]):
        assert line.endswith(f"({label})")


def test_single_lean_cutoff():
    js = SITE_JS.read_text()
    assert js.count("STRONG_LEAN_EDGE = ") == 1


# ---- fixture card: fixed cases independent of the live week ----

def test_fixture_rows(fixture_card):
    data = _run(fixture_card)
    by_id = _check_rows(FIXTURE, data["rows"])
    assert set(by_id) == {"FX_FAV", "FX_DOG", "FX_PK"}


def test_fixture_underdog_shows_plus(fixture_card):
    by_id = _rows_by_id(FIXTURE, _run(fixture_card)["rows"])
    _, html = by_id["FX_DOG"]
    assert _text(html).startswith("Take CCC +10.5 "), _text(html)
    assert '<span class="sr-only">Take CCC plus 10.5</span>' in html


def test_fixture_favorite_strong_lean(fixture_card):
    by_id = _rows_by_id(FIXTURE, _run(fixture_card)["rows"])
    _, html = by_id["FX_FAV"]
    assert _text(html).startswith("Take BBB \u22123.0 "), _text(html)
    assert 'class="lean strong"' in html
    assert '<span class="sr-only">Take BBB minus 3.0</span>' in html


def test_fixture_pickem(fixture_card):
    by_id = _rows_by_id(FIXTURE, _run(fixture_card)["rows"])
    _, html = by_id["FX_PK"]
    assert _text(html).startswith("Take FFF (pick'em) "), _text(html)
    assert "Take FFF pick'em</span>" in html.replace("&#39;", "'")


@pytest.mark.parametrize("graded_count", [1, len(FIXTURE["games"])])
def test_rows_with_graded_picks(tmp_path, graded_count):
    card = deepcopy(FIXTURE)
    for g in card["games"][:graded_count]:
        g["grading"] = {"home_score": 24, "away_score": 17, "actual_margin": 7,
                        "spread_outcome": "win"}
    path = tmp_path / "graded-card.json"
    path.write_text(json.dumps(card))
    data = _run(path)
    assert len(data["rows"]) == len(card["games"])
    _check_rows(card, data["rows"])


@pytest.mark.parametrize("home_margin", [3.0, -3.0])
def test_rams_pick_keeps_display_label_and_price(tmp_path, home_margin):
    game = _game("FX_RAMS", "SEA", "LA", home_margin, "LA", STRONG + 0.5)
    card = {"games": [game]}
    path = tmp_path / "rams-pick.json"
    path.write_text(json.dumps(card))
    data = _run(path)
    _check_rows(card, data["rows"])
    sign = "-" if home_margin > 0 else "+"
    assert data["official"] == [f"LAR {sign}3.0 (Strong lean)"]
    assert "Take LA " not in _text(data["rows"][0])


@pytest.mark.parametrize("home_margin, pick, expected", [
    (1.5, "BBB", "BBB must win by 2 or more points."),
    (13.5, "AAA", "AAA can win, tie, or lose by up to 13 points."),
    (-3.5, "AAA", "AAA must win by 4 or more points."),
    (-2.5, "BBB", "BBB can win, tie, or lose by up to 2 points."),
    (3, "BBB", "BBB must win by 4 or more points. A 3-point win is a push, counted as neither a win nor a loss."),
    (3, "AAA", "AAA can win, tie, or lose by up to 2 points. A 3-point loss is a push, counted as neither a win nor a loss."),
    (0, "BBB", "BBB must win. A tied game is a push, counted as neither a win nor a loss."),
    (0.5, "AAA", "AAA can win or tie."),
])
def test_row_explains_the_saved_spread_result(tmp_path, home_margin, pick, expected):
    game = _game("FX_RESULT", "AAA", "BBB", home_margin, pick, 2.5)
    path = tmp_path / "card.json"
    path.write_text(json.dumps({"games": [game]}))
    row = _text(_run(path)["rows"][0])
    assert expected in row


@pytest.mark.parametrize("edge, expected", [
    (3.49, "Lean means a model-versus-line gap below 3.5 points."),
    (3.5, "Strong lean means a model-versus-line gap of 3.5 points or more."),
    (-3.5, "Strong lean means a model-versus-line gap of 3.5 points or more."),
])
def test_row_defines_lean_using_the_existing_cutoff(tmp_path, edge, expected):
    game = _game("FX_LEAN", "AAA", "BBB", 3, "BBB", edge)
    path = tmp_path / "card.json"
    path.write_text(json.dumps({"games": [game]}))
    assert expected in _text(_run(path)["rows"][0])


def test_missing_saved_line_does_not_invent_a_pickem_explanation(tmp_path):
    game = _game("FX_MISSING", "AAA", "BBB", 0, "BBB", 2.5)
    game["pick_time"]["home_margin"] = None
    path = tmp_path / "card.json"
    path.write_text(json.dumps({"games": [game]}))
    assert "The saved spread is unavailable." in _text(_run(path)["rows"][0])


@pytest.mark.parametrize("state, hidden", [("pre", False), ("no-picks", True), ("final", True)])
def test_pick_helper_only_shows_with_relevant_picks(tmp_path, state, hidden):
    public = tmp_path / "public"
    shutil.copytree(ROOT / "public", public)
    card = deepcopy(FIXTURE)
    for game in card["games"]:
        if state == "no-picks":
            game["selection"]["spread_qualifies"] = False
        if state == "final":
            game["grading"] = {"home_score": 24, "away_score": 17,
                               "actual_margin": 7, "spread_outcome": "win"}
    (public / "api" / "picks.json").write_text(json.dumps(card))
    out = subprocess.run(
        [_node(), str(ROOT / "tests" / "render_site.mjs"), str(public), NOW, "home"],
        capture_output=True, text=True, check=True,
    )
    help_text = json.loads(out.stdout)["home"]["picks-help"]
    assert help_text["hidden"] is hidden
    assert "spread" in help_text["text"] and "Lean" in help_text["text"]
