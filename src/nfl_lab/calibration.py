"""Margin calibration v2. Proposed for 2026 week 6 on; every number is fit on 2016-2021 only.

Why: the frozen model's margins are too bunched up in weeks 5-8 and its totals barely move.

  * Margins. One points-per-EPA number was fit across all weeks pooled. Checked
    leave-one-season-out on 2016-2021, a projected 1-point edge turned into ~1.24
    real points in weeks 5-8 and ~0.91 in weeks 9+, so mid-season projections were
    squeezed. Re-fitting the scale per part of the season fixes that. Re-tuning the
    EPA shrinkage did not help (the grid still picks the heavy setting). A shrunk
    scoring-margin rating (points for minus points against, pulled toward last
    seasons) predicted margins better than the EPA rating on 2016-2021, and once it
    was in, the EPA rating added nothing (its coefficient went negative), so v2
    margins use the scoring-margin rating with a per-season-segment scale.
  * Totals. Totals used one EPA number (with the defense sign flipped, fixed in the
    previous commit) and ignored how many points teams actually score and allow.
    v2 adds each team's shrunk points-scored and points-allowed levels.

Causality: week W uses only games before week W of season S plus seasons S-3..S-1.
Selection rule (fixed before the grid ran): rank by leave-one-season-out MAE on
2016-2021; among settings within 0.01 points of the best, take the one whose
actual-vs-projected slope is closest to 1 in weeks 1-4, 5-8 and 9+. Coefficients
must be positive. Lines are never used to fit or choose anything.
"""
from __future__ import annotations

import itertools
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy.stats import norm

from .config import OUTPUT_DIR
from .ratings import shrink_to_prior
from .walkforward import features as epa_features
from .walkforward import precompute

V2_PATH = OUTPUT_DIR / "calibration" / "model_v2.json"
TUNE_SEASONS = list(range(2016, 2022))
APPLIES_FROM = {"season": 2026, "week": 6}
BUCKETS = [("wk1_4", 1, 4), ("wk5_8", 5, 8), ("wk9_plus", 9, 99)]
MARGIN_KG, MARGIN_RG = [4, 8, 12, 16, 24, 32], [0.2, 0.3, 0.5, 0.7]
TOTAL_KG, TOTAL_RG = [1, 2, 3, 8, 12, 16, 24], [0.3, 0.5, 0.7, 0.85, 1.0]
EPA_GRID = [(0.3, 1200), (0.3, 1600), (0.45, 800), (0.45, 1200)]
MAE_TOL = 0.01


# ---------------------------------------------------------------- scoring levels
def team_games(schedules: pd.DataFrame) -> pd.DataFrame:
    s = schedules[schedules["home_score"].notna()]
    if "game_type" in s.columns:
        s = s[s["game_type"] == "REG"]
    h = s[["season", "week", "home_team", "home_score", "away_score"]].set_axis(["season", "week", "team", "pf", "pa"], axis=1)
    a = s[["season", "week", "away_team", "away_score", "home_score"]].set_axis(["season", "week", "team", "pf", "pa"], axis=1)
    return pd.concat([h, a], ignore_index=True)


def _prior_levels(tg: pd.DataFrame, season: int) -> tuple[pd.DataFrame, float]:
    """Team points for/against vs league over seasons S-3..S-1, weighted 1:2:3."""
    rows = []
    for i, y in enumerate(range(season - 3, season)):
        t = tg[tg["season"] == y]
        if not len(t):
            continue
        L = float(t["pf"].mean())
        m = t.groupby("team")[["pf", "pa"]].mean() - L
        rows.append(m.assign(w=i + 1, L=L).reset_index())
    if not rows:
        raise RuntimeError(f"no prior seasons with scores for {season}")
    a = pd.concat(rows)
    prior = a.groupby("team").apply(
        lambda g: pd.Series({c: np.average(g[c], weights=g["w"]) for c in ("pf", "pa")}), include_groups=False)
    yrs = a.drop_duplicates("w")
    return prior, float(np.average(yrs["L"], weights=yrs["w"]))


