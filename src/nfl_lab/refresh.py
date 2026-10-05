"""Reload nflverse inputs and publish this week's card. Does not regrade 2022–2025."""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from .config import (
    LIVE_SEASON,
    LIVE_START_WEEK,
    OUTPUT_DIR,
    PRE_KICKOFF_MINUTES,
    PRIOR_SEASONS,
)
from .data_loader import filter_offensive_plays, load_injuries, load_depth_charts, load_pbp, load_schedules
from .model import ModelParams, project_games
from .odds_espn import MissingLineError, fetch_week_lines
from .picks import (
    apply_pre_kickoff,
    build_games,
    card_path,
    grade_game,
    health_summary,
    load_card,
    locked_rule,
    merge_card,
    new_card,
    save_card,
)
from .publish import publish_card, write_site
from . import qb_adjust
from .ratings import build_current_ratings
from .team_stats import compute_season_team_stats

UTC = ZoneInfo("UTC")
CT = ZoneInfo("America/Chicago")


def log(msg: str) -> None:
    print(msg, flush=True)


def live_week(schedules: pd.DataFrame) -> int:
    cur = schedules[schedules["season"] == LIVE_SEASON].copy()
    if "game_type" in cur.columns:
        cur = cur[cur["game_type"] == "REG"]
    cur = cur[cur["week"] >= LIVE_START_WEEK]
    open_games = cur[cur["home_score"].isna()]
    if len(open_games):
        return int(open_games["week"].min())
    if len(cur):
        return int(cur["week"].max())
    raise RuntimeError(f"no {LIVE_SEASON} regular-season games from week {LIVE_START_WEEK}")


def slate_for(schedules: pd.DataFrame, week: int) -> pd.DataFrame:
    cur = schedules[(schedules["season"] == LIVE_SEASON) & (schedules["week"] == week)].copy()
    if "game_type" in cur.columns:
        cur = cur[cur["game_type"] == "REG"]
    if cur.empty:
        raise RuntimeError(f"no schedule rows for {LIVE_SEASON} week {week}")
    return cur


def weekly_team_epa(pbp: pd.DataFrame, through_week: int) -> list[dict]:
    plays = pbp[(pbp["season"] == LIVE_SEASON) & (pbp["week"] <= through_week)].copy()
    if "season_type" in plays.columns:
        plays = plays[plays["season_type"] == "REG"]
    plays = filter_offensive_plays(plays)
    rows = []
    weeks = sorted(int(w) for w in plays["week"].unique())
    teams = sorted(set(plays["posteam"].dropna()).union(set(plays["defteam"].dropna())))
    for team in teams:
        for week in weeks:
            off = plays[(plays["posteam"] == team) & (plays["week"] == week)]
            deff = plays[(plays["defteam"] == team) & (plays["week"] == week)]
            if len(off) == 0 and len(deff) == 0:
                continue
            rows.append({
                "team": team,
                "week": week,
                "off_epa": float(off["epa"].mean()) if len(off) else None,
                "def_epa": float(deff["epa"].mean()) if len(deff) else None,
            })
    return rows


def _locked_params() -> tuple[ModelParams, dict]:
    locked = json.loads((OUTPUT_DIR / "backtest" / "locked_model.json").read_text())["locked_model"]
    qb = json.loads((OUTPUT_DIR / "backtest" / "qb_adjustment_validation.json").read_text())
    if not qb.get("adopt"):
        raise RuntimeError("QB adjustment was not adopted on the 2016–2021 check")
    params = ModelParams(
        points_per_net_epa=locked["points_per_net_epa"],
        hfa=locked["hfa"],
        margin_sigma=locked["margin_sigma"],
        base_total=locked["base_total"],
        points_per_combined_off=locked["points_per_combined_off"],
    )
    return params, qb["coefs"]


def _project(schedules, pbp, depth, injuries, week: int):
    through = week - 1
    params, coefs = _locked_params()
    locked = json.loads((OUTPUT_DIR / "backtest" / "locked_model.json").read_text())["locked_model"]
    log(f"ratings for week {week} use plays through week {through}")
    ratings = build_current_ratings(
        pbp,
        season=LIVE_SEASON,
        through_week=through,
        prior_seasons=list(PRIOR_SEASONS),
        prior_plays_equiv=locked["prior_plays_equiv"],
        prior_regress=locked["prior_regress"],
    )
    slate = slate_for(schedules, week)
    proj = project_games(slate, ratings, params)
    db = qb_adjust.load_dropbacks(range(LIVE_SEASON - 3, LIVE_SEASON + 1), pbp=pbp)
    proj = qb_adjust.apply_to_slate(
        proj, slate, db, LIVE_SEASON, week, coefs, depth=depth, injuries=injuries
    )
    stats = compute_season_team_stats(pbp, LIVE_SEASON, through_week=through)
    weekly = weekly_team_epa(pbp, through)
    return ratings, stats, weekly, proj, slate, through


