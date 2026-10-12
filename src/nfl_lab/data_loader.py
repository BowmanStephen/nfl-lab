"""Load schedules, play-by-play, depth charts, and injuries via nflreadpy.

nflreadpy is the current nflverse Python loader (nfl_data_py is deprecated).
Frames are converted to pandas at this boundary so the frozen rating code stays put.
Raw downloads are cached under data/ and are not committed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import nflreadpy as nfl
import pandas as pd

from .config import CURRENT_SEASON, DATA_DIR


# Relocated franchises -> current abbreviation so priors carry across seasons
TEAM_FIX = {"STL": "LA", "SD": "LAC", "OAK": "LV", "LAR": "LA", "WSH": "WAS"}
TEAM_COLS = ["posteam", "defteam", "home_team", "away_team", "team"]

# Columns the rating model, QB adjustment, and team pages actually read.
PBP_COLS = [
    "game_id", "season", "week", "season_type", "posteam", "defteam",
    "home_team", "away_team", "epa", "success", "pass", "rush", "play_type",
    "qb_kneel", "qb_spike", "down", "yards_gained", "pass_oe", "cpoe",
    "passer_id", "passer", "passer_player_id", "passer_player_name",
    "qb_dropback", "qb_epa",
]


def normalize_teams(df: pd.DataFrame) -> pd.DataFrame:
    for c in TEAM_COLS:
        if c in df.columns:
            df[c] = df[c].replace(TEAM_FIX)
    return df


def _cache_path(name: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / name


def _to_pandas(frame) -> pd.DataFrame:
    if isinstance(frame, pd.DataFrame):
        return frame
    return frame.to_pandas()


def load_schedules(seasons: Iterable[int] | None = None, force: bool = False) -> pd.DataFrame:
    """NFL schedules from nflverse (spread_line is home margin: positive means home favored)."""
    seasons_list = list(seasons) if seasons is not None else None
    cache = _cache_path("schedules.parquet")
    if force or not cache.exists():
        df = _to_pandas(nfl.load_schedules(seasons_list if seasons_list is not None else True))
        df.to_parquet(cache, index=False)
    else:
        df = pd.read_parquet(cache)
        if seasons_list is not None:
            have = set(int(s) for s in df["season"].unique())
            missing = [s for s in seasons_list if s not in have]
            if missing:
                extra = _to_pandas(nfl.load_schedules(missing))
                df = pd.concat([df, extra], ignore_index=True)
                df.to_parquet(cache, index=False)
    if seasons_list is not None:
        df = df[df["season"].isin(seasons_list)].copy()
    return normalize_teams(df.reset_index(drop=True))


def load_pbp(
    years: Iterable[int],
    force: bool = False,
    columns: list[str] | None = None,
    force_years: Iterable[int] = (),
) -> pd.DataFrame:
    """Play-by-play for the given seasons. `columns` limits the in-memory frame, not the cache."""
    force_years = set(force_years)
    frames: list[pd.DataFrame] = []
    for year in years:
        cache = _cache_path(f"pbp_{year}.parquet")
        if force or year in force_years or not cache.exists():
            full = _to_pandas(nfl.load_pbp([int(year)]))
            keep = [c for c in PBP_COLS if c in full.columns]
            full = full[keep]
            full.to_parquet(cache, index=False)
            df = full
        else:
            df = pd.read_parquet(cache)
        if columns:
            df = df[[c for c in columns if c in df.columns]]
        frames.append(normalize_teams(df.copy()))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_depth_charts(season: int, force: bool = False) -> pd.DataFrame:
    cache = _cache_path(f"depth_{season}.parquet")
    if force or not cache.exists():
        df = _to_pandas(nfl.load_depth_charts([int(season)]))
        df.to_parquet(cache, index=False)
    else:
        df = pd.read_parquet(cache)
    return normalize_teams(df)


def load_injuries(season: int, force: bool = False) -> pd.DataFrame:
    cache = _cache_path(f"inj_{season}.parquet")
    if force or not cache.exists():
        df = _to_pandas(nfl.load_injuries([int(season)]))
        df.to_parquet(cache, index=False)
    else:
        df = pd.read_parquet(cache)
    return normalize_teams(df)


def filter_offensive_plays(pbp: pd.DataFrame) -> pd.DataFrame:
    """Keep designed pass/run plays with EPA (exclude special teams / kneels / spikes)."""
    df = pbp.copy()
    if "pass" in df.columns and "rush" in df.columns:
        mask = (df["pass"] == 1) | (df["rush"] == 1)
    else:
        mask = df["play_type"].isin(["pass", "run"])
    if "qb_kneel" in df.columns:
        mask &= df["qb_kneel"] != 1
    if "qb_spike" in df.columns:
        mask &= df["qb_spike"] != 1
    if "epa" in df.columns:
        mask &= df["epa"].notna()
    if "posteam" in df.columns:
        mask &= df["posteam"].notna()
    return df.loc[mask].copy()


def data_availability_report(schedules: pd.DataFrame, pbp: pd.DataFrame) -> dict:
    """Summarize what seasons/weeks exist and which games are complete."""
    report: dict = {"current_season": CURRENT_SEASON, "seasons": {}}
    for season, grp in schedules.groupby("season"):
        completed = grp[grp["home_score"].notna()]
        upcoming = grp[grp["home_score"].isna()]
        pbp_season = pbp[pbp["season"] == season] if "season" in pbp.columns and len(pbp) else pd.DataFrame()
        pbp_weeks = sorted(pbp_season["week"].dropna().unique().tolist()) if len(pbp_season) else []
        report["seasons"][int(season)] = {
            "schedule_games": int(len(grp)),
            "completed_games": int(len(completed)),
            "upcoming_games": int(len(upcoming)),
            "completed_weeks": sorted(int(w) for w in completed["week"].unique().tolist()),
            "upcoming_weeks": sorted(int(w) for w in upcoming["week"].unique().tolist()),
            "pbp_weeks": [int(w) for w in pbp_weeks],
            "pbp_plays": int(len(pbp_season)),
            "last_completed_gameday": str(completed["gameday"].max()) if len(completed) else None,
        }
    cur = schedules[schedules["season"] == CURRENT_SEASON]
    completed = cur[cur["home_score"].notna()]
    upcoming = cur[cur["home_score"].isna()]
    latest_completed_week = int(completed["week"].max()) if len(completed) else None
    next_week = int(upcoming["week"].min()) if len(upcoming) else None
    report["latest_completed_week"] = latest_completed_week
    report["upcoming_week"] = next_week
    return report