def scoring_levels(tg: pd.DataFrame, season: int, week: int, kg: float, rg: float, cache: dict | None = None) -> pd.DataFrame:
    """Shrunk points scored / allowed per game for every team, as of the start of `week`.

    level = (points so far + kg * (league + rg * prior deviation)) / (games so far + kg)
    """
    if cache is not None and season in cache:
        prior, L = cache[season]
    else:
        prior, L = _prior_levels(tg, season)
        if cache is not None:
            cache[season] = (prior, L)
    cur = tg[(tg["season"] == season) & (tg["week"] < week)].groupby("team").agg(
        pf=("pf", "sum"), pa=("pa", "sum"), n=("pf", "size"))
    teams = prior.index.union(cur.index)
    cur, pr = cur.reindex(teams).fillna(0.0), prior.reindex(teams).fillna(0.0)
    out = pd.DataFrame(index=teams)
    for c in ("pf", "pa"):
        out[c] = (cur[c] + kg * (L + rg * pr[c])) / (cur["n"] + kg)
    return out


def _bucket_cols(prefix: str) -> list[str]:
    return [f"{prefix}_{b}" for b, _, _ in BUCKETS]


def add_level_features(g: pd.DataFrame, tg: pd.DataFrame, kg_m: float, rg_m: float, kg_t: float, rg_t: float,
                       cache: dict | None = None) -> pd.DataFrame:
    g = g.copy()
    ptdiff = pd.Series(np.nan, index=g.index)
    pts_env = pd.Series(np.nan, index=g.index)
    for (s, w), idx in g.groupby(["season", "week"]).groups.items():
        lm = scoring_levels(tg, int(s), int(w), kg_m, rg_m, cache)
        lt = scoring_levels(tg, int(s), int(w), kg_t, rg_t, cache)
        H, A = g.loc[idx, "home_team"], g.loc[idx, "away_team"]
        ptdiff[idx] = (H.map(lm["pf"]) - H.map(lm["pa"])) - (A.map(lm["pf"]) - A.map(lm["pa"]))
        pts_env[idx] = H.map(lt["pf"]) + A.map(lt["pa"]) + A.map(lt["pf"]) + H.map(lt["pa"])
    g["ptdiff"], g["pts_env"] = ptdiff, pts_env
    for b, lo, hi in BUCKETS:
        on = g["week"].between(lo, hi).astype(float)
        g[f"pt_{b}"] = g["ptdiff"] * on
        if "rating_diff" in g.columns:
            g[f"rd_{b}"] = g["rating_diff"] * on
    if "hfa_flag" not in g.columns:
        g["hfa_flag"] = np.where(g.get("location", "Home") == "Neutral", 0.0, 1.0)
    g["one"] = 1.0
    return g


# ---------------------------------------------------------------- fitting helpers
def _ols(f: pd.DataFrame, cols: list[str], y: str) -> np.ndarray:
    return np.linalg.lstsq(f[cols].values.astype(float), f[y].values.astype(float), rcond=None)[0]


def _loso(f: pd.DataFrame, cols: list[str], y: str, seasons: list[int]) -> pd.Series:
    pred = pd.Series(np.nan, index=f.index)
    for h in seasons:
        tr, te = f[f["season"] != h], f[f["season"] == h]
        pred[te.index] = te[cols].values.astype(float) @ _ols(tr, cols, y)
    return pred


def _calibration(f: pd.DataFrame, pred: pd.Series, y: str) -> dict:
    out = {"all": float(np.polyfit(pred, f[y], 1)[0])}
    for b, lo, hi in BUCKETS:
        m = f["week"].between(lo, hi)
        out[b] = float(np.polyfit(pred[m], f.loc[m, y], 1)[0])
    return out


def _score(f: pd.DataFrame, pred: pd.Series, y: str, line: str) -> dict:
    cal = _calibration(f, pred, y)
    return {"loso_mae": float(np.mean(np.abs(pred - f[y]))), "projected_sd": float(pred.std()),
            "slope_actual_on_projected": cal, "calibration_error": float(np.mean([abs(cal[b] - 1) for b, _, _ in BUCKETS])),
            "market_sd": float(f[line].std()), "actual_sd": float(f[y].std()),
            "week5_projected_sd": float(pred[f["week"] == 5].std())}


