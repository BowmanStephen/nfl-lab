"""2026 weeks 1-4 report card: what the frozen model would have said, walk-forward.

This is a backtest, not the live record. It reuses the exact holdout path in
`walkforward.py` (precompute -> features -> apply_coefs -> grade) with the
coefficients frozen in `output/backtest/locked_model.json` (fit on 2016-2021).

Causality:
  * Week W ratings use 2026 plays from weeks < W only (walkforward.precompute).
  * The 2026 prior uses 2023-2025 regular-season plays only.
  * nflverse closing lines are used to grade, never to fit.
  * `leak_check` re-runs the projections with every 2026 play from week W on
    replaced by garbage and asserts week W's numbers do not move.
"""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .config import OUTPUT_DIR, TEAM_NAMES
from .data_loader import load_pbp, load_schedules
from .ratings import shrink_to_prior
from .walkforward import BREAKEVEN, _record, apply_coefs, features, grade, precompute, with_signfix_totals

SEASON = 2026
WEEKS = [1, 2, 3, 4]
CT = ZoneInfo("America/Chicago")
SITE_JSON = OUTPUT_DIR.parent / "public" / "api" / "report_card.json"


def _locked() -> tuple[dict, dict]:
    bt = OUTPUT_DIR / "backtest"
    # Totals coefficients refit for the defense-sign fix (margin coefficients unchanged).
    locked = with_signfix_totals(json.loads((bt / "locked_model.json").read_text())["locked_model"])
    prereg = json.loads((bt / "preregistration.json").read_text())
    return locked, prereg


def project(pbp: pd.DataFrame, schedules: pd.DataFrame, locked: dict) -> tuple[pd.DataFrame, dict]:
    pre = precompute(pbp, schedules, [SEASON])
    f = apply_coefs(features(pre, locked["prior_regress"], locked["prior_plays_equiv"]), locked)
    return f[f["week"].isin(WEEKS)].copy(), pre


def leak_check(pbp: pd.DataFrame, schedules: pd.DataFrame, locked: dict, base: pd.DataFrame) -> list[dict]:
    """For each week W, replace every 2026 play in weeks >= W with random EPA and confirm week W is unchanged.

    Positive control: randomizing weeks < W must move week W, so the check can actually fail.
    """
    out = []
    rng = np.random.default_rng(20261005)
    key = ["game_id", "proj_margin", "proj_total", "home_rating", "away_rating"]
    for w in WEEKS:
        poisoned = pbp.copy()
        m = (poisoned["season"] == SEASON) & (poisoned["week"] >= w)
        poisoned.loc[m, "epa"] = rng.normal(0.0, 3.0, int(m.sum()))
        poisoned.loc[m, "success"] = (poisoned.loc[m, "epa"] > 0).astype(float)
        p, _ = project(poisoned, schedules, locked)
        a = base[base["week"] == w][key].sort_values("game_id").reset_index(drop=True)
        b = p[p["week"] == w][key].sort_values("game_id").reset_index(drop=True)
        same = len(a) == len(b) and bool((a["game_id"] == b["game_id"]).all()) and bool(
            np.allclose(a[key[1:]].values, b[key[1:]].values, atol=0, rtol=0))
        # Positive control: poisoning only earlier weeks SHOULD move week W (w >= 2).
        # Week 2 is skipped: with one game per team, the frozen opponent adjustment
        # attributes everything to the opponent and nets to zero, so week 2 runs on the prior.
        moved = None
        if w >= 3:
            ctl = pbp.copy()
            mc = (ctl["season"] == SEASON) & (ctl["week"] < w)
            ctl.loc[mc, "epa"] = rng.normal(0.0, 3.0, int(mc.sum()))
            ctl.loc[mc, "success"] = (ctl.loc[mc, "epa"] > 0).astype(float)
            pc, _ = project(ctl, schedules, locked)
            c = pc[pc["week"] == w][key].sort_values("game_id").reset_index(drop=True)
            moved = not bool(np.allclose(a[key[1:]].values, c[key[1:]].values))
        out.append({"week": w, "plays_poisoned": int(m.sum()), "week_unchanged_when_future_poisoned": same,
                    "week_moves_when_past_poisoned": moved, "games": int(len(a))})
    return out


def _name(t: str) -> str:
    return TEAM_NAMES.get(t, t)


def _short(t: str) -> str:
    return _name(t).split()[-1]


