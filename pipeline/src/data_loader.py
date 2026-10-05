"""Load schedules and play-by-play from nflverse / habitatring."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from .config import CURRENT_SEASON, DATA_DIR, PBP_URL, SCHEDULES_URL


# Relocated franchises -> current abbreviation so priors carry across seasons
TEAM_FIX = {"STL": "LA", "SD": "LAC", "OAK": "LV", "LAR": "LA"}
TEAM_COLS = ["posteam", "defteam", "home_team", "away_team"]

# Columns needed for ratings/backtests (keeps memory low for history years)
CORE_PBP_COLS = [
    "game_id", "season", "week", "season_type", "posteam", "defteam",
    "home_team", "away_team", "epa", "success", "pass", "rush", "play_type",
    "qb_kneel", "qb_spike", "down", "yards_gained",
]


def normalize_teams(df: pd.DataFrame) -> pd.DataFrame:
    for c in TEAM_COLS:
        if c in df.columns:
            df[c] = df[c].replace(TEAM_FIX)
    return df


def _cache_path(name: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / name


def load_schedules(seasons: Iterable[int] | None = None, force: bool = False) -> pd.DataFrame:
    """Load NFL schedules (Lee Sharpe / habitatring games.csv)."""
    cache = _cache_path("schedules.csv")
    if force or not cache.exists():
        df = pd.read_csv(SCHEDULES_URL)
        df.to_csv(cache, index=False)
    else:
        df = pd.read_csv(cache)
    if seasons is not None:
        seasons = list(seasons)
        df = df[df["season"].isin(seasons)].copy()
    return normalize_teams(df.reset_index(drop=True))


def load_pbp(
    years: Iterable[int],
    force: bool = False,
    columns: list[str] | None = None,
    force_years: Iterable[int] = (),
) -> pd.DataFrame:
    """Load play-by-play parquet files from nflverse releases (cached in data/).

    force=True re-downloads all years; force_years re-downloads only those
    (use for the in-progress season so new weeks are picked up).
    """
    force_years = set(force_years)
    frames: list[pd.DataFrame] = []
    for year in years:
        cache = _cache_path(f"pbp_{year}.parquet")
        if force or year in force_years or not cache.exists():
            url = PBP_URL.format(year=year)
            full = pd.read_parquet(url)
            full.to_parquet(cache, index=False)
            df = full[[c for c in columns if c in full.columns]] if columns else full
            del full
        else:
            df = pd.read_parquet(cache, columns=columns) if columns else pd.read_parquet(cache)
        frames.append(normalize_teams(df.copy()))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def filter_offensive_plays(pbp: pd.DataFrame) -> pd.DataFrame:
    """Keep designed pass/run plays with EPA (exclude special teams / kneels / spikes)."""
    df = pbp.copy()
    # nflverse flags
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
    out = df.loc[mask].copy()
    return out


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
            "completed_weeks": sorted(completed["week"].unique().tolist()),
            "upcoming_weeks": sorted(upcoming["week"].unique().tolist()),
            "pbp_weeks": [int(w) for w in pbp_weeks],
            "pbp_plays": int(len(pbp_season)),
            "last_completed_gameday": str(completed["gameday"].max()) if len(completed) else None,
        }
    # Infer current slate
    cur = schedules[schedules["season"] == CURRENT_SEASON]
    completed = cur[cur["home_score"].notna()]
    upcoming = cur[cur["home_score"].isna()]
    latest_completed_week = int(completed["week"].max()) if len(completed) else None
    # Upcoming week: earliest week with unscored games
    next_week = int(upcoming["week"].min()) if len(upcoming) else None
    report["latest_completed_week"] = latest_completed_week
    report["upcoming_week"] = next_week
    report["remaining_this_week"] = (
        upcoming[upcoming["week"] == latest_completed_week][
            ["game_id", "week", "gameday", "away_team", "home_team"]
        ].to_dict(orient="records")
        if latest_completed_week is not None and len(upcoming)
        else []
    )
    return report
