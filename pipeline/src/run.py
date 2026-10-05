"""NFL Lab main pipeline — load data, stats, ratings, model, outputs."""
from __future__ import annotations

import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from .config import (
    CURRENT_SEASON,
    DATA_DIR,
    OUTPUT_DIR,
    PRIOR_SEASONS,
)
from . import walkforward
from .data_loader import data_availability_report, load_pbp, load_schedules
from .model import ModelParams, project_games
from .outputs import (
    write_backtest,
    write_previews,
    write_projections,
    write_ratings,
    write_recaps,
    write_summary,
    write_team_stats,
)
from .ratings import build_current_ratings
from .team_stats import compute_qb_stats, compute_season_team_stats


import sys

REGRADE = "--regrade-holdout" in sys.argv  # deliberate, explicit opt-in only


def refresh_aux(season: int) -> None:
    """Depth charts + injuries for the starting-QB cross-check (best effort)."""
    base = "https://github.com/nflverse/nflverse-data/releases/download"
    for name, url in [("depth", f"{base}/depth_charts/depth_charts_{season}.parquet"),
                      ("inj", f"{base}/injuries/injuries_{season}.parquet")]:
        try:
            pd.read_parquet(url).to_parquet(DATA_DIR / f"{name}_{season}.parquet", index=False)
        except Exception as e:  # noqa: BLE001
            print(f"  warning: could not refresh {name}_{season}: {e}")


