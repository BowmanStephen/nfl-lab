"""Thin adapter for the public ESPN NFL scoreboard.

Unofficial endpoint. No API key. It can change or disappear.
Pick-time and pre-kickoff lines both come from here, and only from DraftKings,
so closing-line value compares one book to itself.

Home margin uses the same convention as nflverse spread_line in this lab:
positive means the home team is favored by that many points.
"""
from __future__ import annotations

import json
import urllib.request

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
PROVIDER = "DraftKings"
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
        })
    return lines


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


def fetch_week_lines(season: int, week: int) -> list[dict]:
    return parse_scoreboard(fetch_scoreboard(season, week))