def _lesson(row: pd.Series, kind: str, pre: dict, locked: dict) -> dict:
    w = int(row["week"])
    r = pre["current"][(SEASON, w)].set_index("team")
    sr = shrink_to_prior(pre["current"][(SEASON, w)], pre["priors"][SEASON],
                         prior_plays_equiv=locked["prior_plays_equiv"],
                         prior_regress=locked["prior_regress"]).set_index("team")
    home, away = row["home_team"], row["away_team"]
    hs, as_ = int(row["home_score"]), int(row["away_score"])
    winner, loser = (home, away) if hs > as_ else (away, home)
    score = f"{_short(winner)} {max(hs, as_)}, {_short(loser)} {min(hs, as_)}"
    plays_before = int(r["off_plays"].sum() / 2) if "off_plays" in r else 0
    base = {
        "week": int(row["week"]), "game_id": row["game_id"],
        "matchup": f"{_name(away)} at {_name(home)}", "away": away, "home": home,
        "final": score, "kind": kind,
        "outcome": row["spread_outcome"] if kind == "spread" else row["total_outcome"],
        "home_off_epa_before": float(r.loc[home, "adj_off_epa"]) if home in r.index else None,
        "away_off_epa_before": float(r.loc[away, "adj_off_epa"]) if away in r.index else None,
        "home_def_epa_before": float(r.loc[home, "adj_def_epa"]) if home in r.index else None,
        "away_def_epa_before": float(r.loc[away, "adj_def_epa"]) if away in r.index else None,
        "weeks_of_2026_data": int(row["week"]) - 1,
        # What the model actually used: 2026 blended with the regressed 2023-2025 prior.
        "model_used": {t: {"off_epa": float(sr.loc[t, "shrunk_off_epa"]), "def_epa": float(sr.loc[t, "shrunk_def_epa"]),
                           "weight_2026_off": float(sr.loc[t, "shrink_weight_off"]),
                           "off_plays_2026": int(sr.loc[t, "off_plays"])} for t in (home, away)},
        "off_env": float(row["off_env"]),
    }
    if kind == "spread":
        base.update({
            "line_home_margin": float(row["spread_line"]), "model_home_margin": float(row["proj_margin"]),
            "actual_home_margin": int(row["margin"]), "edge": float(row["spread_edge"]),
            "pick": row["spread_pick"],
            "model_miss_pts": float(abs(row["proj_margin"] - row["margin"])),
            "line_miss_pts": float(abs(row["spread_line"] - row["margin"])),
        })
    else:
        base.update({
            "line_total": float(row["total_line"]), "model_total": float(row["proj_total"]),
            "actual_total": int(row["total_points"]), "edge": float(row["total_edge"]),
            "pick": row["total_pick"],
            "model_miss_pts": float(abs(row["proj_total"] - row["total_points"])),
            "line_miss_pts": float(abs(row["total_line"] - row["total_points"])),
        })
    return base


