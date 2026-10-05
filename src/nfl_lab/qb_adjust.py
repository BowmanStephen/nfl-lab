"""Starting-QB adjustment.

Idea (transparent): a team's rating reflects the QBs who actually took its snaps.
If this week's projected starter is better/worse than that dropback-weighted mix,
shift the projected margin by  q * (home_delta - away_delta), where
  delta = value(projected starter) - dropback-weighted value(team's QBs in rating window)
  value = shrunk EPA/dropback over seasons S-2, S-1 and current season before week W,
          shrunk toward a data-derived backup baseline (QBs with <150 dropbacks in S-3..S-1).

Causal: values for week W use only dropbacks before week W.
Validation: coefficient q fit and evaluated on 2016-2021 only (leave-one-season-out).
The 2022-2025 holdout is NOT re-graded with this adjustment (it was graded once,
pre-registered, without it).
Starters: historical = schedules home_qb_id/away_qb_id (actual starter, a proxy for
the announced starter); upcoming = schedules' projected starter, cross-checked against
the latest nflverse depth chart QB1 and injury report.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from .data_loader import load_depth_charts, load_injuries, load_pbp, normalize_teams

K_SHRINK = 200          # dropbacks of baseline weight (fixed a priori)
BACKUP_MAX_DB = 150     # QBs under this many dropbacks define the backup baseline
DB_COLS = ["season", "week", "season_type", "posteam", "passer_id", "passer", "qb_dropback", "qb_epa"]


def load_dropbacks(years, pbp: pd.DataFrame | None = None) -> pd.DataFrame:
    """Dropbacks strictly as stored. Pass `pbp` to avoid a second download."""
    years = list(years)
    raw = pbp if pbp is not None else load_pbp(years)
    raw = raw[raw["season"].isin(years)].copy()
    if "passer_id" not in raw.columns and "passer_player_id" in raw.columns:
        raw["passer_id"] = raw["passer_player_id"]
    if "passer" not in raw.columns and "passer_player_name" in raw.columns:
        raw["passer"] = raw["passer_player_name"]
    d = raw[(raw["season_type"] == "REG") & (raw["qb_dropback"] == 1) & raw["passer_id"].notna() & raw["qb_epa"].notna()]
    return normalize_teams(d[DB_COLS].copy())


def backup_baseline(db: pd.DataFrame, season: int) -> float:
    w = db[db["season"].between(season - 3, season - 1)]
    per = w.groupby(["season", "passer_id"])["qb_epa"].agg(["sum", "count"])
    low = per[per["count"] < BACKUP_MAX_DB]
    return float(low["sum"].sum() / low["count"].sum())


def qb_values(db: pd.DataFrame, season: int, week: int, baseline: float) -> pd.Series:
    w = db[db["season"].isin([season - 2, season - 1]) | ((db["season"] == season) & (db["week"] < week))]
    g = w.groupby("passer_id")["qb_epa"].agg(["sum", "count"])
    return (g["sum"] + K_SHRINK * baseline) / (g["count"] + K_SHRINK)


def team_reference(db: pd.DataFrame, season: int, week: int, values: pd.Series, baseline: float) -> pd.Series:
    cur = db[(db["season"] == season) & (db["week"] < week)]
    if len(cur) == 0:  # week 1: rating is prior-driven, so reference = last season's QB mix
        cur = db[db["season"] == season - 1]
    v = cur["passer_id"].map(values).fillna(baseline)
    return v.groupby(cur["posteam"]).mean()  # mean over dropbacks = dropback-weighted


def qb_features(db: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """games needs season, week, home_team, away_team, home_qb_id, away_qb_id."""
    out = []
    for (s, w), g in games.groupby(["season", "week"]):
        base = backup_baseline(db, s)
        vals = qb_values(db, s, w, base)
        ref = team_reference(db, s, w, vals, base)
        g = g.copy()
        g["home_qb_value"] = g["home_qb_id"].map(vals).fillna(base)
        g["away_qb_value"] = g["away_qb_id"].map(vals).fillna(base)
        g["home_qb_ref"] = g["home_team"].map(ref).fillna(base)
        g["away_qb_ref"] = g["away_team"].map(ref).fillna(base)
        g["home_qb_delta"] = g["home_qb_value"] - g["home_qb_ref"]
        g["away_qb_delta"] = g["away_qb_value"] - g["away_qb_ref"]
        g["qb_diff"] = g["home_qb_delta"] - g["away_qb_delta"]
        g["qb_baseline"] = base
        out.append(g)
    return pd.concat(out, ignore_index=True)


def validate_on_tuning(f_tune: pd.DataFrame, db: pd.DataFrame, seasons: list[int]) -> dict:
    """LOSO MAE vs margin with and without the QB term, 2016-2021 only."""
    f = qb_features(db, f_tune)
    def fit(d, use_qb):
        cols = [d["rating_diff"], d["hfa_flag"]] + ([d["qb_diff"]] if use_qb else [])
        return np.linalg.lstsq(np.column_stack(cols), d["margin"].values, rcond=None)[0]
    def pred(d, c, use_qb):
        cols = [d["rating_diff"], d["hfa_flag"]] + ([d["qb_diff"]] if use_qb else [])
        return np.column_stack(cols) @ c
    res = {}
    for use_qb in (False, True):
        errs = []
        for hold in seasons:
            tr, te = f[f["season"] != hold], f[f["season"] == hold]
            errs.append(np.abs(pred(te, fit(tr, use_qb), use_qb) - te["margin"].values))
        res["with_qb" if use_qb else "without_qb"] = float(np.mean(np.concatenate(errs)))
    changed = f[f["qb_diff"].abs() > 0.03]
    errs_c = {}
    for use_qb in (False, True):
        e = []
        for hold in seasons:
            tr, te = f[f["season"] != hold], changed[changed["season"] == hold]
            if len(te):
                e.append(np.abs(pred(te, fit(tr, use_qb), use_qb) - te["margin"].values))
        errs_c["with_qb" if use_qb else "without_qb"] = float(np.mean(np.concatenate(e)))
    c_full = fit(f, True)
    resid = f["margin"].values - pred(f, c_full, True)
    return {
        "fit_seasons": seasons,
        "loso_mae_all_games": res,
        "loso_mae_games_with_|qb_diff|>0.03": {**errs_c, "n_games": int(len(changed))},
        "coefs": {"points_per_net_epa": float(c_full[0]), "hfa": float(c_full[1]),
                  "points_per_qb_epa_db": float(c_full[2]),
                  "margin_sigma": float(np.std(resid, ddof=3))},
        "adopt": res["with_qb"] < res["without_qb"],
    }


# Ruled out for the upcoming week. Questionable players stay on the depth chart.
OUT_STATUSES = {"out", "doubtful", "ir", "injured reserve", "pup", "suspended"}


def _qb_chart(depth: pd.DataFrame) -> tuple[pd.DataFrame, str | None]:
    """Latest chart, one row per QB, best rank first."""
    dc = normalize_teams(depth.copy())
    as_of = None
    if "dt" in dc.columns and dc["dt"].notna().any():
        as_of = str(dc["dt"].max())
        dc = dc[dc["dt"] == dc["dt"].max()]
    if "pos_abb" not in dc.columns:
        raise RuntimeError("depth chart is missing pos_abb; refusing to guess starters")
    qbs = dc[dc["pos_abb"].astype(str).str.upper() == "QB"].copy()
    if "pos_rank" not in qbs.columns:
        raise RuntimeError("depth chart is missing pos_rank")
    qbs["pos_rank"] = pd.to_numeric(qbs["pos_rank"], errors="coerce")
    qbs = qbs.dropna(subset=["gsis_id", "pos_rank", "team"])
    qbs = qbs.sort_values(["team", "pos_rank", "pos_slot"] if "pos_slot" in qbs.columns else ["team", "pos_rank"])
    qbs = qbs.drop_duplicates(["team", "gsis_id"], keep="first")
    return qbs, as_of


def _injury_table(injuries: pd.DataFrame, week: int) -> tuple[pd.DataFrame, int | None]:
    inj = injuries.copy()
    if "week" not in inj.columns or inj.empty:
        return inj.iloc[0:0], None
    use = inj[pd.to_numeric(inj["week"], errors="coerce") <= week]
    if use.empty:
        return use, None
    report_week = int(pd.to_numeric(use["week"], errors="coerce").max())
    use = use[pd.to_numeric(use["week"], errors="coerce") == report_week]
    return use, report_week


def resolve_starter(team: str, schedule_id: str | None, schedule_name: str | None,
                    chart: pd.DataFrame, injuries: pd.DataFrame, report_week: int | None) -> dict:
    """Prefer depth-chart order, skipping QBs ruled out. Flag schedule disagreements."""
    rows = chart[chart["team"] == team].sort_values("pos_rank")
    if rows.empty:
        raise RuntimeError(f"{team}: no QB on the depth chart")
    qb1 = rows.iloc[0]
    notes: list[str] = []
    if schedule_name and qb1["player_name"] != schedule_name:
        notes.append(
            f"{team}: schedule lists {schedule_name}, latest depth chart QB1 is {qb1['player_name']}"
        )
    chosen = None
    for qb in rows.itertuples(index=False):
        hit = injuries[injuries["gsis_id"] == qb.gsis_id] if "gsis_id" in injuries.columns else injuries.iloc[0:0]
        status = None
        injury = None
        if len(hit) and "report_status" in hit.columns and hit["report_status"].notna().any():
            row = hit[hit["report_status"].notna()].iloc[0]
            status = str(row["report_status"])
            injury = row["report_primary_injury"] if "report_primary_injury" in hit.columns else None
        if status and status.strip().lower() in OUT_STATUSES:
            detail = f" ({injury})" if isinstance(injury, str) and injury and injury != "nan" else ""
            notes.append(
                f"{team}: {qb.player_name} listed {status}{detail} on week {report_week} report"
            )
            continue
        chosen = qb
        break
    if chosen is None:
        raise RuntimeError(f"{team}: every depth-chart QB is ruled out")
    if schedule_name and chosen.player_name != schedule_name:
        notes.append(
            f"{team}: using {chosen.player_name} from the depth chart and injury report "
            f"(schedule listed {schedule_name})"
        )
    return {
        "gsis_id": chosen.gsis_id,
        "name": chosen.player_name,
        "schedule_name": schedule_name,
        "schedule_id": schedule_id,
        "depth_qb1": qb1["player_name"],
        "source": "depth_chart+injury",
        "differs_from_schedule": bool(schedule_name) and chosen.player_name != schedule_name,
        "notes": notes,
    }


def upcoming_starters(schedules_slate: pd.DataFrame, season: int, as_of_week: int,
                      depth: pd.DataFrame | None = None, injuries: pd.DataFrame | None = None) -> pd.DataFrame:
    """Replace schedule QB ids with the depth-chart starter who is not ruled out."""
    if depth is None:
        depth = load_depth_charts(season)
    if injuries is None:
        injuries = load_injuries(season)
    if depth is None or len(depth) == 0:
        raise RuntimeError(f"no depth chart for {season}; refusing to snapshot starters")
    if injuries is None or len(injuries) == 0:
        raise RuntimeError(f"no injury report for {season}; refusing to snapshot starters")
    chart, dc_asof = _qb_chart(depth)
    inj, inj_wk = _injury_table(injuries, as_of_week)
    s = schedules_slate.copy()
    if "week" not in s.columns:
        s["week"] = as_of_week
    if "season" not in s.columns:
        s["season"] = season
    notes = {}
    resolved_home = []
    resolved_away = []
    for row in s.itertuples(index=False):
        game_notes: list[str] = []
        for side in ("home", "away"):
            team = getattr(row, f"{side}_team")
            info = resolve_starter(
                team,
                getattr(row, f"{side}_qb_id", None),
                getattr(row, f"{side}_qb_name", None),
                chart,
                inj,
                inj_wk,
            )
            game_notes.extend(info["notes"])
            if side == "home":
                resolved_home.append(info)
            else:
                resolved_away.append(info)
        notes[row.game_id] = game_notes
    s["home_qb_schedule_name"] = s["home_qb_name"] if "home_qb_name" in s.columns else None
    s["away_qb_schedule_name"] = s["away_qb_name"] if "away_qb_name" in s.columns else None
    s["home_qb_id"] = [r["gsis_id"] for r in resolved_home]
    s["away_qb_id"] = [r["gsis_id"] for r in resolved_away]
    s["home_qb_name"] = [r["name"] for r in resolved_home]
    s["away_qb_name"] = [r["name"] for r in resolved_away]
    s["home_qb_source"] = [r["source"] for r in resolved_home]
    s["away_qb_source"] = [r["source"] for r in resolved_away]
    s["home_qb_differs"] = [r["differs_from_schedule"] for r in resolved_home]
    s["away_qb_differs"] = [r["differs_from_schedule"] for r in resolved_away]
    s["qb_notes"] = s["game_id"].map(notes)
    s.attrs["depth_chart_as_of"] = dc_asof
    s.attrs["injury_report_week"] = inj_wk
    return s


def apply_to_slate(proj: pd.DataFrame, slate_sched: pd.DataFrame, db: pd.DataFrame,
                   season: int, week: int, coefs: dict,
                   depth: pd.DataFrame | None = None, injuries: pd.DataFrame | None = None) -> pd.DataFrame:
    s = upcoming_starters(slate_sched, season, week, depth=depth, injuries=injuries)
    s = s.assign(week=week)
    qf = qb_features(db, s[["game_id", "season", "week", "home_team", "away_team", "home_qb_id", "away_qb_id"]])
    keep = ["game_id", "home_qb_value", "away_qb_value", "home_qb_ref", "away_qb_ref",
            "home_qb_delta", "away_qb_delta", "qb_diff"]
    extra = ["game_id", "home_qb_name", "away_qb_name", "home_qb_schedule_name", "away_qb_schedule_name",
             "home_qb_source", "away_qb_source", "home_qb_differs", "away_qb_differs", "qb_notes"]
    p = proj.merge(qf[keep], on="game_id", how="left").merge(s[extra], on="game_id", how="left")
    p["qb_adj_points"] = coefs["points_per_qb_epa_db"] * p["qb_diff"]
    p["proj_margin_qb"] = p["proj_margin"] + p["qb_adj_points"]
    p["proj_spread_qb"] = -p["proj_margin_qb"]
    p["home_win_prob_qb"] = norm.cdf(p["proj_margin_qb"] / coefs["margin_sigma"])
    p.attrs.update(s.attrs)
    return p
