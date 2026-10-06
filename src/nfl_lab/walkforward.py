"""Strictly walk-forward tuning + pre-registered holdout grading vs closing lines.

Causality guarantees:
  * Current-season ratings for week W use only plays from weeks < W.
  * Priors for season S use only REG plays from seasons S-3..S-1.
  * Hyperparameters and regression coefficients are chosen using 2016-2021 only
    and then frozen; the 2022-2025 holdout never influences any parameter.
  * Line data (spread_line / total_line) is never used in tuning, only grading.
"""
from __future__ import annotations

import itertools
import json
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy.stats import binomtest, norm

from .config import OUTPUT_DIR
from .data_loader import filter_offensive_plays
from .ratings import build_prior_ratings, opponent_adjust, shrink_to_prior

BT_DIR = OUTPUT_DIR / "backtest"
# Totals coefficients refit on 2016-2021 after the defense-sign fix. The frozen
# locked_model.json totals numbers were fit on the flipped feature, so they must not
# be paired with the corrected one. Margin coefficients are unaffected.
TOTALS_SIGNFIX_PATH = OUTPUT_DIR / "calibration" / "totals_signfix_2016_2021.json"
BREAKEVEN = 110 / 210  # 0.5238
REGRESS_GRID = [0.3, 0.45, 0.6, 0.75, 0.9]
PLAYS_EQUIV_GRID = [150, 300, 500, 800, 1200]


# ---------------------------------------------------------------- precompute
def precompute(pbp: pd.DataFrame, schedules: pd.DataFrame, seasons: list[int]) -> dict:
    """Causal building blocks for every (season, week) game in `seasons`."""
    reg = pbp[pbp["season_type"] == "REG"] if "season_type" in pbp.columns else pbp
    plays_by_season = {s: filter_offensive_plays(g) for s, g in reg.groupby("season")}
    priors, current, games = {}, {}, []
    for s in seasons:
        prior_seasons = [y for y in range(s - 3, s) if y in plays_by_season]
        priors[s] = build_prior_ratings(pbp, prior_seasons)
        sched = schedules[(schedules["season"] == s) & (schedules["game_type"] == "REG")
                          & schedules["home_score"].notna()]
        plays = plays_by_season.get(s, pd.DataFrame())
        for w in sorted(sched["week"].unique()):
            before = plays[plays["week"] < w] if len(plays) else plays
            if len(before):
                current[(s, w)] = opponent_adjust(before)
            else:  # week 1: no current-season data, rating == regressed prior
                current[(s, w)] = pd.DataFrame({
                    "team": priors[s]["team"], "off_plays": 0, "def_plays": 0,
                    "adj_off_epa": 0.0, "adj_def_epa": 0.0,
                })
        games.append(sched)
    return {"priors": priors, "current": current, "games": pd.concat(games, ignore_index=True)}


def features(pre: dict, regress: float, plays_equiv: float) -> pd.DataFrame:
    """Per-game causal rating features for one hyperparameter setting."""
    out = []
    for (s, w), cur in pre["current"].items():
        r = shrink_to_prior(cur, pre["priors"][s], prior_plays_equiv=plays_equiv,
                            prior_regress=regress).set_index("team")
        g = pre["games"][(pre["games"]["season"] == s) & (pre["games"]["week"] == w)].copy()
        g["home_rating"] = g["home_team"].map(r["rating"])
        g["away_rating"] = g["away_team"].map(r["rating"])
        g["rating_diff"] = g["home_rating"] - g["away_rating"]
        # Defense = EPA allowed (higher = leakier), so it adds to the scoring environment.
        g["off_env"] = (g["home_team"].map(r["shrunk_off_epa"]) + g["away_team"].map(r["shrunk_off_epa"])
                        + g["home_team"].map(r["shrunk_def_epa"]) + g["away_team"].map(r["shrunk_def_epa"]))
        out.append(g)
    f = pd.concat(out, ignore_index=True)
    f["margin"] = f["home_score"] - f["away_score"]
    f["total_points"] = f["home_score"] + f["away_score"]
    # Neutral-site games get no home field
    f["hfa_flag"] = np.where(f.get("location", "Home") == "Neutral", 0.0, 1.0)
    return f.dropna(subset=["rating_diff"])


