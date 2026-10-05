"""Team and QB advanced stats from play-by-play."""
from __future__ import annotations

import pandas as pd

from .config import (
    EARLY_DOWNS,
    EXPLOSIVE_PASS_YARDS,
    EXPLOSIVE_RUSH_YARDS,
)
from .data_loader import filter_offensive_plays


def _is_pass(df: pd.DataFrame) -> pd.Series:
    if "pass" in df.columns:
        return df["pass"] == 1
    return df["play_type"] == "pass"


def _is_rush(df: pd.DataFrame) -> pd.Series:
    if "rush" in df.columns:
        return df["rush"] == 1
    return df["play_type"] == "run"


def _explosive(df: pd.DataFrame) -> pd.Series:
    yds = df["yards_gained"].fillna(0)
    is_pass = _is_pass(df)
    is_rush = _is_rush(df)
    return (is_pass & (yds >= EXPLOSIVE_PASS_YARDS)) | (is_rush & (yds >= EXPLOSIVE_RUSH_YARDS))


def compute_team_offense(plays: pd.DataFrame) -> pd.DataFrame:
    """Per-team offensive EPA splits and rates."""
    df = plays.copy()
    df["is_pass"] = _is_pass(df)
    df["is_rush"] = _is_rush(df)
    df["is_early"] = df["down"].isin(EARLY_DOWNS)
    df["is_explosive"] = _explosive(df)

    rows = []
    for team, g in df.groupby("posteam"):
        pass_g = g[g["is_pass"]]
        rush_g = g[g["is_rush"]]
        early = g[g["is_early"]]
        row = {
            "team": team,
            "off_plays": int(len(g)),
            "off_epa": float(g["epa"].mean()),
            "off_success": float(g["success"].mean()) if "success" in g else None,
            "off_pass_epa": float(pass_g["epa"].mean()) if len(pass_g) else None,
            "off_rush_epa": float(rush_g["epa"].mean()) if len(rush_g) else None,
            "off_pass_success": float(pass_g["success"].mean()) if len(pass_g) and "success" in pass_g else None,
            "off_rush_success": float(rush_g["success"].mean()) if len(rush_g) and "success" in rush_g else None,
            "off_early_epa": float(early["epa"].mean()) if len(early) else None,
            "off_early_success": float(early["success"].mean()) if len(early) and "success" in early else None,
            "off_explosive_rate": float(g["is_explosive"].mean()),
            "off_pass_rate": float(g["is_pass"].mean()),
        }
        if "pass_oe" in g.columns and g["pass_oe"].notna().any():
            row["off_proe"] = float(g["pass_oe"].dropna().mean())
        else:
            row["off_proe"] = None
        rows.append(row)
    return pd.DataFrame(rows).sort_values("team").reset_index(drop=True)


def compute_team_defense(plays: pd.DataFrame) -> pd.DataFrame:
    """Per-team defensive EPA allowed (lower is better)."""
    df = plays.copy()
    df["is_pass"] = _is_pass(df)
    df["is_rush"] = _is_rush(df)
    df["is_early"] = df["down"].isin(EARLY_DOWNS)
    df["is_explosive"] = _explosive(df)

    rows = []
    for team, g in df.groupby("defteam"):
        pass_g = g[g["is_pass"]]
        rush_g = g[g["is_rush"]]
        early = g[g["is_early"]]
        rows.append({
            "team": team,
            "def_plays": int(len(g)),
            "def_epa": float(g["epa"].mean()),
            "def_success": float(g["success"].mean()) if "success" in g else None,
            "def_pass_epa": float(pass_g["epa"].mean()) if len(pass_g) else None,
            "def_rush_epa": float(rush_g["epa"].mean()) if len(rush_g) else None,
            "def_early_epa": float(early["epa"].mean()) if len(early) else None,
            "def_explosive_rate": float(g["is_explosive"].mean()),
        })
    return pd.DataFrame(rows).sort_values("team").reset_index(drop=True)


def compute_qb_stats(plays: pd.DataFrame, min_attempts: int = 50) -> pd.DataFrame:
    """QB EPA and CPOE; composite = EPA/play + 0.01 * CPOE (common public scale)."""
    df = plays.copy()
    # Attempt-like throws with CPOE / passer
    passer_col = "passer_player_name" if "passer_player_name" in df.columns else "passer"
    id_col = "passer_id" if "passer_id" in df.columns else "passer_player_id"
    mask = _is_pass(df) & df[passer_col].notna()
    q = df.loc[mask].copy()
    if id_col not in q.columns:
        q["_qb_key"] = q[passer_col]
    else:
        q["_qb_key"] = q[id_col].fillna(q[passer_col])

    rows = []
    for key, g in q.groupby("_qb_key"):
        name = g[passer_col].mode().iloc[0] if len(g[passer_col].mode()) else str(key)
        team = g["posteam"].mode().iloc[0] if len(g["posteam"].mode()) else None
        n = len(g)
        if n < min_attempts:
            continue
        epa_col = "qb_epa" if "qb_epa" in g.columns and g["qb_epa"].notna().any() else "epa"
        epa = float(g[epa_col].mean())
        cpoe = float(g["cpoe"].dropna().mean()) if "cpoe" in g.columns and g["cpoe"].notna().any() else None
        composite = epa + 0.01 * cpoe if cpoe is not None else epa
        rows.append({
            "passer_id": str(key),
            "passer": name,
            "team": team,
            "dropbacks": int(n),
            "qb_epa": epa,
            "cpoe": cpoe,
            "epa_cpoe": float(composite),
            "success": float(g["success"].mean()) if "success" in g else None,
        })
    out = pd.DataFrame(rows)
    if len(out):
        out = out.sort_values("epa_cpoe", ascending=False).reset_index(drop=True)
    return out


def compute_season_team_stats(pbp: pd.DataFrame, season: int, through_week: int | None = None) -> pd.DataFrame:
    """Full team offense+defense table for a season (optionally through a week)."""
    season_pbp = pbp[pbp["season"] == season].copy()
    if through_week is not None:
        season_pbp = season_pbp[season_pbp["week"] <= through_week]
    # Regular season only when available
    if "season_type" in season_pbp.columns:
        season_pbp = season_pbp[season_pbp["season_type"] == "REG"]
    plays = filter_offensive_plays(season_pbp)
    off = compute_team_offense(plays)
    deff = compute_team_defense(plays)
    merged = off.merge(deff, on="team", how="outer")
    merged["season"] = season
    merged["through_week"] = through_week
    merged["net_epa"] = merged["off_epa"] - merged["def_epa"]
    return merged


def compute_all_team_stats(
    pbp: pd.DataFrame,
    seasons: list[int],
    through_week_by_season: dict[int, int] | None = None,
) -> pd.DataFrame:
    frames = []
    for s in seasons:
        tw = None if through_week_by_season is None else through_week_by_season.get(s)
        frames.append(compute_season_team_stats(pbp, s, through_week=tw))
    return pd.concat(frames, ignore_index=True)