def _select(rows: list[dict]) -> dict:
    ok = [r for r in rows if r["all_coefs_positive"]]
    best = min(r["loso_mae"] for r in ok)
    return min([r for r in ok if r["loso_mae"] <= best + MAE_TOL], key=lambda r: r["calibration_error"])


def _env(pre: dict, games: pd.DataFrame, regress: float, plays_equiv: float, def_sign: float = 1.0) -> pd.Series:
    """Totals EPA environment: home_off + away_off + def_sign * (home_def + away_def).

    def_sign=+1 is correct (defense = EPA allowed). def_sign=-1 rebuilds the frozen
    model's flipped feature, used only to report the 'current model' baseline.
    """
    env = pd.Series(np.nan, index=games.index)
    for (s, w), idx in games.groupby(["season", "week"]).groups.items():
        r = shrink_to_prior(pre["current"][(s, w)], pre["priors"][s], prior_plays_equiv=plays_equiv,
                            prior_regress=regress).set_index("team")
        H, A = games.loc[idx, "home_team"], games.loc[idx, "away_team"]
        env[idx] = (H.map(r["shrunk_off_epa"]) + A.map(r["shrunk_off_epa"])
                    + def_sign * (H.map(r["shrunk_def_epa"]) + A.map(r["shrunk_def_epa"])))
    return env