def build() -> dict:
    locked, prereg = _locked()
    smin, tmin = prereg["headline_rule"]["spread_edge_min"], prereg["headline_rule"]["total_edge_min"]
    schedules = load_schedules()
    pbp = load_pbp(range(SEASON - 3, SEASON + 1))
    f, pre = project(pbp, schedules, locked)
    g = grade(f, smin, tmin)

    sched = schedules[(schedules["season"] == SEASON) & (schedules["game_type"] == "REG")
                      & schedules["week"].isin(WEEKS)]
    pending = sched[sched["home_score"].isna()]

    sp = g[g["spread_bet_locked_rule"]]
    to = g[g["total_bet_locked_rule"]]
    weekly = []
    for w in WEEKS:
        gw = g[g["week"] == w]
        weekly.append({
            "week": w, "games_graded": int(len(gw)),
            "spread": _record(gw.loc[gw["spread_bet_locked_rule"], "spread_outcome"]),
            "total": _record(gw.loc[gw["total_bet_locked_rule"], "total_outcome"]),
        })

    # Lessons: biggest-edge spread hit, biggest-edge spread miss, biggest-edge total call that went the other way
    # (or the biggest total hit if every big total won). Chosen by edge size only, from code.
    lessons = []
    hits = sp[sp["spread_outcome"] == "win"].assign(a=lambda d: d["spread_edge"].abs()).sort_values("a", ascending=False)
    miss = sp[sp["spread_outcome"] == "loss"].assign(a=lambda d: d["spread_edge"].abs()).sort_values("a", ascending=False)
    tmiss = to[to["total_outcome"] == "loss"].assign(a=lambda d: d["total_edge"].abs()).sort_values("a", ascending=False)
    thit = to[to["total_outcome"] == "win"].assign(a=lambda d: d["total_edge"].abs()).sort_values("a", ascending=False)
    if len(hits):
        lessons.append({"label": "Biggest spread hit", **_lesson(hits.iloc[0], "spread", pre, locked)})
    if len(miss):
        lessons.append({"label": "Biggest spread miss", **_lesson(miss.iloc[0], "spread", pre, locked)})
    if len(tmiss) and (not len(thit) or tmiss.iloc[0]["a"] >= thit.iloc[0]["a"]):
        lessons.append({"label": "Biggest total miss", **_lesson(tmiss.iloc[0], "total", pre, locked)})
    elif len(thit):
        lessons.append({"label": "Biggest total hit", **_lesson(thit.iloc[0], "total", pre, locked)})

    leaks = leak_check(pbp, schedules, locked, f)
    if not all(x["week_unchanged_when_future_poisoned"] for x in leaks):
        raise RuntimeError(f"leak check failed: {leaks}")
    if not all(x["week_moves_when_past_poisoned"] in (None, True) for x in leaks):
        raise RuntimeError(f"positive control failed: {leaks}")

    hit_rate_su = float(((g["proj_margin"] > 0) == (g["margin"] > 0))[g["margin"] != 0].mean())
    out = {
        "kind": "backtest",
        "label": "What the model would have said. Not official picks.",
        "season": SEASON, "weeks": WEEKS,
        "generated_at": datetime.now(CT).isoformat(),
        "breakeven": BREAKEVEN,
        "rule": {"spread_edge_min": smin, "total_edge_min": tmin},
        "model": {"fit_on_seasons": locked["fit_on_seasons"], "prior_seasons": [SEASON - 3, SEASON - 2, SEASON - 1],
                  "qb_adjustment": False,
                  "note": "Same frozen model and path as the 2022-2025 holdout. The live card adds a starting-QB term; this backtest does not."},
        "lines": "nflverse closing spread_line / total_line (home margin, positive = home favored)",
        "games_graded": int(len(g)),
        "pending": [{"game_id": r.game_id, "matchup": f"{_name(r.away_team)} at {_name(r.home_team)}"} for r in pending.itertuples()],
        "spread": _record(sp["spread_outcome"]),
        "total": _record(to["total_outcome"]),
        "total_by_side": {side: _record(to.loc[to["total_pick"] == side, "total_outcome"]) for side in ["over", "under"]},
        "base_total": float(locked["base_total"]),
        "points_per_combined_off": float(locked["points_per_combined_off"]),
        "names": {t: _short(t) for t in TEAM_NAMES},
        # Underdog = the side the closing line has getting points.
        "spread_underdog_calls": _record(sp.loc[(sp["spread_pick"] == sp["home_team"]) == (sp["spread_line"] < 0), "spread_outcome"]),
        "spread_favorite_calls": _record(sp.loc[(sp["spread_pick"] == sp["home_team"]) != (sp["spread_line"] < 0), "spread_outcome"]),
        "proj_total_range": [float(g["proj_total"].min()), float(g["proj_total"].max())],
        "line_total_range": [float(g["total_line"].min()), float(g["total_line"].max())],
        "all_games_model_side": {"spread": _record(g["spread_outcome"]), "total": _record(g["total_outcome"])},
        "straight_up_accuracy": hit_rate_su,
        "model_mae_margin": float(np.mean(np.abs(g["proj_margin"] - g["margin"]))),
        "market_mae_margin": float(np.mean(np.abs(g["spread_line"] - g["margin"]))),
        "weekly": weekly,
        "lessons": lessons,
        "week2_note": "With one game per team, the frozen opponent adjustment nets every team to zero, so weeks 1 and 2 ran on the 2023-2025 prior alone. 2026 games start counting from week 3.",
        "leak_check": leaks,
        "games": json.loads(g[["game_id", "week", "away_team", "home_team", "away_score", "home_score",
                               "spread_line", "proj_margin", "spread_edge", "spread_pick", "spread_bet_locked_rule",
                               "spread_outcome", "total_line", "proj_total", "total_edge", "total_pick",
                               "total_bet_locked_rule", "total_outcome"]].sort_values(["week", "game_id"]).to_json(orient="records")),
    }
    SITE_JSON.write_text(json.dumps(out, indent=2, default=str))
    (OUTPUT_DIR / "report_card").mkdir(exist_ok=True)
    (OUTPUT_DIR / "report_card" / "2026_wk01_04.json").write_text(json.dumps(out, indent=2, default=str))
    return out


if __name__ == "__main__":
    o = build()
    print(json.dumps({k: o[k] for k in ["games_graded", "spread", "total", "weekly", "leak_check", "pending"]}, indent=1, default=str))
    for l in o["lessons"]:
        print(json.dumps(l, default=str))