def _ols(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.linalg.lstsq(X, y, rcond=None)[0]


def fit_coefs(f: pd.DataFrame) -> dict:
    Xm = np.column_stack([f["rating_diff"], f["hfa_flag"]])
    cm = _ols(Xm, f["margin"].values)
    resid = f["margin"].values - Xm @ cm
    Xt = np.column_stack([f["off_env"], np.ones(len(f))])
    ct = _ols(Xt, f["total_points"].values)
    tres = f["total_points"].values - Xt @ ct
    return {
        "points_per_net_epa": float(cm[0]), "hfa": float(cm[1]),
        "margin_sigma": float(np.std(resid, ddof=2)),
        "points_per_combined_off": float(ct[0]), "base_total": float(ct[1]),
        "total_sigma": float(np.std(tres, ddof=2)), "n_fit_games": int(len(f)),
    }


def apply_coefs(f: pd.DataFrame, c: dict) -> pd.DataFrame:
    f = f.copy()
    f["proj_margin"] = c["points_per_net_epa"] * f["rating_diff"] + c["hfa"] * f["hfa_flag"]
    f["proj_total"] = c["base_total"] + c["points_per_combined_off"] * f["off_env"]
    f["home_win_prob"] = norm.cdf(f["proj_margin"] / c["margin_sigma"])
    return f


# ---------------------------------------------------------------- tuning
def tune(pre_tune: dict, tune_seasons: list[int]) -> dict:
    """Grid search (regress, plays_equiv) by leave-one-season-out MAE vs margin."""
    grid = []
    for rg, pe in itertools.product(REGRESS_GRID, PLAYS_EQUIV_GRID):
        f = features(pre_tune, rg, pe)
        errs = []
        for hold in tune_seasons:
            c = fit_coefs(f[f["season"] != hold])
            p = apply_coefs(f[f["season"] == hold], c)
            errs.append(np.abs(p["proj_margin"] - p["margin"]).values)
        mae = float(np.mean(np.concatenate(errs)))
        grid.append({"prior_regress": rg, "prior_plays_equiv": pe, "loso_mae": mae})
    grid.sort(key=lambda d: d["loso_mae"])
    best = grid[0]
    f_best = features(pre_tune, best["prior_regress"], best["prior_plays_equiv"])
    coefs = fit_coefs(f_best)
    return {"best": best, "grid": grid, "coefs": coefs, "features": f_best}


# ---------------------------------------------------------------- grading
def grade(f: pd.DataFrame, spread_min: float, total_min: float) -> pd.DataFrame:
    """Attach line-based picks and outcomes to each game (ledger rows)."""
    g = f.copy()
    g["spread_edge"] = g["proj_margin"] - g["spread_line"]  # >0 = model likes home vs line
    g["spread_pick"] = np.where(g["spread_edge"] > 0, g["home_team"], g["away_team"])
    ats = g["margin"] - g["spread_line"]
    g["spread_outcome"] = np.select(
        [ats == 0, (ats > 0) == (g["spread_edge"] > 0)], ["push", "win"], "loss")
    g.loc[g["spread_line"].isna() | (g["spread_edge"] == 0), "spread_outcome"] = None
    g["spread_bet_locked_rule"] = g["spread_edge"].abs() >= spread_min

    g["total_edge"] = g["proj_total"] - g["total_line"]
    g["total_pick"] = np.where(g["total_edge"] > 0, "over", "under")
    tdiff = g["total_points"] - g["total_line"]
    g["total_outcome"] = np.select(
        [tdiff == 0, (tdiff > 0) == (g["total_edge"] > 0)], ["push", "win"], "loss")
    g.loc[g["total_line"].isna() | (g["total_edge"] == 0), "total_outcome"] = None
    g["total_bet_locked_rule"] = g["total_edge"].abs() >= total_min
    return g


def _record(outcomes: pd.Series) -> dict:
    o = outcomes.dropna()
    w, l, p = int((o == "win").sum()), int((o == "loss").sum()), int((o == "push").sum())
    n = w + l
    rec = {"bets": int(len(o)), "wins": w, "losses": l, "pushes": p,
           "win_rate": (w / n) if n else None}
    if n:
        bt = binomtest(w, n, BREAKEVEN, alternative="greater")
        ci = binomtest(w, n).proportion_ci(confidence_level=0.95, method="wilson")
        rec.update({
            "win_rate_ci95": [float(ci.low), float(ci.high)],
            "p_value_vs_breakeven_one_sided": float(bt.pvalue),
            "roi_at_minus_110": float((w * (100 / 110) - l) / (w + l + p)) if (w + l + p) else None,
            "units_at_minus_110": float(w * (100 / 110) - l),
            "beats_breakeven": bool(w / n > BREAKEVEN),
        })
    return rec


def _buckets(g: pd.DataFrame, edge_col: str, out_col: str, edges: list[float]) -> list[dict]:
    rows = []
    a = g[edge_col].abs()
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (a >= lo) & (a < hi)
        label = f"{lo:g}-{hi:g}" if math.isfinite(hi) else f"{lo:g}+"
        rows.append({"edge_bucket": label, **_record(g.loc[m, out_col])})
    return rows


def _accuracy(g: pd.DataFrame, sigma: float) -> dict:
    hw = np.where(g["margin"] > 0, 1.0, np.where(g["margin"] == 0, 0.5, 0.0))
    has_line = g["spread_line"].notna()
    mkt_prob = norm.cdf(g.loc[has_line, "spread_line"] / sigma)
    nt = g["margin"] != 0
    return {
        "n_games": int(len(g)),
        "model_mae_margin": float(np.mean(np.abs(g["proj_margin"] - g["margin"]))),
        "market_mae_margin": float(np.mean(np.abs(g.loc[has_line, "spread_line"] - g.loc[has_line, "margin"]))),
        "model_mae_total": float(np.mean(np.abs(g["proj_total"] - g["total_points"]))),
        "market_mae_total": float(np.nanmean(np.abs(g["total_line"] - g["total_points"]))),
        "model_brier": float(np.mean((g["home_win_prob"] - hw) ** 2)),
        "market_brier_from_spread": float(np.mean((mkt_prob - hw[has_line.values]) ** 2)),
        "model_straight_up_acc": float(((g["proj_margin"] > 0) == (g["margin"] > 0))[nt].mean()),
        "corr_model_margin": float(np.corrcoef(g["proj_margin"], g["margin"])[0, 1]),
    }


def summarize(g: pd.DataFrame, sigma: float, label: str) -> dict:
    return {
        "window": label,
        "seasons": sorted(int(s) for s in g["season"].unique()),
        "accuracy_ats_free": _accuracy(g, sigma),
        "locked_rule": {
            "spread": _record(g.loc[g["spread_bet_locked_rule"], "spread_outcome"]),
            "total": _record(g.loc[g["total_bet_locked_rule"], "total_outcome"]),
        },
        "all_games_model_side": {
            "spread": _record(g["spread_outcome"]),
            "total": _record(g["total_outcome"]),
        },
        "descriptive_only__spread_edge_buckets": _buckets(g, "spread_edge", "spread_outcome", [0, 1, 2, 3, np.inf]),
        "descriptive_only__total_edge_buckets": _buckets(g, "total_edge", "total_outcome", [0, 1, 2, 3, 5, np.inf]),
        "descriptive_only__per_season": [
            {"season": int(s),
             "accuracy_ats_free": _accuracy(gs, sigma),
             "locked_rule_spread": _record(gs.loc[gs["spread_bet_locked_rule"], "spread_outcome"]),
             "locked_rule_total": _record(gs.loc[gs["total_bet_locked_rule"], "total_outcome"])}
            for s, gs in g.groupby("season")
        ],
    }


LEDGER_COLS = [
    "game_id", "season", "week", "gameday", "away_team", "home_team", "away_score", "home_score",
    "margin", "total_points", "home_rating", "away_rating", "proj_margin", "proj_total", "home_win_prob",
    "spread_line", "spread_edge", "spread_pick", "spread_bet_locked_rule", "spread_outcome",
    "total_line", "total_edge", "total_pick", "total_bet_locked_rule", "total_outcome",
]


def run(pbp: pd.DataFrame, schedules: pd.DataFrame, prereg: dict) -> dict:
    tune_seasons, hold_seasons = prereg["tuning_window"], prereg["holdout_window"]
    smin, tmin = prereg["headline_rule"]["spread_edge_min"], prereg["headline_rule"]["total_edge_min"]

    # 1) Tuning on 2016-2021 only
    pre_tune = precompute(pbp, schedules, tune_seasons)
    t = tune(pre_tune, tune_seasons)
    locked = {
        "locked_at": datetime.now(ZoneInfo("America/Chicago")).isoformat(),
        "fit_on_seasons": tune_seasons,
        "prior_regress": t["best"]["prior_regress"],
        "prior_plays_equiv": t["best"]["prior_plays_equiv"],
        "prior_seasons_weighting": "S-3:S-2:S-1 = 1:2:3",
        **t["coefs"],
    }
    BT_DIR.mkdir(parents=True, exist_ok=True)
    (BT_DIR / "locked_model.json").write_text(json.dumps(
        {"locked_model": locked, "tuning_grid_loso_mae": t["grid"]}, indent=2))

    # 2) Holdout 2022-2025: frozen params, causal ratings, graded once
    pre_hold = precompute(pbp, schedules, hold_seasons)
    f_hold = apply_coefs(features(pre_hold, locked["prior_regress"], locked["prior_plays_equiv"]), locked)
    g_hold = grade(f_hold, smin, tmin)
    # Tuning-window grading (in-sample for coefficients; descriptive only)
    g_tune = grade(apply_coefs(t["features"], locked), smin, tmin)

    sigma = locked["margin_sigma"]
    result = {
        "preregistration": prereg,
        "graded_at": datetime.now(ZoneInfo("America/Chicago")).isoformat(),
        "locked_model": locked,
        "HEADLINE_holdout": summarize(g_hold, sigma, "holdout 2022-2025 (untouched, graded once)"),
        "descriptive_only__tuning_window_in_sample": summarize(g_tune, sigma, "tuning 2016-2021 (in-sample, descriptive)"),
    }
    (BT_DIR / "backtest_results.json").write_text(json.dumps(result, indent=2, default=str))

    ledger = pd.concat([g_hold.assign(window="holdout"), g_tune.assign(window="tuning_in_sample")])
    ledger = ledger[["window"] + LEDGER_COLS].sort_values(["season", "week", "game_id"])
    (BT_DIR / "ledger.json").write_text(json.dumps({
        "preregistration": prereg,
        "locked_model": locked,
        "graded_at": result["graded_at"],
        "games": json.loads(ledger.to_json(orient="records")),
    }, indent=2))
    ledger.to_csv(BT_DIR / "ledger.csv", index=False)
    return result


# ---------------------------------------------------------------- totals sign fix
def refit_totals_signfix(pbp: pd.DataFrame, schedules: pd.DataFrame, locked: dict,
                         tune_seasons: list[int]) -> dict:
    """Refit only the two totals numbers on the corrected feature, 2016-2021 only.

    Same ratings (locked prior_regress / prior_plays_equiv) and the same 2-term form
    (base_total + points_per_combined_off * env). Reports leave-one-season-out MAE and
    the spread (SD) of projected totals before and after, all inside the tuning window.
    """
    assert max(tune_seasons) <= 2021, "totals sign fix may only be fit on 2016-2021"
    pre = precompute(pbp, schedules, tune_seasons)
    f = features(pre, locked["prior_regress"], locked["prior_plays_equiv"])
    # Rebuild the old (flipped) feature for the before/after comparison only.
    olds = []
    for (s, w), cur in pre["current"].items():
        r = shrink_to_prior(cur, pre["priors"][s], prior_plays_equiv=locked["prior_plays_equiv"],
                            prior_regress=locked["prior_regress"]).set_index("team")
        g = pre["games"][(pre["games"]["season"] == s) & (pre["games"]["week"] == w)][["game_id"]].copy()
        gg = pre["games"].set_index("game_id").loc[g["game_id"]]
        g["old_env"] = (gg["home_team"].map(r["shrunk_off_epa"]).values + gg["away_team"].map(r["shrunk_off_epa"]).values
                        - gg["home_team"].map(r["shrunk_def_epa"]).values - gg["away_team"].map(r["shrunk_def_epa"]).values)
        olds.append(g)
    f = f.merge(pd.concat(olds), on="game_id", how="left")

    def loso(col: str) -> np.ndarray:
        pred = np.full(len(f), np.nan)
        for hold in tune_seasons:
            tr, te = f["season"] != hold, f["season"] == hold
            c = _ols(np.column_stack([f.loc[tr, col], np.ones(tr.sum())]), f.loc[tr, "total_points"].values)
            pred[te.values] = np.column_stack([f.loc[te, col], np.ones(te.sum())]) @ c
        return pred

    def stats(pred: np.ndarray) -> dict:
        y = f["total_points"].values
        return {"loso_mae": float(np.mean(np.abs(pred - y))), "projected_total_sd": float(np.std(pred, ddof=1)),
                "slope_actual_on_projected": float(np.polyfit(pred, y, 1)[0])}

    X = np.column_stack([f["off_env"], np.ones(len(f))])
    ct = _ols(X, f["total_points"].values)
    resid = f["total_points"].values - X @ ct
    return {
        "fit_on_seasons": tune_seasons,
        "fitted_at": datetime.now(ZoneInfo("America/Chicago")).isoformat(),
        "feature": "home_off + away_off + home_def + away_def (shrunk EPA/play; def = EPA allowed)",
        "points_per_combined_off": float(ct[0]),
        "base_total": float(ct[1]),
        "total_sigma": float(np.std(resid, ddof=2)),
        "n_fit_games": int(len(f)),
        "tuning_window_before_after": {
            "before_flipped_sign": stats(loso("old_env")),
            "after_sign_fix": stats(loso("off_env")),
            "market_total_sd": float(f["total_line"].std()),
        },
    }


def with_signfix_totals(locked: dict) -> dict:
    """Locked margin coefficients + totals coefficients refit for the corrected sign."""
    if not TOTALS_SIGNFIX_PATH.exists():
        raise RuntimeError(
            f"{TOTALS_SIGNFIX_PATH} missing: run `nfl-lab refit-totals-signfix`. The locked totals "
            "coefficients were fit on the flipped defense sign and must not be used with the fixed feature.")
    fix = json.loads(TOTALS_SIGNFIX_PATH.read_text())
    out = dict(locked)
    for k in ("points_per_combined_off", "base_total", "total_sigma"):
        out[k] = fix[k]
    return out
