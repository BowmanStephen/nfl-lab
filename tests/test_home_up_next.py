"""Home pins one Up next row when the next kickoff is not one of our spread picks."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

# Renders public/index.html with the real site.js. getElementById only resolves
# ids that are in the markup, so a missing #up-next cannot pass by accident.
RENDER = r"""
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const publicDir = process.argv[1];
const nowIso = process.argv[2];
const html = fs.readFileSync(path.join(publicDir, "index.html"), "utf8");
const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]));

class El {
  constructor(id) {
    this.id = id;
    const tag = html.match(new RegExp(`<[^>]*\\bid="${id}"[^>]*>`));
    this.hidden = Boolean(tag && /\shidden\b/.test(tag[0]));
    this._html = "";
  }
  set textContent(value) { this._html = value == null ? "" : String(value); }
  get textContent() { return this._html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim(); }
  set innerHTML(value) { this._html = value == null ? "" : String(value); }
  get innerHTML() { return this._html; }
  setAttribute() {}
  getAttribute() { return ""; }
  addEventListener() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
  closest() { return null; }
  scrollIntoView() {}
}

const elements = new Map();
function getElementById(id) {
  if (!ids.has(id)) return null;
  if (!elements.has(id)) elements.set(id, new El(id));
  return elements.get(id);
}

const jobs = [];
function trackedFetch(url) {
  const job = (async () => {
    const rel = decodeURIComponent(new URL(url, "http://nfl-lab.test/index.html").pathname).replace(/^\/+/, "");
    const full = path.resolve(publicDir, rel);
    const root = path.resolve(publicDir);
    if (full !== root && !full.startsWith(root + path.sep)) throw new Error("refusing " + url);
    const exists = fs.existsSync(full);
    return {
      ok: exists,
      status: exists ? 200 : 404,
      async json() { return JSON.parse(fs.readFileSync(full, "utf8")); },
      async text() { return fs.readFileSync(full, "utf8"); },
    };
  })();
  jobs.push(job);
  return job;
}

const document = {
  body: { dataset: { page: "home" } },
  title: "",
  getElementById,
  querySelector(sel) { return sel === "main" ? getElementById("main") : null; },
  querySelectorAll() { return []; },
};
const sandbox = {
  console, document, fetch: trackedFetch, URL, URLSearchParams,
  location: { href: "http://nfl-lab.test/index.html", search: "?now=" + encodeURIComponent(nowIso), hash: "", reload() {} },
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(publicDir, "assets", "site.js"), "utf8"), sandbox, { filename: "site.js" });

