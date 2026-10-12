"""Thin adapter for the public ESPN NFL scoreboard and game summary.

Unofficial endpoints. No API key. They can change or disappear.
Pick-time and pre-kickoff lines both come from DraftKings on ESPN, so a
same-book comparison uses one book twice.

The scoreboard is the first read. On Oct 11 2026 it returned the Sunday games
and then omitted DraftKings while those games were still inside the pre-kickoff
window. The game summary's pickcenter block is the second read, and only before
kickoff. A line taken after kickoff is not written back as the pre-kickoff snapshot.

Home margin uses the same convention as nflverse spread_line in this lab:
positive means the home team is favored by that many points.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
ESPN_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary"
PROVIDER = "DraftKings"
UTC = ZoneInfo("UTC")
# ESPN abbreviations that differ from the lab's nflverse abbreviations.
ESPN_TO_LAB = {"WSH": "WAS", "LAR": "LA", "JAC": "JAX"}


class MissingLineError(RuntimeError):
    """A scheduled game has no DraftKings spread or total. The job must stop."""


def lab_abbr(abbreviation: str) -> str:
    abbr = (abbreviation or "").upper()
    return ESPN_TO_LAB.get(abbr, abbr)


def home_margin_from_odds(odds: dict) -> float:
    """Betting spread on the home team (negative = home favored) -> home margin."""
    try:
        raw = odds["pointSpread"]["home"]["close"]["line"]
        text = str(raw).replace("+", "").strip()
        betting_spread = float(text)
    except (KeyError, TypeError, ValueError) as exc:
        raise MissingLineError(f"DraftKings home spread missing or unreadable ({exc})") from exc
    return -betting_spread


def total_from_odds(odds: dict) -> float:
    try:
        return float(odds["overUnder"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MissingLineError(f"DraftKings total missing or unreadable ({exc})") from exc


def draftkings_odds(competition: dict) -> dict | None:
    for odds in competition.get("odds") or []:
        name = ((odds.get("provider") or {}).get("name") or "").strip().lower()
        if name == PROVIDER.lower():
            return odds
    return None


def parse_scoreboard(payload: dict) -> list[dict]:
    """One dict per event that has a usable DraftKings spread and total."""
    lines = []
    for event in payload.get("events") or []:
        competitions = event.get("competitions") or []
        if not competitions:
            continue
        comp = competitions[0]
        competitors = comp.get("competitors") or []
        try:
            home = next(c for c in competitors if c.get("homeAway") == "home")
            away = next(c for c in competitors if c.get("homeAway") == "away")
        except StopIteration:
            continue
        odds = draftkings_odds(comp)
        if odds is None:
            lines.append({
                "espn_id": str(event.get("id") or ""),
                "kickoff_utc": event.get("date"),
                "away_team": lab_abbr(away["team"]["abbreviation"]),
                "home_team": lab_abbr(home["team"]["abbreviation"]),
                "provider": None,
                "home_margin": None,
                "total": None,
                "spread_display": None,
                "missing": True,
            })
            continue
        margin = home_margin_from_odds(odds)
        total = total_from_odds(odds)
        lines.append({
            "espn_id": str(event.get("id") or ""),
            "kickoff_utc": event.get("date"),
            "away_team": lab_abbr(away["team"]["abbreviation"]),
            "home_team": lab_abbr(home["team"]["abbreviation"]),
            "provider": PROVIDER,
            "home_margin": margin,
            "total": total,
            "spread_display": odds.get("details"),
            "missing": False,
            "source": "espn_scoreboard",
        })
    return lines


def _kickoff(raw: str | None) -> datetime | None:
    if not raw:
        return None
    kick = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if kick.tzinfo is None:
        kick = kick.replace(tzinfo=UTC)
    return kick


def home_margin_from_pickcenter(odds: dict) -> float:
    """DraftKings pickcenter spread -> lab home margin.

    Prefer the same ``pointSpread.home.close.line`` field the scoreboard uses.
    If that block is absent, ``spread`` is the home betting line when it is
    signed, and the favorite flag is the check when it is only a magnitude.
    """
    if isinstance(odds.get("pointSpread"), dict):
        return home_margin_from_odds(odds)
    try:
        spread = float(odds["spread"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MissingLineError(f"DraftKings pickcenter spread missing or unreadable ({exc})") from exc
    home = odds.get("homeTeamOdds") or {}
    favorite = home.get("favorite")
    if favorite is True and spread > 0:
        spread = -spread
    elif favorite is False and spread < 0:
        spread = -spread
    elif favorite is None:
        raise MissingLineError("DraftKings pickcenter does not say whether home is favored")
    return -spread


def line_from_summary(summary: dict, stub: dict) -> dict | None:
    """Copy a DraftKings pickcenter line onto a scoreboard stub that had none."""
    odds = None
    for item in summary.get("pickcenter") or []:
        name = ((item.get("provider") or {}).get("name") or "").strip().lower()
        if name == PROVIDER.lower():
            odds = item
            break
    if odds is None:
        return None
    try:
        margin = home_margin_from_pickcenter(odds)
        total = total_from_odds(odds)
    except MissingLineError:
        return None
    updated = dict(stub)
    updated.update({
        "provider": PROVIDER,
        "home_margin": margin,
        "total": total,
        "spread_display": odds.get("details"),
        "missing": False,
        "source": "espn_summary",
    })
    return updated


def fill_missing_from_summaries(lines: list[dict], fetch_summary_fn, now: datetime | None = None) -> list[dict]:
    """Fill DraftKings from the game summary when the scoreboard omitted it.

    Games whose kickoff has already passed are left missing. The pre-kickoff
    slot is not back-filled from a post-game read.
    """
    filled = []
    for line in lines:
        if not line.get("missing") or not line.get("espn_id"):
            filled.append(line)
            continue
        kick = _kickoff(line.get("kickoff_utc"))
        if now is not None and kick is not None and now >= kick:
            filled.append(line)
            continue
        try:
            summary = fetch_summary_fn(str(line["espn_id"]))
        except MissingLineError:
            filled.append(line)
            continue
        patched = line_from_summary(summary, line)
        filled.append(patched or line)
    return filled


def fetch_scoreboard(season: int, week: int, timeout: int = 30) -> dict:
    url = f"{ESPN_SCOREBOARD}?week={int(week)}&year={int(season)}&seasontype=2"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "nfl-lab/0.1 (research; keyless)", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except Exception as exc:  # noqa: BLE001 — surface any transport/parse failure loudly
        raise MissingLineError(f"ESPN scoreboard request failed for {season} week {week}: {exc}") from exc


def fetch_summary(espn_id: str, timeout: int = 20) -> dict:
    url = f"{ESPN_SUMMARY}?event={espn_id}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "nfl-lab/0.1 (research; keyless)", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except Exception as exc:  # noqa: BLE001 — surface any transport/parse failure loudly
        raise MissingLineError(f"ESPN summary request failed for event {espn_id}: {exc}") from exc


def fetch_week_lines(season: int, week: int, now: datetime | None = None) -> list[dict]:
    lines = parse_scoreboard(fetch_scoreboard(season, week))
    return fill_missing_from_summaries(lines, fetch_summary, now)
