"""Reload nflverse inputs and publish this week's card. Does not regrade 2022–2025."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
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
from .odds_espn import MissingLineError, PartialSnapshot, fetch_week_lines
from .picks import (
    annotate_close_fallback,
    apply_pre_kickoff,
    apply_unclear_starter_nopick,
    build_games,
    card_path,
    closes_from_schedule,
    grade_game,
    health_summary,
    load_card,
    locked_rule,
    merge_card,
    new_card,
    save_card,
)
from .publish import publish_card, write_site
from . import calibration, qb_adjust
from .ratings import build_current_ratings
from .team_stats import compute_season_team_stats
from .walkforward import with_signfix_totals

UTC = ZoneInfo("UTC")
CT = ZoneInfo("America/Chicago")


def log(msg: str) -> None:
    print(msg, flush=True)


def _clock() -> datetime:
    """Wall clock for kickoff checks. Tests replace this."""
    return datetime.now(UTC)


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
    locked = with_signfix_totals(
        json.loads((OUTPUT_DIR / "backtest" / "locked_model.json").read_text())["locked_model"])
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
    v2 = calibration.load_v2()
    if calibration.applies(v2, LIVE_SEASON, week):
        # Margin calibration v2 (fit on 2016-2021 only), from 2026 week 6 on. See CHANGES.md.
        log(f"week {week}: using {v2['model_version']} (fit on 2016-2021)")
        proj = calibration.project_slate(slate, schedules, ratings, v2, LIVE_SEASON, week)
        coefs = {"points_per_qb_epa_db": v2["qb"]["points_per_qb_epa_db"], "margin_sigma": v2["qb"]["margin_sigma"]}
    else:
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


def _kickoff(game: dict) -> datetime | None:
    raw = game.get("kickoff_utc")
    if not raw:
        return None
    kick = datetime.fromisoformat(raw)
    if kick.tzinfo is None:
        kick = kick.replace(tzinfo=UTC)
    return kick


def _due(games: list[dict], now: datetime) -> bool:
    window = timedelta(minutes=PRE_KICKOFF_MINUTES)
    for game in games:
        if game.get("pre_kickoff"):
            continue
        kick = _kickoff(game)
        if kick is None:
            continue
        if now >= kick or kick - now <= window:
            return True
    return False


def _past_without_line(games: list[dict], now: datetime) -> bool:
    for game in games:
        if game.get("pre_kickoff"):
            continue
        kick = _kickoff(game)
        if kick is not None and now >= kick:
            return True
    return False


def _closes_for(season: int, week: int) -> dict:
    schedules = load_schedules([season], force_seasons=[season])
    slate = schedules[(schedules["season"] == season) & (schedules["week"] == week)].copy()
    if "game_type" in slate.columns:
        slate = slate[slate["game_type"] == "REG"]
    return closes_from_schedule(slate)


def _stored_this_run(games: list[dict], captured_at: str) -> bool:
    return any((g.get("pre_kickoff") or {}).get("captured_at") == captured_at for g in games)


def _kickoff_already_passed(lines: list[dict], now: datetime) -> bool:
    for line in lines:
        kick = _kickoff({"kickoff_utc": line.get("kickoff_utc")})
        if kick is not None and now >= kick:
            return True
    return False


def season_games(current: dict | None = None) -> list[dict]:
    """Every live card's games. ``current`` replaces the copy already on disk for its week."""
    by_week: dict[int, dict] = {}
    for week in range(LIVE_START_WEEK, 23):
        card = load_card(LIVE_SEASON, week)
        if card:
            by_week[week] = card
    if current is not None:
        by_week[int(current["week"])] = current
    games: list[dict] = []
    for week in sorted(by_week):
        games.extend(by_week[week]["games"])
    return games


def season_health(current: dict | None = None) -> dict:
    """Live record across every saved week, not just the card being published."""
    return health_summary(season_games(current))


