"""Transparent game model: ratings -> spread, total, win probability."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm

from .config import HFA_PRIOR
from .data_loader import filter_offensive_plays
from .ratings import build_current_ratings, opponent_adjust


@dataclass
class ModelParams:
    """Fitted mapping from rating differential to points."""
    points_per_net_epa: float  # margin ≈ ppne * (home_rating - away_rating) + hfa
    hfa: float
    margin_sigma: float
    base_total: float
    points_per_combined_off: float  # total boost from both offenses / defenses

    def to_dict(self) -> dict:
        return asdict(self)


def _game_features(
    schedules: pd.DataFrame,
    ratings: pd.DataFrame,
) -> pd.DataFrame:
    """Join ratings onto completed (or upcoming) games."""
    r = ratings.set_index("team")
    games = schedules.copy()
    games["home_rating"] = games["home_team"].map(r["rating"])
    games["away_rating"] = games["away_team"].map(r["rating"])
    games["home_off"] = games["home_team"].map(r["shrunk_off_epa"])
    games["away_off"] = games["away_team"].map(r["shrunk_off_epa"])
    games["home_def"] = games["home_team"].map(r["shrunk_def_epa"])
    games["away_def"] = games["away_team"].map(r["shrunk_def_epa"])
    games["rating_diff"] = games["home_rating"] - games["away_rating"]
    # Scoring environment for totals. Defense ratings are EPA *allowed* per play
    # (higher = leakier), so a weak defense ADDS points and a stingy one subtracts.
    # Before Oct 2026 this subtracted the defense terms, which counted a stingy
    # defense as adding points. See CHANGES.md.
    games["off_env"] = (
        games["home_off"].fillna(0)
        + games["away_off"].fillna(0)
        + games["home_def"].fillna(0)
        + games["away_def"].fillna(0)
    )
    if "result" in games.columns:
        # result = home_score - away_score in habitatring
        games["margin"] = games["result"]
    elif "home_score" in games.columns:
        games["margin"] = games["home_score"] - games["away_score"]
    if "home_score" in games.columns and "away_score" in games.columns:
        games["total_points"] = games["home_score"] + games["away_score"]
    return games


def fit_model_params(
    pbp: pd.DataFrame,
    schedules: pd.DataFrame,
    fit_seasons: list[int],
    prior_seasons_template: list[int] | None = None,
    min_week: int = 4,
) -> ModelParams:
    """
    Fit points-per-net-EPA, HFA, and margin sigma on historical seasons.

    For each season S and week W (>= min_week), build ratings using weeks 1..W-1
    of S plus priors, then predict week W games. Pool all such predictions.
    """
    rows_margin = []
    rows_total = []
    for season in fit_seasons:
        sched_s = schedules[
            (schedules["season"] == season)
            & (schedules["game_type"] == "REG")
            if "game_type" in schedules.columns
            else (schedules["season"] == season)
        ]
        # priors: seasons before this one from available pbp
        available = sorted(pbp["season"].unique())
        priors = [y for y in available if y < season][-3:]
        max_week = int(sched_s["week"].max()) if len(sched_s) else 18
        for week in range(min_week, min(max_week, 18) + 1):
            ratings = build_current_ratings(
                pbp, season=season, through_week=week - 1, prior_seasons=priors
            )
            week_games = sched_s[
                (sched_s["week"] == week) & sched_s["home_score"].notna()
            ].copy()
            if len(week_games) == 0:
                continue
            feat = _game_features(week_games, ratings).dropna(subset=["rating_diff", "margin"])
            for row in feat.itertuples(index=False):
                rows_margin.append({
                    "rating_diff": row.rating_diff,
                    "margin": row.margin,
                    "off_env": row.off_env,
                    "total_points": getattr(row, "total_points", np.nan),
                })
                if pd.notna(getattr(row, "total_points", np.nan)):
                    rows_total.append({
                        "off_env": row.off_env,
                        "total_points": row.total_points,
                    })

    if not rows_margin:
        # Fallback priors if fit fails
        return ModelParams(
            points_per_net_epa=55.0,
            hfa=HFA_PRIOR,
            margin_sigma=13.5,
            base_total=45.0,
            points_per_combined_off=25.0,
        )

    mdf = pd.DataFrame(rows_margin)
    # OLS: margin ~ rating_diff + intercept(HFA)
    X = np.column_stack([mdf["rating_diff"].values, np.ones(len(mdf))])
    y = mdf["margin"].values
    coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    ppne, hfa = float(coef[0]), float(coef[1])
    resid = y - X @ coef
    sigma = float(np.std(resid, ddof=1)) if len(resid) > 1 else 13.5

    if rows_total:
        tdf = pd.DataFrame(rows_total)
        Xt = np.column_stack([tdf["off_env"].values, np.ones(len(tdf))])
        yt = tdf["total_points"].values
        tcoef, _, _, _ = np.linalg.lstsq(Xt, yt, rcond=None)
        pp_off, base_total = float(tcoef[0]), float(tcoef[1])
    else:
        pp_off, base_total = 25.0, float(mdf["total_points"].mean()) if "total_points" in mdf else 45.0

    return ModelParams(
        points_per_net_epa=ppne,
        hfa=hfa,
        margin_sigma=max(sigma, 8.0),
        base_total=base_total,
        points_per_combined_off=pp_off,
    )


def project_games(
    schedules_week: pd.DataFrame,
    ratings: pd.DataFrame,
    params: ModelParams,
) -> pd.DataFrame:
    """Project spread (home perspective), total, and home win probability."""
    feat = _game_features(schedules_week, ratings)
    hfa_flag = (feat["location"] != "Neutral").astype(float) if "location" in feat.columns else 1.0
    feat["proj_margin"] = (
        params.points_per_net_epa * feat["rating_diff"].fillna(0) + params.hfa * hfa_flag
    )
    feat["proj_total"] = (
        params.base_total
        + params.points_per_combined_off * feat["off_env"].fillna(0)
    )
    # Market-style spread: negative means home favored
    feat["proj_spread"] = -feat["proj_margin"]
    feat["home_win_prob"] = 1.0 - norm.cdf(
        0.0, loc=feat["proj_margin"], scale=params.margin_sigma
    )
    feat["away_win_prob"] = 1.0 - feat["home_win_prob"]
    # Pick
    feat["model_favorite"] = np.where(
        feat["proj_margin"] >= 0, feat["home_team"], feat["away_team"]
    )
    cols = [
        "game_id", "season", "week", "gameday", "gametime",
        "away_team", "home_team", "location",
        "away_rating", "home_rating", "rating_diff",
        "proj_margin", "proj_spread", "proj_total",
        "home_win_prob", "away_win_prob", "model_favorite",
        "spread_line", "total_line", "home_moneyline", "away_moneyline",
        "home_score", "away_score", "result",
    ]
    keep = [c for c in cols if c in feat.columns]
    return feat[keep].sort_values(["gameday", "gametime", "game_id"]).reset_index(drop=True)


def quick_fit_from_full_seasons(
    pbp: pd.DataFrame,
    schedules: pd.DataFrame,
    seasons: list[int],
) -> ModelParams:
    """
    Faster fit: use full prior-year ratings to predict each season's games.
    Used as a robust backup / initialization; primary fit is week-by-week.
    """
    rows = []
    for season in seasons:
        available = sorted(pbp["season"].unique())
        priors = [y for y in available if y < season][-3:]
        if not priors:
            continue
        # Use prior seasons only (as-of week 0)
        from .ratings import build_prior_ratings, shrink_to_prior
        prior = build_prior_ratings(pbp, priors)
        # Fake current with zeros / tiny plays so shrink ≈ prior
        current = prior.rename(columns={
            "adj_off_epa": "adj_off_epa",
            "adj_def_epa": "adj_def_epa",
        }).copy()
        current["off_plays"] = 0
        current["def_plays"] = 0
        ratings = shrink_to_prior(current, prior, prior_plays_equiv=1)
        # Actually just use prior net as rating
        ratings = prior.copy()
        ratings["shrunk_off_epa"] = ratings["adj_off_epa"]
        ratings["shrunk_def_epa"] = ratings["adj_def_epa"]
        ratings["rating"] = ratings["adj_net_epa"]
        sched_s = schedules[(schedules["season"] == season) & schedules["home_score"].notna()]
        if "game_type" in sched_s.columns:
            sched_s = sched_s[sched_s["game_type"] == "REG"]
        feat = _game_features(sched_s, ratings).dropna(subset=["rating_diff", "margin"])
        rows.append(feat)
    if not rows:
        return ModelParams(55.0, HFA_PRIOR, 13.5, 45.0, 25.0)
    mdf = pd.concat(rows, ignore_index=True)
    X = np.column_stack([mdf["rating_diff"].values, np.ones(len(mdf))])
    y = mdf["margin"].values
    coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    Xt = np.column_stack([mdf["off_env"].fillna(0).values, np.ones(len(mdf))])
    yt = mdf["total_points"].values
    tcoef, _, _, _ = np.linalg.lstsq(Xt, yt, rcond=None)
    return ModelParams(
        points_per_net_epa=float(coef[0]),
        hfa=float(coef[1]),
        margin_sigma=float(max(np.std(resid, ddof=1), 8.0)),
        base_total=float(tcoef[1]),
        points_per_combined_off=float(tcoef[0]),
    )