(async () => {
  for (let i = 0; i < 30; i += 1) {
    if (jobs.length === 0) break;
    const batch = jobs.splice(0, jobs.length);
    await Promise.all(batch);
    await new Promise((resolve) => setImmediate(resolve));
  }
  if (jobs.length) throw new Error("home render did not settle");
  const up = elements.get("up-next");
  const hook = sandbox.upNextTeam;
  process.stdout.write(JSON.stringify({
    hidden: !up || up.hidden,
    text: up ? up.textContent : "",
    html: up ? up.innerHTML : "",
    hook: hook ? hook("LA") : null,
  }));
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
"""


def _game(game_id, away, home, kickoff, qualifies, line, edge):
    return {
        "game_id": game_id,
        "season": 2026,
        "week": 6,
        "kickoff_utc": kickoff,
        "away_team": away,
        "home_team": home,
        "pick_time": {
            "home_margin": -2.5,
            "total": 40.5,
            "spread_display": line,
            "provider": "DraftKings",
            "captured_at": "2026-10-13T11:27:41Z",
            "captured_at_ct": "2026-10-13T06:27:41-05:00",
        },
        "pre_kickoff": None,
        "grading": None,
        "selection": {
            "model_margin": -3.0,
            "spread_edge": edge,
            "spread_pick": away,
            "spread_qualifies": qualifies,
            "total_edge": 3.2,
            "total_pick": "over",
            "total_qualifies": not qualifies,
            "total_voided": False,
            "away_qb": "Away QB",
            "home_qb": "Home QB",
            "qb_notes": [],
        },
    }


def _card(games):
    return {"season": 2026, "week": 6, "games": games, "totals_void_note": ""}


def render_home(card, now):
    with tempfile.TemporaryDirectory() as tmp:
        public = Path(tmp) / "public"
        shutil.copytree(PUBLIC, public)
        (public / "api" / "picks.json").write_text(json.dumps(card))
        proc = subprocess.run(
            ["node", "-e", RENDER, str(public), now],
            capture_output=True,
            text=True,
            check=False,
        )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_markup_pins_the_slot_above_our_picks():
    html = (PUBLIC / "index.html").read_text()
    up = html.find('id="up-next"')
    picks = html.find('id="picks-h"')
    assert up != -1 and picks != -1 and up < picks
    assert 'class="up-next" hidden' in html


def test_up_next_team_codes_go_through_one_helper():
    js = (PUBLIC / "assets" / "site.js").read_text()
    assert js.count("function upNextTeam(") == 1
    body = js.split("function upNextMarkup(g) {", 1)[1].split("\n}", 1)[0]
    assert body.count("upNextTeam(") == 3
    assert "g.away_team" not in body.replace("upNextTeam(g.away_team)", "")
    assert "g.home_team" not in body.replace("upNextTeam(g.home_team)", "")
    card = _card([
        _game("2026_06_LA_SEA", "LA", "SEA", "2026-10-16T00:15:00Z", False, "LA -3.5", 0.4),
    ])
    row = render_home(card, "2026-10-14T18:00:00Z")
    shown = row["hook"]
    assert f"{shown} at SEA, Thu 7:15 PM CT" in row["text"]
    assert f"Vegas says {shown} -3.5" in row["text"]


def test_up_next_row_when_next_kickoff_is_not_a_pick():
    """SEA at DEN is next and is not a spread pick, even with a qualifying total."""
    card = _card([
        _game("2026_06_SEA_DEN", "SEA", "DEN", "2026-10-16T00:15:00Z", False, "SEA -2.5", 0.4),
        _game("2026_06_LAR_SF", "LAR", "SF", "2026-10-18T20:15:00Z", False, "SF -3", 0.2),
        _game("2026_06_CHI_GB", "CHI", "GB", "2026-10-19T00:20:00Z", True, "GB -6.5", 2.5),
    ])
    row = render_home(card, "2026-10-14T18:00:00Z")
    assert row["hidden"] is False
    assert "SEA at DEN, Thu 7:15 PM CT" in row["text"]
    assert "Vegas says SEA -2.5" in row["text"]
    assert "LAR at SF" not in row["text"]
    assert "Up next" in row["text"]


def test_up_next_row_absent_when_next_kickoff_is_a_pick():
    card = _card([
        _game("2026_06_CHI_GB", "CHI", "GB", "2026-10-16T00:15:00Z", True, "GB -6.5", 2.5),
        _game("2026_06_SEA_DEN", "SEA", "DEN", "2026-10-18T17:00:00Z", False, "SEA -2.5", 0.4),
    ])
    row = render_home(card, "2026-10-14T18:00:00Z")
    assert row["hidden"] is True
    assert row["html"] == ""
    assert "SEA at DEN" not in row["text"]


def test_up_next_rolls_to_the_following_unplayed_game():
    card = _card([
        _game("2026_06_SEA_DEN", "SEA", "DEN", "2026-10-16T00:15:00Z", False, "SEA -2.5", 0.4),
        _game("2026_06_HOU_JAX", "HOU", "JAX", "2026-10-18T13:30:00Z", False, "JAX -3", 0.3),
    ])
    row = render_home(card, "2026-10-16T02:00:00Z")
    assert row["hidden"] is False
    assert "HOU at JAX, Sun 8:30 AM CT" in row["text"]
    assert "Vegas says JAX -3" in row["text"]
    assert "SEA at DEN" not in row["text"]


def test_up_next_hidden_when_no_unplayed_games_remain():
    card = _card([
        _game("2026_06_SEA_DEN", "SEA", "DEN", "2026-10-16T00:15:00Z", False, "SEA -2.5", 0.4),
        _game("2026_06_HOU_JAX", "HOU", "JAX", "2026-10-18T13:30:00Z", False, "JAX -3", 0.3),
    ])
    row = render_home(card, "2026-10-20T12:00:00Z")
    assert row["hidden"] is True
    assert row["html"] == ""