# ---------------------------------------------------------------- tuning (2016-2021 only)
def fit_v2(pbp: pd.DataFrame, schedules: pd.DataFrame, dropbacks: pd.DataFrame, locked: dict) -> dict:
    from . import qb_adjust

    seasons = TUNE_SEASONS
    assert max(seasons) <= 2021, "v2 may only be fit on 2016-2021"
    sched = schedules[schedules["season"] <= max(seasons)]
    assert pbp["season"].max() <= max(seasons), "pass only pre-2022 play-by-play"
    tg = team_games(sched)
    pre = precompute(pbp, sched, seasons)
    r0, k0 = locked["prior_regress"], locked["prior_plays_equiv"]
    base = epa_features(pre, r0, k0)
    base["env_fix"] = _env(pre, base, r0, k0)
    base["env_old"] = _env(pre, base, r0, k0, def_sign=-1.0)
    cache: dict = {}

    # Margin candidates: current EPA model, EPA with per-segment scale, scoring-margin rating (single / per-segment)
    mrows = []
    for (r, k) in EPA_GRID:
        f = add_level_features(epa_features(pre, r, k), tg, 16, 0.3, 2, 1.0, cache)
        for name, cols in [("epa_single_scale", ["rating_diff", "hfa_flag"]),
                           ("epa_per_segment_scale", _bucket_cols("rd") + ["hfa_flag"])]:
            c = _ols(f, cols, "margin")
            mrows.append({"model": name, "prior_regress": r, "prior_plays_equiv": k, "kg": None, "rg": None,
                          "cols": cols, "all_coefs_positive": bool((c > 0).all()),
                          **_score(f, _loso(f, cols, "margin", seasons), "margin", "spread_line")})
    for kg, rg in itertools.product(MARGIN_KG, MARGIN_RG):
        f = add_level_features(base, tg, kg, rg, 2, 1.0, cache)
        for name, cols in [("points_single_scale", ["ptdiff", "hfa_flag"]),
                           ("points_per_segment_scale", _bucket_cols("pt") + ["hfa_flag"])]:
            c = _ols(f, cols, "margin")
            mrows.append({"model": name, "prior_regress": r0, "prior_plays_equiv": k0, "kg": kg, "rg": rg,
                          "cols": cols, "all_coefs_positive": bool((c > 0).all()),
                          **_score(f, _loso(f, cols, "margin", seasons), "margin", "spread_line")})
    m_pick = _select(mrows)
    current = next(r for r in mrows if r["model"] == "epa_single_scale" and (r["prior_regress"], r["prior_plays_equiv"]) == (r0, k0))

    # Totals candidates (sign-fixed EPA environment and/or scoring levels)
    trows = []
    for kg, rg in itertools.product(TOTAL_KG, TOTAL_RG):
        f = add_level_features(base, tg, 16, 0.3, kg, rg, cache)
        for name, cols in [("points_levels", ["pts_env", "one"]), ("epa_env_plus_points_levels", ["env_fix", "pts_env", "one"])]:
            c = _ols(f, cols, "total_points")
            trows.append({"model": name, "kg": kg, "rg": rg, "cols": cols, "all_coefs_positive": bool((c > 0).all()),
                          **_score(f, _loso(f, cols, "total_points", seasons), "total_points", "total_line")})
    t_pick = _select(trows)
    f0 = base.assign(one=1.0)
    t_current = _score(f0, _loso(f0, ["env_old", "one"], "total_points", seasons), "total_points", "total_line")
    t_signfix = _score(f0, _loso(f0, ["env_fix", "one"], "total_points", seasons), "total_points", "total_line")

    # Final fit with the chosen settings + the starting-QB term refit jointly
    f = add_level_features(base, tg, m_pick["kg"], m_pick["rg"], t_pick["kg"], t_pick["rg"], cache)
    fq = qb_adjust.qb_features(dropbacks, f)
    mcols = m_pick["cols"]
    loso_no_qb = float(np.mean(np.abs(_loso(fq, mcols, "margin", seasons) - fq["margin"])))
    loso_qb = float(np.mean(np.abs(_loso(fq, mcols + ["qb_diff"], "margin", seasons) - fq["margin"])))
    use_qb = loso_qb < loso_no_qb
    mc = _ols(fq, mcols + (["qb_diff"] if use_qb else []), "margin")
    resid = fq["margin"].values - fq[mcols + (["qb_diff"] if use_qb else [])].values @ mc
    tcols = t_pick["cols"]
    tc = _ols(f, tcols, "total_points")
    tres = f["total_points"].values - f[tcols].values @ tc
    strip = lambda d: {k: v for k, v in d.items() if k != "cols"}
    return {
        "model_version": "v2-margin-calibration",
        "status": "PROPOSED. Applies only from 2026 week 6 if the PR is merged. Week 1-5 cards and the 2022-2025 ledger are untouched.",
        "fit_on_seasons": seasons,
        "fitted_at": datetime.now(ZoneInfo("America/Chicago")).isoformat(),
        "applies_from": APPLIES_FROM,
        "selection_rule": "LOSO MAE on 2016-2021; among settings within 0.01 of the best, smallest mean |slope-1| over weeks 1-4/5-8/9+; positive coefficients only. Lines never used.",
        "buckets": [{"name": b, "weeks": [lo, hi]} for b, lo, hi in BUCKETS],
        "margin": {"model": m_pick["model"], "kg_games": m_pick["kg"], "prior_regress_points": m_pick["rg"],
                   "coefs": dict(zip(mcols, map(float, mc[:len(mcols)]))), "margin_sigma": float(np.std(resid, ddof=len(mc)))},
        "total": {"model": t_pick["model"], "kg_games": t_pick["kg"], "prior_regress_points": t_pick["rg"],
                  "epa_prior_regress": r0, "epa_prior_plays_equiv": k0,
                  "coefs": dict(zip(tcols, map(float, tc))), "total_sigma": float(np.std(tres, ddof=len(tc)))},
        "qb": {"adopted": bool(use_qb), "points_per_qb_epa_db": float(mc[-1]) if use_qb else 0.0,
               "margin_sigma": float(np.std(resid, ddof=len(mc))),
               "loso_mae_without_qb": loso_no_qb, "loso_mae_with_qb": loso_qb},
        "tuning_window_2016_2021": {
            "margin_current_frozen_model": strip(current),
            "margin_v2": strip(m_pick),
            "total_current_frozen_model_flipped_sign": t_current,
            "total_sign_fix_only": t_signfix,
            "total_v2": strip(t_pick),
        },
        "grids": {"margin": [strip(r) for r in mrows], "total": [strip(r) for r in trows]},
    }