def main() -> dict:
    t0 = time.time()
    tz = ZoneInfo("America/Chicago")
    now = datetime.now(tz)

    print("== NFL Lab pipeline ==")
    print(f"Local time: {now.strftime('%Y-%m-%d %H:%M %Z')}")

    seasons_needed = list(range(2013, CURRENT_SEASON + 1))  # 2013-15 = priors for 2016 tuning
    print(f"Loading schedules for {seasons_needed}...")
    schedules = load_schedules(seasons_needed, force=True)
    print(f"  schedules rows={len(schedules)}")

    print(f"Loading play-by-play for {seasons_needed}...")
    from .data_loader import CORE_PBP_COLS
    hist = load_pbp([y for y in seasons_needed if y != CURRENT_SEASON], columns=CORE_PBP_COLS)
    cur_full = load_pbp([CURRENT_SEASON], force_years=[CURRENT_SEASON])
    pbp = pd.concat([hist, cur_full], ignore_index=True)
    print(f"  pbp rows={len(pbp)}")

    avail = data_availability_report(schedules, pbp)
    print("Availability:", json.dumps({
        k: avail[k] for k in ["latest_completed_week", "upcoming_week", "remaining_this_week"]
    }, indent=2, default=str))
    for s, info in avail["seasons"].items():
        if s >= CURRENT_SEASON - 1:
            print(f"  {s}: completed weeks={info['completed_weeks']} pbp_weeks={info['pbp_weeks']} "
                  f"completed_games={info['completed_games']}")

    latest_week = avail["latest_completed_week"]
    upcoming_week = avail["upcoming_week"]
    if latest_week is None:
        raise RuntimeError("No completed games found for current season")

    # Through-week for ratings/stats: all PBP weeks available
    cur_info = avail["seasons"].get(CURRENT_SEASON, {})
    pbp_weeks = cur_info.get("pbp_weeks") or []
    through_week = max(pbp_weeks) if pbp_weeks else latest_week
    print(f"Using through_week={through_week} for ratings/stats")

    # --- Team stats ---
    print("Computing team advanced stats...")
    team_stats = compute_season_team_stats(pbp, CURRENT_SEASON, through_week=through_week)
    plays_cur = pbp[(pbp["season"] == CURRENT_SEASON) & (pbp["week"] <= through_week)]
    if "season_type" in plays_cur.columns:
        plays_cur = plays_cur[plays_cur["season_type"] == "REG"]
    from .data_loader import filter_offensive_plays
    qb_stats = compute_qb_stats(filter_offensive_plays(plays_cur), min_attempts=40)
    write_team_stats(team_stats, qb_stats)
    print(f"  teams={len(team_stats)} qbs={len(qb_stats)}")

    # --- Strict walk-forward backtest (pre-registered rule) ---
    prereg = json.loads((OUTPUT_DIR / "backtest" / "preregistration.json").read_text())
    results_path = OUTPUT_DIR / "backtest" / "backtest_results.json"
    if results_path.exists() and not REGRADE:
        # Holdout is graded ONCE. Reuse the frozen model + result; never re-grade silently.
        print("Holdout already graded; reusing frozen model from backtest_results.json")
        bt = json.loads(results_path.read_text())
    else:
        print("Walk-forward tuning (2016-2021) + holdout grading (2022-2025)...")
        bt = walkforward.run(pbp, schedules, prereg)
    write_backtest(bt)
    lm = bt["locked_model"]
    params = ModelParams(
        points_per_net_epa=lm["points_per_net_epa"], hfa=lm["hfa"], margin_sigma=lm["margin_sigma"],
        base_total=lm["base_total"], points_per_combined_off=lm["points_per_combined_off"],
    )
    h = bt["HEADLINE_holdout"]
    print("  locked:", {k: lm[k] for k in ["prior_regress", "prior_plays_equiv", "points_per_net_epa", "hfa"]})
    print("  holdout spread:", h["locked_rule"]["spread"])
    print("  holdout total:", h["locked_rule"]["total"])

    # Production ratings use the same locked hyperparameters
    ratings = build_current_ratings(
        pbp, season=CURRENT_SEASON, through_week=through_week, prior_seasons=PRIOR_SEASONS,
        prior_plays_equiv=lm["prior_plays_equiv"], prior_regress=lm["prior_regress"],
    )
    print("  top 5:", ratings.head(5)[["team", "rating"]].to_dict(orient="records"))
    print("  bottom 5:", ratings.tail(5)[["team", "rating"]].to_dict(orient="records"))
    write_ratings(ratings, params.to_dict())

    # --- Upcoming week projections + previews ---
    # Prefer full upcoming slate week; if remaining games in latest_week, include those too
    cur_sched = schedules[schedules["season"] == CURRENT_SEASON].copy()
    weeks_any_done = set(cur_sched.loc[cur_sched["home_score"].notna(), "week"])
    unscored_weeks = sorted(set(cur_sched.loc[cur_sched["home_score"].isna(), "week"]) - weeks_any_done)
    preview_week = unscored_weeks[0] if unscored_weeks else latest_week
    upcoming_games = cur_sched[
        (cur_sched["week"] == preview_week) & cur_sched["home_score"].isna()
    ].copy()
    # Also any leftover games from earlier weeks still unscored (e.g. MNF)
    leftovers = cur_sched[
        (cur_sched["week"] < preview_week) & cur_sched["home_score"].isna()
    ]
    preview_slate = pd.concat([leftovers, upcoming_games], ignore_index=True)
    print(f"Projecting {len(preview_slate)} upcoming games (week {preview_week} + leftovers)...")
    projections = project_games(preview_slate, ratings, params)
    # Starting-QB adjustment (validated on 2016-2021 only; secondary to the base model)
    refresh_aux(CURRENT_SEASON)
    qbv_path = OUTPUT_DIR / "backtest" / "qb_adjustment_validation.json"
    qb_meta = {"applied": False}
    if qbv_path.exists():
        qbv = json.loads(qbv_path.read_text())
        if qbv.get("adopt"):
            from . import qb_adjust
            db = qb_adjust.load_dropbacks(range(CURRENT_SEASON - 2, CURRENT_SEASON + 1))
            projections = qb_adjust.apply_to_slate(
                projections, preview_slate, db, CURRENT_SEASON, preview_week, qbv["coefs"])
            qb_meta = {"applied": True, "points_per_qb_epa_db": qbv["coefs"]["points_per_qb_epa_db"],
                       "depth_chart_as_of_utc": projections.attrs.get("depth_chart_as_of"),
                       "injury_report_week": projections.attrs.get("injury_report_week")}
    for wk, grp in projections.groupby("week"):
        write_projections(grp.reset_index(drop=True), int(wk))
    preview_files = write_previews(projections, team_stats, preview_week)
    print(f"  wrote {len(preview_files)} preview artifacts")

    # --- Recaps for most recent completed week ---
    recap_week = latest_week
    # If latest week still has games, recap the completed ones in that week;
    # also if week is empty of completed, step back
    recap_games = cur_sched[(cur_sched["week"] == recap_week) & cur_sched["home_score"].notna()]
    if len(recap_games) == 0 and recap_week > 1:
        recap_week = recap_week - 1
        recap_games = cur_sched[(cur_sched["week"] == recap_week) & cur_sched["home_score"].notna()]

    # Build retrospective projections for recap week (ratings through week-1)
    print(f"Building recap projections for week {recap_week}...")
    # Pre-game ratings: only weeks before the recap week (what the model knew at kickoff)
    ratings_pre = build_current_ratings(
        pbp, season=CURRENT_SEASON, through_week=recap_week - 1, prior_seasons=PRIOR_SEASONS,
        prior_plays_equiv=lm["prior_plays_equiv"], prior_regress=lm["prior_regress"],
    )
    recap_proj = project_games(recap_games, ratings_pre, params)
    proj_lookup = {g["game_id"]: g for g in recap_proj.to_dict(orient="records")}
    recap_files = write_recaps(recap_games, team_stats, proj_lookup, pbp, recap_week)
    print(f"  wrote {len(recap_files)} recap artifacts")

    # --- Summary ---
    top5 = ratings.head(5)[["team", "rating", "shrunk_off_epa", "shrunk_def_epa"]].to_dict(orient="records")
    bot5 = ratings.tail(5)[["team", "rating", "shrunk_off_epa", "shrunk_def_epa"]].to_dict(orient="records")
    summary = {
        "generated_at": now.isoformat(),
        "timezone": "America/Chicago",
        "current_season": CURRENT_SEASON,
        "through_week": through_week,
        "latest_completed_week": latest_week,
        "preview_week": preview_week,
        "recap_week": recap_week,
        "availability": avail,
        "top5_ratings": top5,
        "bottom5_ratings": bot5,
        "model_params": params.to_dict(),
        "backtest_headline_holdout": {
            "accuracy_ats_free": h["accuracy_ats_free"],
            "locked_rule": h["locked_rule"],
        },
        "qb_adjustment": qb_meta,
        "pending_games_not_recapped": cur_sched[(cur_sched["week"] == recap_week) & cur_sched["home_score"].isna()]["game_id"].tolist(),
        "n_previews": len(projections),
        "n_recaps": int(len(recap_games)),
        "elapsed_sec": round(time.time() - t0, 1),
    }
    write_summary(summary)
    print(f"Done in {summary['elapsed_sec']}s. Outputs in {OUTPUT_DIR}")
    return summary


if __name__ == "__main__":
    summary = main()
    print(json.dumps({
        "top5": summary["top5_ratings"],
        "bottom5": summary["bottom5_ratings"],
        "backtest": summary["backtest_headline_holdout"],
        "preview_week": summary["preview_week"],
        "recap_week": summary["recap_week"],
        "n_previews": summary["n_previews"],
        "n_recaps": summary["n_recaps"],
    }, indent=2, default=str))
