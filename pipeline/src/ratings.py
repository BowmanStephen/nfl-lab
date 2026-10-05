"""Opponent-adjusted team ratings with prior-season shrinkage."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import PRIOR_PLAYS_EQUIV, PRIOR_REGRESS
from .data_loader import filter_offensive_plays


def _team_raw_from_plays(plays: pd.DataFrame) -> pd.DataFrame:
    """Raw off/def EPA and play counts."""
    off = (
        plays.groupby("posteam")
        .agg(off_epa=("epa", "mean"), off_plays=("epa", "count"), off_success=("success", "mean"))
        .reset_index()
        .rename(columns={"posteam": "team"})
    )
    deff = (
        plays.groupby("defteam")
        .agg(def_epa=("epa", "mean"), def_plays=("epa", "count"), def_success=("success", "mean"))
        .reset_index()
        .rename(columns={"defteam": "team"})
    )
    return off.merge(deff, on="team", how="outer")


def opponent_adjust(plays: pd.DataFrame, n_iter: int = 6) -> pd.DataFrame:
    """
    Iterative opponent-adjusted offense/defense EPA (vectorized).

    Each iteration:
      adj_off[team] = mean over its plays of (epa - adj_def[opponent])
      adj_def[team] = mean over its plays of (epa - adj_off[opponent])
    Both centered to league average 0 each pass. Lower adj_def = better defense.
    """
    df = plays[["posteam", "defteam", "epa"]].dropna().copy()
    teams = sorted(set(df["posteam"]).union(set(df["defteam"])))
    adj_off = pd.Series(0.0, index=teams)
    adj_def = pd.Series(0.0, index=teams)
    for _ in range(n_iter):
        new_off = (df["epa"] - df["defteam"].map(adj_def)).groupby(df["posteam"]).mean()
        new_def = (df["epa"] - df["posteam"].map(adj_off)).groupby(df["defteam"]).mean()
        adj_off = (new_off - new_off.mean()).reindex(teams).fillna(0.0)
        adj_def = (new_def - new_def.mean()).reindex(teams).fillna(0.0)

    raw = _team_raw_from_plays(plays).set_index("team")
    out = pd.DataFrame({
        "team": teams,
        "off_epa_raw": raw["off_epa"].reindex(teams).values,
        "def_epa_raw": raw["def_epa"].reindex(teams).values,
        "off_plays": raw["off_plays"].reindex(teams).fillna(0).astype(int).values,
        "def_plays": raw["def_plays"].reindex(teams).fillna(0).astype(int).values,
        "adj_off_epa": adj_off.values,
        "adj_def_epa": adj_def.values,
    })
    out["adj_net_epa"] = out["adj_off_epa"] - out["adj_def_epa"]
    return out.sort_values("adj_net_epa", ascending=False).reset_index(drop=True)


def shrink_to_prior(
    current: pd.DataFrame,
    prior: pd.DataFrame,
    prior_plays_equiv: float = PRIOR_PLAYS_EQUIV,
    prior_regress: float = PRIOR_REGRESS,
) -> pd.DataFrame:
    """
    Prior ratings are first regressed toward league average (multiplied by
    prior_regress, since year-over-year EPA is only partly sticky), then:
    Bayesian-style shrink of current adj EPA toward prior-season ratings.

    weight_current = n / (n + k), weight_prior = k / (n + k)
    Applied separately to offense and defense.
    """
    prior_idx = prior.set_index("team")
    rows = []
    for row in current.itertuples(index=False):
        team = row.team
        if team in prior_idx.index:
            p_off = prior_regress * float(prior_idx.loc[team, "adj_off_epa"])
            p_def = prior_regress * float(prior_idx.loc[team, "adj_def_epa"])
        else:
            p_off, p_def = 0.0, 0.0
        n_off = max(int(row.off_plays), 0)
        n_def = max(int(row.def_plays), 0)
        w_off = n_off / (n_off + prior_plays_equiv) if (n_off + prior_plays_equiv) else 0.0
        w_def = n_def / (n_def + prior_plays_equiv) if (n_def + prior_plays_equiv) else 0.0
        shr_off = w_off * row.adj_off_epa + (1 - w_off) * p_off
        shr_def = w_def * row.adj_def_epa + (1 - w_def) * p_def
        rows.append({
            "team": team,
            "off_plays": n_off,
            "def_plays": n_def,
            "adj_off_epa": row.adj_off_epa,
            "adj_def_epa": row.adj_def_epa,
            "prior_off_epa": p_off,
            "prior_def_epa": p_def,
            "shrunk_off_epa": shr_off,
            "shrunk_def_epa": shr_def,
            "rating": shr_off - shr_def,
            "shrink_weight_off": w_off,
            "shrink_weight_def": w_def,
        })
    return pd.DataFrame(rows).sort_values("rating", ascending=False).reset_index(drop=True)


def build_prior_ratings(pbp: pd.DataFrame, prior_seasons: list[int]) -> pd.DataFrame:
    """Average opponent-adjusted ratings across prior full seasons (REG)."""
    frames = []
    for s in prior_seasons:
        sp = pbp[pbp["season"] == s]
        if "season_type" in sp.columns:
            sp = sp[sp["season_type"] == "REG"]
        plays = filter_offensive_plays(sp)
        if len(plays) == 0:
            continue
        frames.append(opponent_adjust(plays).assign(season=s))
    if not frames:
        return pd.DataFrame(columns=["team", "adj_off_epa", "adj_def_epa", "adj_net_epa"])
    all_r = pd.concat(frames, ignore_index=True)
    # Weight recent prior season more (simple: last prior gets 2x)
    weights = {s: (i + 1) for i, s in enumerate(sorted(prior_seasons))}
    all_r["w"] = all_r["season"].map(weights).fillna(1)
    def wavg(g, col):
        return float(np.average(g[col], weights=g["w"]))
    rows = []
    for team, g in all_r.groupby("team"):
        rows.append({
            "team": team,
            "adj_off_epa": wavg(g, "adj_off_epa"),
            "adj_def_epa": wavg(g, "adj_def_epa"),
            "adj_net_epa": wavg(g, "adj_net_epa"),
        })
    return pd.DataFrame(rows)


def build_current_ratings(
    pbp: pd.DataFrame,
    season: int,
    through_week: int,
    prior_seasons: list[int],
    prior_plays_equiv: float = PRIOR_PLAYS_EQUIV,
    prior_regress: float = PRIOR_REGRESS,
    prior_cache: dict | None = None,
) -> pd.DataFrame:
    """Prior ratings + current season through_week, shrunk."""
    key = tuple(prior_seasons)
    if prior_cache is not None and key in prior_cache:
        prior = prior_cache[key]
    else:
        prior = build_prior_ratings(pbp, prior_seasons)
        if prior_cache is not None:
            prior_cache[key] = prior
    sp = pbp[(pbp["season"] == season) & (pbp["week"] <= through_week)]
    if "season_type" in sp.columns:
        sp = sp[sp["season_type"] == "REG"]
    plays = filter_offensive_plays(sp)
    current = opponent_adjust(plays)
    return shrink_to_prior(current, prior, prior_plays_equiv=prior_plays_equiv, prior_regress=prior_regress)
