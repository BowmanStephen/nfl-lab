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

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .config import DATA_DIR, OUTPUT_DIR
from .data_loader import normalize_teams

K_SHRINK = 200          # dropbacks of baseline weight (fixed a priori)
BACKUP_MAX_DB = 150     # QBs under this many dropbacks define the backup baseline
DB_COLS = ["season", "week", "season_type", "posteam", "passer_id", "passer", "qb_dropback", "qb_epa"]


def load_dropbacks(years) -> pd.DataFrame:
    frames = []
    for y in years:
        d = pd.read_parquet(DATA_DIR / f"pbp_{y}.parquet", columns=DB_COLS)
        d = d[(d["season_type"] == "REG") & (d["qb_dropback"] == 1) & d["passer_id"].notna() & d["qb_epa"].notna()]
        frames.append(normalize_teams(d.copy()))
    return pd.concat(frames, ignore_index=True)


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


def upcoming_starters(schedules_slate: pd.DataFrame, season: int, as_of_week: int) -> pd.DataFrame:
    """Projected starters from schedules, cross-checked with depth chart + injuries."""
    s = schedules_slate.copy()
    notes = {gid: [] for gid in s["game_id"]}
    try:
        dc = pd.read_parquet(DATA_DIR / f"depth_{season}.parquet")
        dc = normalize_teams(dc.rename(columns={"team": "posteam"})).rename(columns={"posteam": "team"})
        latest = dc[dc["dt"] == dc["dt"].max()]
        qb1 = latest[(latest["pos_abb"] == "QB") & (latest["pos_rank"] == 1)].drop_duplicates("team").set_index("team")
        dc_asof = str(dc["dt"].max())
    except Exception:
        qb1, dc_asof = pd.DataFrame(), None
    try:
        inj = pd.read_parquet(DATA_DIR / f"inj_{season}.parquet")
        inj = inj[inj["week"] == inj["week"].max()]
        inj_wk = int(inj["week"].max()) if len(inj) else None
    except Exception:
        inj, inj_wk = pd.DataFrame(), None
    for row in s.itertuples(index=False):
        for side in ("home", "away"):
            team, qid, qname = getattr(row, f"{side}_team"), getattr(row, f"{side}_qb_id"), getattr(row, f"{side}_qb_name")
            if len(qb1) and team in qb1.index and qb1.loc[team, "gsis_id"] != qid:
                notes[row.game_id].append(f"{team}: schedule lists {qname}, latest depth chart QB1 is {qb1.loc[team, 'player_name']}")
            if len(inj):
                hit = inj[(inj["gsis_id"] == qid) & inj["report_status"].notna()]
                for h in hit.itertuples(index=False):
                    notes[row.game_id].append(f"{team}: {qname} listed {h.report_status} ({h.report_primary_injury}) on week {inj_wk} report")
    s["qb_notes"] = s["game_id"].map(notes)
    s.attrs["depth_chart_as_of"] = dc_asof
    s.attrs["injury_report_week"] = inj_wk
    return s


def apply_to_slate(proj: pd.DataFrame, slate_sched: pd.DataFrame, db: pd.DataFrame,
                   season: int, week: int, coefs: dict) -> pd.DataFrame:
    s = upcoming_starters(slate_sched, season, week)
    s = s.assign(week=week)  # all slate games valued as of the preview week (data before it)
    qf = qb_features(db, s[["game_id", "season", "week", "home_team", "away_team", "home_qb_id", "away_qb_id"]])
    keep = ["game_id", "home_qb_value", "away_qb_value", "home_qb_ref", "away_qb_ref",
            "home_qb_delta", "away_qb_delta", "qb_diff"]
    p = proj.merge(qf[keep], on="game_id", how="left").merge(
        s[["game_id", "home_qb_name", "away_qb_name", "qb_notes"]], on="game_id", how="left")
    p["qb_adj_points"] = coefs["points_per_qb_epa_db"] * p["qb_diff"]
    p["proj_margin_qb"] = p["proj_margin"] + p["qb_adj_points"]
    p["proj_spread_qb"] = -p["proj_margin_qb"]
    from scipy.stats import norm
    p["home_win_prob_qb"] = norm.cdf(p["proj_margin_qb"] / coefs["margin_sigma"])
    p.attrs.update(s.attrs)
    return p