def _capture_closes(games: list[dict], captured_at: str, now: datetime, season: int, week: int,
                    lines: list[dict] | None = None, closes: dict | None = None) -> str | None:
    """Store ESPN lines that are due, and nflverse closes after a missed snapshot.

    Returns the fail-loud message when something is still missing. Lines that
    were stored stay on ``games`` so the caller can save them before exiting.
    ESPN is fetched before any nflverse reload. A reload failure then leaves
    the DraftKings lines already in hand, and only the kicked games stay open.
    ``closes`` is the nflverse map. When it is omitted and a kickoff has passed,
    the live season schedule is reloaded so the close is current.
    """
    if lines is None:
        try:
            lines = fetch_week_lines(season, week, now=now)
        except MissingLineError as exc:
            log(f"ESPN lines unavailable ({exc}); nflverse close is the fallback for games already kicked")
            lines = []
    if closes is None and _past_without_line(games, now):
        try:
            closes = _closes_for(season, week)
        except Exception as exc:  # noqa: BLE001 — keep the ESPN lines already fetched
            log(f"nflverse close reload failed ({exc}); already-kicked games stay unresolved")
            closes = {}
    if closes is None:
        closes = {}
    message = None
    try:
        apply_pre_kickoff(games, lines, captured_at, now, closes)
    except MissingLineError as exc:
        message = str(exc)
    for game in games:
        pre = game.get("pre_kickoff") or {}
        if pre.get("captured_at") == captured_at:
            log(f"{game['away_team']} @ {game['home_team']}: close stored from {pre.get('source')}")
    return message


def _persist_captured(card: dict, games: list[dict], captured_at: str, generated: datetime,
                      message: str | None) -> None:
    """Write a partial capture, then fail if a line is still missing."""
    if message and not _stored_this_run(games, captured_at):
        raise MissingLineError(message)
    card["games"] = games
    annotate_close_fallback(card)
    card["health"] = season_health(card)
    save_card(card)
    publish_card(card, generated)
    if message:
        raise PartialSnapshot(message)


def _grade_saved_card(card: dict, schedules: pd.DataFrame, now: datetime) -> dict:
    """Fill a missed close and write final scores onto a card that is already over."""
    slate = slate_for(schedules, int(card["week"]))
    games = json.loads(json.dumps(card["games"]))
    captured_at = now.isoformat()
    message = None
    if _due(games, now):
        message = _capture_closes(
            games, captured_at, now, int(card["season"]), int(card["week"]),
            closes=closes_from_schedule(slate),
        )
    games = _with_grades(games, slate)
    graded = dict(card)
    graded["games"] = games
    annotate_close_fallback(graded)
    graded["health"] = health_summary(graded["games"])
    save_card(graded)
    if message:
        raise PartialSnapshot(message)
    return graded


def _finalize_completed_weeks(schedules: pd.DataFrame, now: datetime) -> list[int]:
    """Grade weeks that are already finished before ``live_week`` moves on.

    Once every score in a week is filled, ``live_week`` returns the next week.
    The card that just ended has to be graded first, or its picks never settle
    and drop out of the live record.
    """
    current = live_week(schedules)
    graded: list[int] = []
    for week in range(LIVE_START_WEEK, current):
        card = load_card(LIVE_SEASON, week)
        if card is None:
            continue
        log(f"grading finished {LIVE_SEASON} week {week} before week {current}")
        _grade_saved_card(card, schedules, now)
        graded.append(week)
    return graded


