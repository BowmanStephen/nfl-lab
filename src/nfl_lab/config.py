"""Shared configuration for NFL Lab."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
PREVIEWS_DIR = OUTPUT_DIR / "previews"
RECAPS_DIR = OUTPUT_DIR / "recaps"
LIVE_DIR = OUTPUT_DIR / "live"
PUBLIC_DIR = ROOT / "public"
PUBLIC_API = PUBLIC_DIR / "api"

# Live proof starts with the 2026 week 5 slate (first kickoff Thu Oct 8, 2026).
LIVE_SEASON = 2026
LIVE_START_WEEK = 5
# Same-book pre-kickoff window. An hourly job can land a DraftKings snapshot inside it.
PRE_KICKOFF_MINUTES = 120

# Current season and priors
CURRENT_SEASON = 2026
PRIOR_SEASONS = [2023, 2024, 2025]  # weighted 1:2:3 (most recent heaviest)
HISTORY_SEASONS = [2020, 2021, 2022]  # loaded only so 2023 backtest has priors
BACKTEST_SEASONS = [2023, 2024, 2025]

# Shrinkage: prior weight as equivalent sample of plays
PRIOR_PLAYS_EQUIV = 350  # prior worth ~350 plays (~5-6 games) of current data
PRIOR_REGRESS = 0.6     # fraction of prior rating retained (regression to mean)

# Explosive play thresholds (nflverse-style)
EXPLOSIVE_PASS_YARDS = 20
EXPLOSIVE_RUSH_YARDS = 15

# Early downs
EARLY_DOWNS = (1, 2)

# Home field advantage prior (points); refined in model fit
HFA_PRIOR = 2.2

# Schedules source (Lee Sharpe / habitatring, same as nfl_data_py)
SCHEDULES_URL = "http://www.habitatring.com/games.csv"
PBP_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "pbp/play_by_play_{year}.parquet"
)

TEAM_NAMES = {
    "ARI": "Arizona Cardinals",
    "ATL": "Atlanta Falcons",
    "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers",
    "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals",
    "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos",
    "DET": "Detroit Lions",
    "GB": "Green Bay Packers",
    "HOU": "Houston Texans",
    "IND": "Indianapolis Colts",
    "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs",
    "LA": "Los Angeles Rams",
    "LAC": "Los Angeles Chargers",
    "LV": "Las Vegas Raiders",
    "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings",
    "NE": "New England Patriots",
    "NO": "New Orleans Saints",
    "NYG": "New York Giants",
    "NYJ": "New York Jets",
    "PHI": "Philadelphia Eagles",
    "PIT": "Pittsburgh Steelers",
    "SEA": "Seattle Seahawks",
    "SF": "San Francisco 49ers",
    "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans",
    "WAS": "Washington Commanders",
}