def _with_grades(games: list[dict], slate: pd.DataFrame) -> list[dict]:
    scores = slate.set_index("game_id")
    out = []
    for game in games:
        row = dict(game)
        if game["game_id"] in scores.index:
            rec = scores.loc[game["game_id"]]
            row["grading"] = grade_game(game, rec.get("home_score"), rec.get("away_score"))
        out.append(row)
    return out


def _due(games: list[dict], now: datetime) -> bool:
    from datetime import timedelta
    window = timedelta(minutes=PRE_KICKOFF_MINUTES)
    for game in games:
        if game.get("pre_kickoff") or not game.get("kickoff_utc"):
            continue
        kick = datetime.fromisoformat(game["kickoff_utc"])
        if kick.tzinfo is None:
            kick = kick.replace(tzinfo=UTC)
        if now >= kick or kick - now <= window:
            return True
    return False


def run(mode: str = "refresh") -> dict:
    now = datetime.now(UTC)
    captured_at = now.isoformat()
    existing = None

    if mode == "line-snapshot":
        # Fast path: do not rebuild ratings. The pick is already frozen.
        # Week is discovered from the newest card at or after the live start.
        cards = sorted(card_path(LIVE_SEASON, w) for w in range(LIVE_START_WEEK, 23))
        present = [p for p in cards if p.exists()]
        if not present:
            raise MissingLineError("no pick card yet. Run `nfl-lab pick-card` before kickoff.")
        existing = json.loads(present[-1].read_text())
        if not _due(existing["games"], now):
            log("no pre-kickoff snapshots are due")
            return existing
        lines = fetch_week_lines(existing["season"], existing["week"])
        games = json.loads(json.dumps(existing["games"]))
        apply_pre_kickoff(games, lines, captured_at, now)
        for game in games:
            if not game.get("pre_kickoff"):
                continue
            prev = game.get("grading") or {}
            game["grading"] = grade_game(game, prev.get("home_score"), prev.get("away_score"))
        existing["games"] = games
        existing["health"] = health_summary(existing["games"])
        save_card(existing)
        publish_card(existing, datetime.now(CT))
        log(f"pre-kickoff lines saved to {card_path(existing['season'], existing['week'])}")
        return existing

    log("loading nflverse schedules, play-by-play, depth chart, injuries")
    seasons = list(range(LIVE_SEASON - 3, LIVE_SEASON + 1))
    schedules = load_schedules(seasons)
    pbp = load_pbp(seasons, force_years=[LIVE_SEASON])
    depth = load_depth_charts(LIVE_SEASON, force=True)
    injuries = load_injuries(LIVE_SEASON, force=True)
    week = live_week(schedules)
    existing = load_card(LIVE_SEASON, week)
    ratings, stats, weekly, proj, slate, through = _project(schedules, pbp, depth, injuries, week)
    records = json.loads(proj.to_json(orient="records"))
    spread_min, total_min = locked_rule()

    if existing is None:
        log(f"no pick card for {LIVE_SEASON} week {week}; snapshotting ESPN DraftKings")
        lines = fetch_week_lines(LIVE_SEASON, week)
        games = build_games(records, lines, captured_at, spread_min, total_min)
        if _due(games, now):
            apply_pre_kickoff(games, lines, captured_at, now)
        games = _with_grades(games, slate)
        card = new_card(LIVE_SEASON, week, games, captured_at)
    else:
        log(f"pick card already frozen ({existing['created_at']}); leaving picks and pick-time lines")
        incoming = json.loads(json.dumps(existing["games"]))
        if _due(incoming, now):
            lines = fetch_week_lines(LIVE_SEASON, week)
            apply_pre_kickoff(incoming, lines, captured_at, now)
        incoming = _with_grades(incoming, slate)
        card = merge_card(existing, incoming)
        card["health"] = health_summary(card["games"])

    save_card(card)
    generated = datetime.now(CT)
    summary = write_site(card, ratings, stats, through, weekly, generated)
    log(
        f"week {week}: {summary['n_spread_picks']} spread picks, "
        f"{summary['n_total_picks']} total picks, {summary['n_games']} games snapshotted"
    )
    log(card["health"]["line"])
    return card


def print_backtest() -> None:
    results = json.loads((OUTPUT_DIR / "backtest" / "backtest_results.json").read_text())
    hold = results["HEADLINE_holdout"]["locked_rule"]
    spread, total = hold["spread"], hold["total"]
    def rec(r):
        rate = 100 * r["win_rate"]
        return f"{r['wins']}-{r['losses']}-{r['pushes']} ({rate:.1f}%)"
    print("Spent holdout 2022–2025, graded once. Not a target.")
    print(f"  spreads {rec(spread)}")
    print(f"  totals  {rec(total)}")
    print("Live proof is 2026 from week 5. See PRODUCT.md.")
