"""Write the small JSON files the static site reads, plus a freshness record."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import OUTPUT_DIR, PUBLIC_API, TEAM_NAMES
from .picks import total_is_active

CT = ZoneInfo("America/Chicago")


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def baseline_payload() -> dict:
    results = json.loads((OUTPUT_DIR / "backtest" / "backtest_results.json").read_text())
    hold = results["HEADLINE_holdout"]
    spread = hold["locked_rule"]["spread"]
    total = hold["locked_rule"]["total"]
    seasons = []
    for row in hold["descriptive_only__per_season"]:
        seasons.append({
            "season": row["season"],
            "games": row["accuracy_ats_free"]["n_games"],
            "spread": row["locked_rule_spread"],
            "total": row["locked_rule_total"],
        })
    return {
        "label": "Spent holdout. Graded once. Not a target.",
        "window": "2022–2025",
        "spread": spread,
        "total": total,
        "per_season": seasons,
        "graded_at": results.get("graded_at"),
        "locked_at": results["preregistration"]["locked_at"],
    }


def teams_payload(ratings, stats, through_week: int, weekly: list[dict]) -> dict:
    rating_idx = ratings.set_index("team")
    weekly_idx: dict[str, list] = {}
    for row in weekly:
        weekly_idx.setdefault(row["team"], []).append(row)
    teams = []
    for row in stats.to_dict(orient="records"):
        team = row["team"]
        if team not in rating_idx.index:
            continue
        r = rating_idx.loc[team]
        teams.append({
            "team": team,
            "name": TEAM_NAMES.get(team, team),
            "rating": float(r["rating"]),
            "off_epa": _f(row.get("off_epa")),
            "def_epa": _f(row.get("def_epa")),
            "off_success": _f(row.get("off_success")),
            "def_success": _f(row.get("def_success")),
            "net_epa": _f(row.get("net_epa")),
            "weekly": weekly_idx.get(team, []),
        })
    teams.sort(key=lambda t: t["rating"], reverse=True)
    return {"season": 2026, "through_week": through_week, "teams": teams}


def _f(value):
    if value is None:
        return None
    try:
        if value != value:  # NaN
            return None
    except TypeError:
        return None
    return float(value)


def publish_card(card: dict, generated_at: datetime) -> None:
    """Update the pick card the site reads without rebuilding team pages."""
    PUBLIC_API.mkdir(parents=True, exist_ok=True)
    _write(PUBLIC_API / "picks.json", card)
    summary_path = PUBLIC_API / "summary.json"
    summary = {}
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())
    summary.update({
        "generated_at": generated_at.isoformat(),
        "week": card["week"],
        "health": card["health"],
        "n_games": len(card["games"]),
        "n_spread_picks": sum(1 for g in card["games"] if g["selection"]["spread_qualifies"]),
        "n_total_picks": sum(1 for g in card["games"] if total_is_active(g["selection"])),
    })
    _write(summary_path, summary)
    _refresh_freshness(generated_at)


def _refresh_freshness(generated_at: datetime) -> None:
    now = generated_at.isoformat()
    files = []
    for path in sorted(PUBLIC_API.glob("*.json")):
        if path.name == "freshness.json":
            continue
        files.append({
            "path": f"api/{path.name}",
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "updated_at": now,
        })
    _write(PUBLIC_API / "freshness.json", {
        "generated_at": now,
        "stale_after": (generated_at + timedelta(hours=36)).isoformat(),
        "files": files,
    })


def _signed_points(value: float) -> str:
    text = f"{float(value):.1f}"
    if text.endswith(".0"):
        text = text[:-2]
    if float(value) > 0:
        text = "+" + text
    return text


def model_game_from_card(game: dict) -> dict:
    """Chart row for one official pick. Market sign matches the existing chart: negative means home is favored."""
    sel = game["selection"]
    home_margin = float(game["pick_time"]["home_margin"])
    spread_pick = None
    if sel["spread_qualifies"]:
        points = -home_margin if sel["spread_pick"] == game["home_team"] else home_margin
        spread_pick = f"{sel['spread_pick']} {_signed_points(points)}"
    total_pick = None
    if total_is_active(sel):
        word = "OVER" if sel["total_pick"] == "over" else "UNDER"
        total_pick = f"{word} {float(game['pick_time']['total']):.1f}"
    row = {
        "game": f"{game['away_team']}@{game['home_team']}",
        "away": game["away_team"],
        "home": game["home_team"],
        "kickoff_utc": game.get("kickoff_utc"),
        "market_margin_home": -home_margin,
        "model_margin_home": sel["model_margin"],
        "market_total": game["pick_time"]["total"],
        "model_total": sel["model_total"],
        "spread_edge": sel["spread_edge"],
        "total_edge": sel["total_edge"],
        "spread_pick": spread_pick,
        "total_pick": total_pick,
        "is_pick": bool(sel["spread_qualifies"] or total_is_active(sel)),
        "away_qb": sel.get("away_qb"),
        "home_qb": sel.get("home_qb"),
    }
    if sel.get("no_pick_reason"):
        row["no_pick_reason"] = sel["no_pick_reason"]
    return row


def sync_model_page(card: dict, ratings) -> None:
    """Point the model page at the official card. Leave the holdout block alone."""
    path = PUBLIC_API / "model.json"
    if not path.exists():
        return
    model = json.loads(path.read_text())
    ppe = float(model["rating_units"]["points_per_net_epa"])
    by_team = ratings.set_index("team")
    for row in model.get("ratings") or []:
        team = row.get("team")
        if team not in by_team.index:
            continue
        epa = float(by_team.loc[team]["rating"])
        row["rating_epa"] = round(epa, 6)
        row["points"] = round(epa * ppe, 2)
    model["ratings"] = sorted(model.get("ratings") or [], key=lambda r: r.get("points") or 0, reverse=True)
    model["week"] = card["week"]
    model["season"] = card["season"]
    model["games"] = [model_game_from_card(game) for game in card["games"]]
    model["live_2026"] = {
        "label": card.get("lock_label"),
        "holdout_note": card.get("holdout_note"),
        "settled_picks": card["health"]["settled_picks"],
        "wins": card["health"]["wins"],
        "losses": card["health"]["losses"],
        "pushes": card["health"]["pushes"],
    }
    source = model.setdefault("generated_from", {})
    source["official_picks"] = f"output/live/{card['season']}-week-{int(card['week']):02d}.json"
    source.pop("preview_lines", None)
    _write(path, model)


def write_site(card: dict, ratings, stats, through_week: int, weekly: list[dict], generated_at: datetime) -> dict:
    PUBLIC_API.mkdir(parents=True, exist_ok=True)
    picks_path = PUBLIC_API / "picks.json"
    teams_path = PUBLIC_API / "teams.json"
    baseline_path = PUBLIC_API / "baseline.json"
    summary_path = PUBLIC_API / "summary.json"
    _write(picks_path, card)
    _write(teams_path, teams_payload(ratings, stats, through_week, weekly))
    _write(baseline_path, baseline_payload())
    summary = {
        "generated_at": generated_at.isoformat(),
        "timezone": "America/Chicago",
        "season": card["season"],
        "week": card["week"],
        "through_week": through_week,
        "health": card["health"],
        "n_games": len(card["games"]),
        "n_spread_picks": sum(1 for g in card["games"] if g["selection"]["spread_qualifies"]),
        "n_total_picks": sum(1 for g in card["games"] if total_is_active(g["selection"])),
    }
    _write(summary_path, summary)
    sync_model_page(card, ratings)
    _refresh_freshness(generated_at)
    return summary