def _next_card(schedules, pbp, depth, injuries):
    """Build (but do not save) the live week's card."""
    week = live_week(schedules)
    existing = load_card(LIVE_SEASON, week)
    ratings, stats, weekly, proj, slate, through = _project(schedules, pbp, depth, injuries, week)
    records = json.loads(proj.to_json(orient="records"))
    spread_min, total_min = locked_rule()

    if existing is None:
        now = _clock()
        log(f"no pick card for {LIVE_SEASON} week {week}; snapshotting ESPN DraftKings")
        lines = fetch_week_lines(LIVE_SEASON, week, now=now)
        if _kickoff_already_passed(lines, now):
            raise MissingLineError(
                "kickoff passed before the pick card could be created. "
                "Refusing to lock a post-kickoff line."
            )
        captured_at = now.isoformat()
        games = build_games(records, lines, captured_at, spread_min, total_min)
        if LIVE_SEASON == 2026 and int(week) == 5:
            noted = apply_unclear_starter_nopick(games, "2026_05_NYG_WAS")
            log(noted["selection"]["no_pick_reason"])
        message = None
        if _due(games, now):
            message = _capture_closes(
                games, captured_at, now, LIVE_SEASON, week, lines=lines,
                closes=closes_from_schedule(slate),
            )
        games = _with_grades(games, slate)
        card = new_card(LIVE_SEASON, week, games, captured_at)
        if calibration.applies(calibration.load_v2(), LIVE_SEASON, week):
            card["model_version"] = "v2-margin-calibration"
            card["model_note"] = (
                "Margin and total are model v2 (scoring-margin rating with a per-season-segment scale; "
                "totals from sign-fixed EPA plus scoring levels), all fit on 2016-2021 only, plus the "
                "starting-QB adjustment refit on 2016-2021. v2 is not in the 2022-2025 ledger.")
    else:
        now = _clock()
        captured_at = now.isoformat()
        log(f"pick card already frozen ({existing['created_at']}); leaving picks and pick-time lines")
        incoming = json.loads(json.dumps(existing["games"]))
        message = None
        if _due(incoming, now):
            message = _capture_closes(
                incoming, captured_at, now, LIVE_SEASON, week,
                closes=closes_from_schedule(slate),
            )
        incoming = _with_grades(incoming, slate)
        card = merge_card(existing, incoming)

    return week, card, message, captured_at, ratings, stats, weekly, through


def run(mode: str = "refresh") -> dict:
    now = _clock()
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
        now = _clock()
        captured_at = now.isoformat()
        games = json.loads(json.dumps(existing["games"]))
        message = _capture_closes(games, captured_at, now, existing["season"], existing["week"])
        for game in games:
            if not game.get("pre_kickoff"):
                continue
            prev = game.get("grading") or {}
            game["grading"] = grade_game(game, prev.get("home_score"), prev.get("away_score"))
        _persist_captured(existing, games, captured_at, datetime.now(CT), message)
        log(f"pre-kickoff lines saved to {card_path(existing['season'], existing['week'])}")
        return existing

    log("loading nflverse schedules, play-by-play, depth chart, injuries")
    seasons = list(range(LIVE_SEASON - 3, LIVE_SEASON + 1))
    schedules = load_schedules(seasons, force_seasons=[LIVE_SEASON])
    pbp = load_pbp(seasons, force_years=[LIVE_SEASON])
    depth = load_depth_charts(LIVE_SEASON, force=True)
    injuries = load_injuries(LIVE_SEASON, force=True)
    # The downloads above can outlast a kickoff. Grade a week that just ended
    # before live_week() steps past it, then read the clock again at capture.
    now = _clock()
    graded_weeks = _finalize_completed_weeks(schedules, now)
    try:
        week, card, message, captured_at, ratings, stats, weekly, through = _next_card(
            schedules, pbp, depth, injuries)
    except PartialSnapshot:
        raise
    except Exception as exc:
        if not graded_weeks:
            raise
        # The finished week is already graded and saved. Exit 2 so the
        # workflow commits it, then the job still fails on the next card.
        raise PartialSnapshot(
            f"graded {LIVE_SEASON} week(s) {graded_weeks} saved, "
            f"but the next pick card failed: {type(exc).__name__}: {exc}"
        ) from exc
    annotate_close_fallback(card)
    card["health"] = season_health(card)
    if message and not _stored_this_run(card["games"], captured_at):
        raise MissingLineError(message)
    save_card(card)
    generated = datetime.now(CT)
    summary = write_site(card, ratings, stats, through, weekly, generated)
    if message:
        raise PartialSnapshot(message)
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