def holdout_info(pbp: pd.DataFrame, schedules: pd.DataFrame, locked: dict, v2: dict) -> dict:
    """2022-2025 MAE / spread with v2 FROZEN. Information only: computed after selection, chooses nothing."""
    seasons = [2022, 2023, 2024, 2025]
    tg = team_games(schedules)
    pre = precompute(pbp, schedules, seasons)
    r0, k0 = locked["prior_regress"], locked["prior_plays_equiv"]
    f = epa_features(pre, r0, k0)
    f["env_fix"] = _env(pre, f, r0, k0)
    f["env_old"] = _env(pre, f, r0, k0, def_sign=-1.0)
    f = add_level_features(f, tg, v2["margin"]["kg_games"], v2["margin"]["prior_regress_points"],
                           v2["total"]["kg_games"], v2["total"]["prior_regress_points"])
    pm_old = locked["points_per_net_epa"] * f["rating_diff"] + locked["hfa"] * f["hfa_flag"]
    mc, tcf = v2["margin"]["coefs"], v2["total"]["coefs"]
    pt_old = locked["base_total"] + locked["points_per_combined_off"] * f["env_old"]
    pm = sum(f[c] * v for c, v in mc.items())
    pt = sum(f[c] * v for c, v in tcf.items())

    def s(p, y, line):
        return {"mae": float(np.mean(np.abs(p - f[y]))), "projected_sd": float(p.std()),
                "slope_actual_on_projected": float(np.polyfit(p, f[y], 1)[0]), "market_sd": float(f[line].std()),
                "market_mae": float(np.mean(np.abs(f[line] - f[y])))}
    return {"note": "Information only. v2 settings were frozen on 2016-2021 before this ran; nothing here was used to choose them.",
            "n_games": int(len(f)), "margin_current": s(pm_old, "margin", "spread_line"), "margin_v2": s(pm, "margin", "spread_line"),
            "total_current": s(pt_old, "total_points", "total_line"), "total_v2": s(pt, "total_points", "total_line")}


# ---------------------------------------------------------------- live projection
def load_v2() -> dict | None:
    return json.loads(V2_PATH.read_text()) if V2_PATH.exists() else None


def applies(v2: dict | None, season: int, week: int) -> bool:
    return bool(v2) and season == v2["applies_from"]["season"] and week >= v2["applies_from"]["week"]


def project_slate(slate: pd.DataFrame, schedules: pd.DataFrame, ratings: pd.DataFrame, v2: dict,
                  season: int, week: int) -> pd.DataFrame:
    """Same columns as model.project_games, from v2. Uses only games before `week` and seasons S-3..S-1."""
    past = (schedules["season"] < season) | ((schedules["season"] == season) & (schedules["week"] < week))
    tg = team_games(schedules[past])
    r = ratings.set_index("team")
    g = slate.copy()
    g["week"] = week
    g["home_rating"], g["away_rating"] = g["home_team"].map(r["rating"]), g["away_team"].map(r["rating"])
    g["rating_diff"] = g["home_rating"] - g["away_rating"]
    g["env_fix"] = (g["home_team"].map(r["shrunk_off_epa"]) + g["away_team"].map(r["shrunk_off_epa"])
                    + g["home_team"].map(r["shrunk_def_epa"]) + g["away_team"].map(r["shrunk_def_epa"]))
    g = add_level_features(g, tg, v2["margin"]["kg_games"], v2["margin"]["prior_regress_points"],
                           v2["total"]["kg_games"], v2["total"]["prior_regress_points"])
    g["proj_margin"] = sum(g[c] * v for c, v in v2["margin"]["coefs"].items())
    g["proj_total"] = sum(g[c] * v for c, v in v2["total"]["coefs"].items())
    g["proj_spread"] = -g["proj_margin"]
    g["home_win_prob"] = norm.cdf(g["proj_margin"] / v2["margin"]["margin_sigma"])
    g["away_win_prob"] = 1.0 - g["home_win_prob"]
    g["model_favorite"] = np.where(g["proj_margin"] >= 0, g["home_team"], g["away_team"])
    g["model_version"] = v2["model_version"]
    cols = ["game_id", "season", "week", "gameday", "gametime", "away_team", "home_team", "location",
            "away_rating", "home_rating", "rating_diff", "ptdiff", "proj_margin", "proj_spread", "proj_total",
            "home_win_prob", "away_win_prob", "model_favorite", "model_version", "spread_line", "total_line",
            "home_moneyline", "away_moneyline", "home_score", "away_score", "result"]
    keep = [c for c in cols if c in g.columns]
    return g[keep].sort_values(["gameday", "gametime", "game_id"]).reset_index(drop=True)
