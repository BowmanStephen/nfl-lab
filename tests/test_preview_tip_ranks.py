"""Preview tips rank the same way the existing EPA sentences do.

Higher offensive numbers rank better (1st is the best offense). Lower
defensive EPA allowed ranks better (1st is the stingiest defense). Ranks are
among all 32 teams in the week-4 snapshot the previews were written from.
"""
from __future__ import annotations

import json
from pathlib import Path

from nfl_lab.config import ROOT

STATS = ROOT / "pipeline" / "output" / "team_stats.json"
PREVIEW = ROOT / "public" / "previews" / "week5.html"


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def ranks(teams: list[dict], key: str, higher_better: bool) -> dict[str, int]:
    rows = [(team["team"], team[key]) for team in teams if team.get(key) is not None]
    rows.sort(key=lambda row: ((-row[1] if higher_better else row[1]), row[0]))
    out: dict[str, int] = {}
    index = 0
    while index < len(rows):
        nxt = index + 1
        while nxt < len(rows) and rows[nxt][1] == rows[index][1]:
            nxt += 1
        for tied in range(index, nxt):
            out[rows[tied][0]] = index + 1
        index = nxt
    return out


def test_rank_direction_matches_existing_epa_sentences():
    teams = json.loads(STATS.read_text())["teams"]
    html = PREVIEW.read_text()
    offense = ranks(teams, "off_epa", higher_better=True)
    defense = ranks(teams, "def_epa", higher_better=False)
    assert len(offense) == 32
    assert len(defense) == 32
    assert ordinal(offense["SF"]) == "1st"
    assert ordinal(offense["DAL"]) == "2nd"
    assert ordinal(offense["TB"]) == "32nd"
    assert ordinal(defense["MIN"]) == "1st"
    assert ordinal(defense["DAL"]) == "31st"
    assert "1st of 32" in html
    assert "+0.19 allowed, 31st of 32" in html


def test_newcomer_tips_publish_those_ranks():
    teams = json.loads(STATS.read_text())["teams"]
    html = PREVIEW.read_text()
    success = ranks(teams, "off_success", higher_better=True)
    early = ranks(teams, "off_early_epa", higher_better=True)
    explosive = ranks(teams, "off_explosive_rate", higher_better=True)
    passing = ranks(teams, "off_pass_epa", higher_better=True)
    expected = [
        f"49% of snaps ({ordinal(success['CHI'])} of 32)",
        f"39% ({ordinal(success['GB'])} of 32)",
        f"−0.08 EPA/play ({ordinal(early['NE'])} of 32)",
        f"−0.03 ({ordinal(early['LV'])} of 32)",
        f"5.3% of snaps ({ordinal(explosive['DEN'])} of 32)",
        f"6.1% ({ordinal(explosive['LAC'])} of 32)",
        f"+0.54 EPA per pass play ({ordinal(passing['SF'])} of 32)",
    ]
    for phrase in expected:
        assert phrase in html
