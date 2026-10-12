"""Live pick cards.

A card is written once, before kickoff, with the ESPN DraftKings number at that
moment. Later runs may fill the pre-kickoff snapshot and the final score.
They do not change the pick or the pick-time line.

Closing-line value compares those two ESPN DraftKings numbers. nflverse closes
stay on the historical ledger only.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from .config import LIVE_DIR, OUTPUT_DIR, PRE_KICKOFF_MINUTES
from .odds_espn import MissingLineError

ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")

# Display copy for the spent holdout. Not a regrade.
HOLDOUT_NOTE = (
    "2026 live record starts with these picks. "
    "Holdout record 48.8% ATS vs 52.4% break-even stays as-is."
)


def locked_rule() -> tuple[float, float]:
    path = OUTPUT_DIR / "backtest" / "preregistration.json"
    prereg = json.loads(path.read_text())
    rule = prereg["headline_rule"]
    return float(rule["spread_edge_min"]), float(rule["total_edge_min"])


def captured_ct(captured_at: str) -> datetime:
    dt = datetime.fromisoformat(captured_at)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(CT)


def format_lock_label(week: int, captured_at: str) -> str:
    """The sentence the site shows for an official card. Clock is Central Time."""
    clock = captured_ct(captured_at).strftime("%a %b %-d %-I:%M %p")
    return (
        f"Official week-{int(week)} picks, locked {clock} CT, "
        "DraftKings lines at lock"
    )


def apply_unclear_starter_nopick(games: list[dict], game_id: str) -> dict:
    """Do not score one game whose starter is unconfirmed.

    The locked edge rule runs first. If it already leaves both the spread and
    the total unqualified, record that reason and leave the flags alone. If it
    would have scored either market, clear the flags and record the starter
    reason. Model numbers and the pick-time line stay as the pipeline wrote them.
    """
    for game in games:
        if game.get("game_id") != game_id:
            continue
        sel = game["selection"]
        spread_q = bool(sel["spread_qualifies"])
        total_q = bool(sel["total_qualifies"])
        spread_abs = abs(float(sel["spread_edge"]))
        total_abs = abs(float(sel["total_edge"]))
        if not spread_q and not total_q:
            sel["no_pick_reason"] = (
                "No pick: the locked rule already excludes this game "
                f"(|spread edge| {spread_abs:.2f} < 2 and "
                f"|total edge| {total_abs:.2f} < 3). "
                "Washington's starter is unclear; that did not change the card."
            )
            return game
        sel["locked_rule_would_qualify"] = {"spread": spread_q, "total": total_q}
        sel["spread_qualifies"] = False
        sel["total_qualifies"] = False
        sel["no_pick_reason"] = (
            "No pick: Washington's starter is unclear. "
            "The locked rule would have scored this game; it is not a pick."
        )
        return game
    raise MissingLineError(
        f"{game_id}: not on the card. Refusing to skip the unclear-starter check."
    )


def card_path(season: int, week: int):
    return LIVE_DIR / f"{season}-week-{int(week):02d}.json"


def _num(value) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return float(value)


def kickoff_from_schedule(gameday: str, gametime: str | None) -> datetime | None:
    if not gameday or not gametime or (isinstance(gametime, float) and math.isnan(gametime)):
        return None
    text = str(gametime).strip()
    if len(text) == 4:
        text = "0" + text
    try:
        local = datetime.strptime(f"{gameday} {text}", "%Y-%m-%d %H:%M").replace(tzinfo=ET)
    except ValueError:
        return None
    return local.astimezone(UTC)


def spread_clv(pick_team: str, home_team: str, pick_margin: float, close_margin: float) -> float:
    """Positive when the home-margin line moves toward the side we picked."""
    toward_home = close_margin - pick_margin
    return toward_home if pick_team == home_team else -toward_home


def total_clv(pick: str, pick_total: float, close_total: float) -> float:
    """Positive when the total moves toward over/under as picked."""
    toward_over = close_total - pick_total
    return toward_over if pick == "over" else -toward_over


def grade_spread(pick_team: str, home_team: str, actual_margin: float, line_margin: float) -> str:
    ats = round(actual_margin - line_margin, 4)
    if ats == 0:
        return "push"
    home_covered = ats > 0
    picked_home = pick_team == home_team
    return "win" if home_covered == picked_home else "loss"


def grade_total(pick: str, actual_total: float, line_total: float) -> str:
    diff = round(actual_total - line_total, 4)
    if diff == 0:
        return "push"
    went_over = diff > 0
    return "win" if went_over == (pick == "over") else "loss"


def total_is_active(selection: dict) -> bool:
    """A totals pick is scored only when it cleared the locked rule and was not voided.

    ``total_qualifies`` stays as the lock wrote it. ``total_voided`` is a later
    decision on that market alone, so a spread on the same game still counts.
    """
    return bool(selection.get("total_qualifies")) and not selection.get("total_voided")


def _line_block(captured_at: str, line: dict) -> dict:
    if line.get("missing") or line.get("home_margin") is None or line.get("total") is None:
        raise MissingLineError(
            f"{line.get('away_team')} @ {line.get('home_team')}: ESPN DraftKings line is missing"
        )
    return {
        "captured_at": captured_at,
        "captured_at_ct": captured_ct(captured_at).isoformat(),
        "provider": "DraftKings",
        "source": "espn_scoreboard",
        "home_margin": float(line["home_margin"]),
        "total": float(line["total"]),
        "spread_display": line.get("spread_display"),
        "kickoff_utc": line.get("kickoff_utc"),
        "espn_id": line.get("espn_id"),
    }


def _match_line(game: dict, lines: list[dict]) -> dict:
    key = (game["away_team"], game["home_team"])
    for line in lines:
        if (line.get("away_team"), line.get("home_team")) == key:
            return line
    raise MissingLineError(
        f"{game['away_team']} @ {game['home_team']} ({game['game_id']}): "
        "no ESPN scoreboard game. Refusing to omit it."
    )


def selection_from_projection(game: dict, pick_time: dict, spread_min: float, total_min: float) -> dict:
    margin = _num(game.get("proj_margin_qb"))
    if margin is None:
        margin = _num(game.get("proj_margin"))
    total = _num(game.get("proj_total"))
    if margin is None or total is None:
        raise RuntimeError(f"{game.get('game_id')}: model margin or total missing")
    spread_edge = margin - pick_time["home_margin"]
    total_edge = total - pick_time["total"]
    spread_pick = game["home_team"] if spread_edge > 0 else game["away_team"]
    total_pick = "over" if total_edge > 0 else "under"
    return {
        "model_margin": margin,
        "base_margin": _num(game.get("proj_margin")),
        "model_total": total,
        "qb_adj_points": _num(game.get("qb_adj_points")),
        "spread_edge": spread_edge,
        "spread_pick": spread_pick,
        "spread_qualifies": abs(spread_edge) >= spread_min,
        "total_edge": total_edge,
        "total_pick": total_pick,
        "total_qualifies": abs(total_edge) >= total_min,
        "away_qb": game.get("away_qb_name"),
        "home_qb": game.get("home_qb_name"),
        "away_qb_schedule": game.get("away_qb_schedule_name"),
        "home_qb_schedule": game.get("home_qb_schedule_name"),
        "away_qb_differs": bool(game.get("away_qb_differs")),
        "home_qb_differs": bool(game.get("home_qb_differs")),
        "qb_notes": list(game.get("qb_notes") or []),
    }


def build_games(projected: list[dict], lines: list[dict], captured_at: str,
                spread_min: float, total_min: float) -> list[dict]:
    """Every scheduled game becomes a row. A missing line raises."""
    games = []
    for game in projected:
        line = _match_line(game, lines)
        block = _line_block(captured_at, line)
        kick = line.get("kickoff_utc") or None
        if kick is None:
            scheduled = kickoff_from_schedule(str(game.get("gameday") or ""), game.get("gametime"))
            kick = scheduled.isoformat() if scheduled else None
        selection = selection_from_projection(game, block, spread_min, total_min)
        games.append({
            "game_id": game["game_id"],
            "season": int(game["season"]),
            "week": int(game["week"]),
            "gameday": game.get("gameday"),
            "gametime_et": game.get("gametime"),
            "kickoff_utc": kick,
            "away_team": game["away_team"],
            "home_team": game["home_team"],
            "pick_time": block,
            "pre_kickoff": None,
            "selection": selection,
            "grading": None,
        })
    if not games:
        raise MissingLineError("pick card has no games")
    return games


def grade_game(game: dict, home_score, away_score) -> dict | None:
    sel = game["selection"]
    line = game["pick_time"]
    pre = game.get("pre_kickoff")
    try:
        have_score = not pd.isna(home_score) and not pd.isna(away_score)
    except TypeError:
        have_score = home_score is not None and away_score is not None
    if not have_score and not pre:
        return None
    grading = {
        "home_score": None,
        "away_score": None,
        "actual_margin": None,
        "actual_total": None,
        "spread_outcome": None,
        "total_outcome": None,
        "spread_clv": None,
        "total_clv": None,
        "spread_moved_toward": None,
        "total_moved_toward": None,
    }
    if have_score:
        home_score = float(home_score)
        away_score = float(away_score)
        actual_margin = home_score - away_score
        actual_total = home_score + away_score
        grading["home_score"] = home_score
        grading["away_score"] = away_score
        grading["actual_margin"] = actual_margin
        grading["actual_total"] = actual_total
        if sel["spread_qualifies"]:
            grading["spread_outcome"] = grade_spread(
                sel["spread_pick"], game["home_team"], actual_margin, line["home_margin"]
            )
        if total_is_active(sel):
            grading["total_outcome"] = grade_total(sel["total_pick"], actual_total, line["total"])
    if pre:
        if sel["spread_qualifies"]:
            clv = spread_clv(sel["spread_pick"], game["home_team"], line["home_margin"], pre["home_margin"])
            grading["spread_clv"] = clv
            grading["spread_moved_toward"] = clv > 0
        if total_is_active(sel):
            clv = total_clv(sel["total_pick"], line["total"], pre["total"])
            grading["total_clv"] = clv
            grading["total_moved_toward"] = clv > 0
    return grading


def apply_pre_kickoff(games: list[dict], lines: list[dict], captured_at: str, now: datetime) -> list[str]:
    """Fill empty pre-kickoff snapshots inside the window. Raise if a due line is missing."""
    problems = []
    window = timedelta(minutes=PRE_KICKOFF_MINUTES)
    for game in games:
        if game.get("pre_kickoff"):
            continue
        kick_raw = game.get("kickoff_utc")
        if not kick_raw:
            problems.append(f"{game['game_id']}: no kickoff time")
            continue
        kick = datetime.fromisoformat(kick_raw)
        if kick.tzinfo is None:
            kick = kick.replace(tzinfo=UTC)
        if now >= kick:
            problems.append(
                f"{game['away_team']} @ {game['home_team']}: kickoff passed with no pre-kickoff ESPN line"
            )
            continue
        if kick - now > window:
            continue
        try:
            line = _match_line(game, lines)
            game["pre_kickoff"] = _line_block(captured_at, line)
        except MissingLineError as exc:
            problems.append(str(exc))
    if problems:
        raise MissingLineError("; ".join(problems))
    return [g["game_id"] for g in games if g.get("pre_kickoff") and g["pre_kickoff"]["captured_at"] == captured_at]


def merge_card(existing: dict, incoming_games: list[dict]) -> dict:
    """Keep selection and pick-time lines. Allow pre-kickoff fill and grading refresh."""
    by_id = {g["game_id"]: g for g in incoming_games}
    if set(by_id) != {g["game_id"] for g in existing["games"]}:
        raise MissingLineError(
            "slate no longer matches the frozen pick card. Refusing to drop or add a game quietly."
        )
    merged = []
    for old in existing["games"]:
        new = by_id[old["game_id"]]
        row = json.loads(json.dumps(old))
        if row.get("pre_kickoff") is None and new.get("pre_kickoff"):
            row["pre_kickoff"] = new["pre_kickoff"]
        row["grading"] = new.get("grading")
        merged.append(row)
    existing = dict(existing)
    existing["games"] = merged
    return existing


def health_summary(games: list[dict]) -> dict:
    """One line for the home page. Pushes are counted and left out of the rate."""
    settled = []
    moved = []
    clvs = []
    for game in games:
        grading = game.get("grading") or {}
        sel = game["selection"]
        if sel["spread_qualifies"] and grading.get("spread_outcome"):
            settled.append(grading["spread_outcome"])
        if total_is_active(sel) and grading.get("total_outcome"):
            settled.append(grading["total_outcome"])
        if sel["spread_qualifies"] and grading.get("spread_moved_toward") is not None:
            moved.append(bool(grading["spread_moved_toward"]))
            clvs.append(float(grading["spread_clv"]))
        if total_is_active(sel) and grading.get("total_moved_toward") is not None:
            moved.append(bool(grading["total_moved_toward"]))
            clvs.append(float(grading["total_clv"]))
    wins = settled.count("win")
    losses = settled.count("loss")
    pushes = settled.count("push")
    decided = wins + losses
    rate = (wins / decided) if decided else None
    if decided == 0:
        line = "Live 2026 record: no settled picks yet. Judged once after week 18."
    else:
        pct = 100 * rate
        line = f"Live 2026 record: {wins}–{losses}, {pushes} pushes ({pct:.1f}%). Judged once after week 18."
    return {
        "line": line,
        "settled_picks": decided + pushes,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "cover_rate": rate,
        "clv_samples": len(clvs),
        "moved_toward_rate": (sum(moved) / len(moved)) if moved else None,
        "average_clv": (sum(clvs) / len(clvs)) if clvs else None,
    }


def new_card(season: int, week: int, games: list[dict], captured_at: str) -> dict:
    spread_min, total_min = locked_rule()
    return {
        "season": season,
        "week": week,
        "created_at": captured_at,
        "created_at_ct": captured_ct(captured_at).isoformat(),
        "official_lock": True,
        "lock_label": format_lock_label(week, captured_at),
        "holdout_note": HOLDOUT_NOTE,
        "line_source": "espn_draftkings",
        "same_book_clv": "ESPN DraftKings at pick time vs ESPN DraftKings pre-kickoff. Not nflverse.",
        "rule": {"spread_edge_min": spread_min, "total_edge_min": total_min},
        "model_note": (
            "Margin is the frozen 2016–2021 model plus the starting-QB adjustment "
            "checked on 2016–2021 only. That adjustment is not in the 2022–2025 ledger."
        ),
        "games": games,
        "health": health_summary(games),
    }


def save_card(card: dict) -> None:
    path = card_path(card["season"], card["week"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(card, indent=2) + "\n")


def load_card(season: int, week: int) -> dict | None:
    path = card_path(season, week)
    if not path.exists():
        return None
    return json.loads(path.read_text())
