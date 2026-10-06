"""Reference: the live model form on main, for research/gate.py only. READ-ONLY.

This is NOT the live pipeline (src/nfl_lab/ is untouched). It rebuilds main's model
form inside the research harness so gate.py has a fair yardstick on 2020-2021 until
some candidate passes the gate:
  * Margin: opponent-adjusted EPA rating difference (shrunk to a 3-season prior,
    prior_regress 0.3, 1200 plays) + home field + the starting-QB term.
  * Total: base + scale * (home_off + away_off - home_def - away_def), i.e. main's
    totals feature WITH its flipped defense sign, as live today.
  * Coefficients are refit walk-forward exactly like research/candidate.py, so the
    comparison is like for like (main's locked numbers were fit on 2016-2021 and
    would be in-sample on GATE).
Same predict(history, games) contract as candidate.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- settings
TRAIN_FIRST = 2013                 # first season of training rows (needs 2010-2012 priors)
EPA_REGRESS, EPA_PLAYS_EQUIV = 0.3, 1200
MARGIN_KG, MARGIN_RG = 32, 0.2     # scoring-margin level: prior games-equivalent, prior regress
TOTAL_KG, TOTAL_RG = 2, 1.0        # scoring levels used for totals
BUCKETS = [("wk1_4", 1, 4), ("wk5_8", 5, 8), ("wk9_plus", 9, 99)]
QB_K_SHRINK, QB_BACKUP_MAX_DB = 200, 150
MARGIN_COLS = ["rating_diff", "hfa_flag", "qb_diff"]
TOTAL_COLS = ["env_old", "one"]


# ---------------------------------------------------------------- EPA ratings
def offensive_plays(pbp: pd.DataFrame) -> pd.DataFrame:
    m = ((pbp["pass"] == 1) | (pbp["rush"] == 1)) & (pbp["qb_kneel"] != 1) & (pbp["qb_spike"] != 1)
    m &= pbp["epa"].notna() & pbp["posteam"].notna()
    return pbp.loc[m, ["season", "week", "posteam", "defteam", "epa"]]


def opponent_adjust(plays: pd.DataFrame, n_iter: int = 6) -> pd.DataFrame:
    df = plays[["posteam", "defteam", "epa"]].dropna()
    teams = sorted(set(df["posteam"]).union(df["defteam"]))
    adj_off = pd.Series(0.0, index=teams)
    adj_def = pd.Series(0.0, index=teams)
    for _ in range(n_iter):
        new_off = (df["epa"] - df["defteam"].map(adj_def)).groupby(df["posteam"]).mean()
        new_def = (df["epa"] - df["posteam"].map(adj_off)).groupby(df["defteam"]).mean()
        adj_off = (new_off - new_off.mean()).reindex(teams).fillna(0.0)
        adj_def = (new_def - new_def.mean()).reindex(teams).fillna(0.0)
    return pd.DataFrame({
        "off_plays": df.groupby("posteam").size().reindex(teams).fillna(0),
        "def_plays": df.groupby("defteam").size().reindex(teams).fillna(0),
        "adj_off_epa": adj_off, "adj_def_epa": adj_def,
    })


def prior_ratings(plays_by_season: dict, season: int) -> pd.DataFrame:
    """Opponent-adjusted EPA over seasons S-3..S-1 (REG), weighted 1:2:3."""
    frames = []
    for i, y in enumerate(range(season - 3, season)):
        if y in plays_by_season:
            frames.append(opponent_adjust(plays_by_season[y]).assign(w=i + 1))
    a = pd.concat(frames)
    w = a["w"]
    return pd.DataFrame({c: (a[c] * w).groupby(level=0).sum() / w.groupby(level=0).sum()
                         for c in ("adj_off_epa", "adj_def_epa")})


def shrunk_epa(current: pd.DataFrame | None, prior: pd.DataFrame) -> pd.DataFrame:
    teams = prior.index if current is None else prior.index.union(current.index)
    p = prior.reindex(teams).fillna(0.0) * EPA_REGRESS
    out = pd.DataFrame(index=teams)
    for side, n in (("off", "off_plays"), ("def", "def_plays")):
        if current is None:
            out[f"{side}"] = p[f"adj_{side}_epa"]
            continue
        c = current.reindex(teams)
        nn = c[n].fillna(0.0)
        wt = nn / (nn + EPA_PLAYS_EQUIV)
        out[f"{side}"] = wt * c[f"adj_{side}_epa"].fillna(0.0) + (1 - wt) * p[f"adj_{side}_epa"]
    return out


# ---------------------------------------------------------------- scoring levels
def team_games(schedule: pd.DataFrame) -> pd.DataFrame:
    s = schedule[(schedule["game_type"] == "REG") & schedule["home_score"].notna()]
    h = s[["season", "week", "home_team", "home_score", "away_score"]].set_axis(["season", "week", "team", "pf", "pa"], axis=1)
    a = s[["season", "week", "away_team", "away_score", "home_score"]].set_axis(["season", "week", "team", "pf", "pa"], axis=1)
    return pd.concat([h, a], ignore_index=True)


def prior_levels(tg: pd.DataFrame, season: int) -> tuple[pd.DataFrame, float]:
    rows = []
    for i, y in enumerate(range(season - 3, season)):
        t = tg[tg["season"] == y]
        if len(t):
            L = float(t["pf"].mean())
            rows.append((t.groupby("team")[["pf", "pa"]].mean() - L).assign(w=i + 1, L=L))
    a = pd.concat(rows)
    w = a["w"]
    prior = pd.DataFrame({c: (a[c] * w).groupby(level=0).sum() / w.groupby(level=0).sum() for c in ("pf", "pa")})
    yrs = a.drop_duplicates("w")
    return prior, float(np.average(yrs["L"], weights=yrs["w"]))


def levels(tg_season: pd.DataFrame, week: int, prior: pd.DataFrame, L: float, kg: float, rg: float) -> pd.DataFrame:
    cur = tg_season[tg_season["week"] < week].groupby("team").agg(pf=("pf", "sum"), pa=("pa", "sum"), n=("pf", "size"))
    teams = prior.index.union(cur.index)
    cur, pr = cur.reindex(teams).fillna(0.0), prior.reindex(teams).fillna(0.0)
    return pd.DataFrame({c: (cur[c] + kg * (L + rg * pr[c])) / (cur["n"] + kg) for c in ("pf", "pa")})


# ---------------------------------------------------------------- starting-QB term
def dropbacks(pbp: pd.DataFrame) -> pd.DataFrame:
    m = (pbp["season_type"] == "REG") & (pbp["qb_dropback"] == 1) & pbp["passer_id"].notna() & pbp["qb_epa"].notna()
    return pbp.loc[m, ["season", "week", "posteam", "passer_id", "qb_epa"]]


def qb_diff(db: pd.DataFrame, season: int, week: int, g: pd.DataFrame) -> pd.Series:
    w3 = db[db["season"].between(season - 3, season - 1)]
    per = w3.groupby(["season", "passer_id"])["qb_epa"].agg(["sum", "count"])
    low = per[per["count"] < QB_BACKUP_MAX_DB]
    base = float(low["sum"].sum() / low["count"].sum())
    win = db[db["season"].isin([season - 2, season - 1]) | ((db["season"] == season) & (db["week"] < week))]
    gq = win.groupby("passer_id")["qb_epa"].agg(["sum", "count"])
    vals = (gq["sum"] + QB_K_SHRINK * base) / (gq["count"] + QB_K_SHRINK)
    cur = db[(db["season"] == season) & (db["week"] < week)]
    if len(cur) == 0:
        cur = db[db["season"] == season - 1]
    ref = cur["passer_id"].map(vals).fillna(base).groupby(cur["posteam"]).mean()
    hd = g["home_qb_id"].map(vals).fillna(base) - g["home_team"].map(ref).fillna(base)
    ad = g["away_qb_id"].map(vals).fillna(base) - g["away_team"].map(ref).fillna(base)
    return hd - ad


# ---------------------------------------------------------------- per-week features
_SEASON: dict = {}   # season -> data built only from seasons < S
_FEAT: dict = {}     # (season, week) -> features built only from data before that week
_COEF: dict = {}     # season -> coefficients fit only on seasons < S


def _season_ctx(history, season: int) -> dict:
    """Priors for `season`; uses only completed seasons before it."""
    if season not in _SEASON:
        past = history.pbp[history.pbp["season"].between(season - 3, season - 1)]
        reg = past[past["season_type"] == "REG"]
        pbs = {y: offensive_plays(g) for y, g in reg.groupby("season")}
        tg = team_games(history.schedule[history.schedule["season"] < season])
        _SEASON[season] = {"epa_prior": prior_ratings(pbs, season), "lv": prior_levels(tg, season)}
    return _SEASON[season]


def _week_features(history, season: int, week: int, g: pd.DataFrame) -> pd.DataFrame:
    """Features for games `g` of (season, week). Every input is filtered to before that week."""
    key = (season, week)
    if key in _FEAT:
        return _FEAT[key]
    ctx = _season_ctx(history, season)
    pbp, sch = history.pbp, history.schedule
    cur_pbp = pbp[(pbp["season"] == season) & (pbp["week"] < week) & (pbp["season_type"] == "REG")]
    plays = offensive_plays(cur_pbp)
    r = shrunk_epa(opponent_adjust(plays) if len(plays) else None, ctx["epa_prior"])
    tg_s = team_games(sch[(sch["season"] == season) & (sch["week"] < week)])
    prior, L = ctx["lv"]
    lm = levels(tg_s, week, prior, L, MARGIN_KG, MARGIN_RG)
    lt = levels(tg_s, week, prior, L, TOTAL_KG, TOTAL_RG)
    db = dropbacks(pbp[pbp["season"].between(season - 3, season)
                       & ((pbp["season"] < season) | (pbp["week"] < week))])

    f = g[["game_id", "season", "week", "home_team", "away_team"]].copy()
    H, A = g["home_team"], g["away_team"]
    f["rating_diff"] = (H.map(r["off"]) - H.map(r["def"])) - (A.map(r["off"]) - A.map(r["def"]))
    f["env_fix"] = H.map(r["off"]) + A.map(r["off"]) + H.map(r["def"]) + A.map(r["def"])
    f["env_old"] = H.map(r["off"]) + A.map(r["off"]) - H.map(r["def"]) - A.map(r["def"])  # main's flipped sign
    f["ptdiff"] = (H.map(lm["pf"]) - H.map(lm["pa"])) - (A.map(lm["pf"]) - A.map(lm["pa"]))
    f["pts_env"] = H.map(lt["pf"]) + A.map(lt["pa"]) + A.map(lt["pf"]) + H.map(lt["pa"])
    f["qb_diff"] = qb_diff(db, season, week, g)
    f["hfa_flag"] = np.where(g["location"].eq("Neutral"), 0.0, 1.0)
    for b, lo, hi in BUCKETS:
        f[f"pt_{b}"] = f["ptdiff"] * float(lo <= week <= hi)
    f["one"] = 1.0
    f = f.fillna(0.0)
    _FEAT[key] = f
    return f


def _fit(history, season: int) -> dict:
    """OLS on every REG game from TRAIN_FIRST through season-1 (all already played)."""
    if season in _COEF:
        return _COEF[season]
    sch = history.schedule
    past = sch[(sch["season"] >= TRAIN_FIRST) & (sch["season"] < season) & (sch["game_type"] == "REG")]
    rows = []
    for (s, w), g in past.groupby(["season", "week"]):
        f = _week_features(history, int(s), int(w), g)
        rows.append(f.merge(g[["game_id", "home_score", "away_score"]], on="game_id"))
    tr = pd.concat(rows, ignore_index=True)
    ym = (tr["home_score"] - tr["away_score"]).to_numpy(float)
    yt = (tr["home_score"] + tr["away_score"]).to_numpy(float)
    cm = np.linalg.lstsq(tr[MARGIN_COLS].to_numpy(float), ym, rcond=None)[0]
    ct = np.linalg.lstsq(tr[TOTAL_COLS].to_numpy(float), yt, rcond=None)[0]
    _COEF[season] = {"margin": cm, "total": ct}
    return _COEF[season]


def predict(history, games: pd.DataFrame) -> pd.DataFrame:
    s, w = history.season, history.week
    coef = _fit(history, s)
    f = _week_features(history, s, w, games)
    return pd.DataFrame({
        "game_id": f["game_id"],
        "pred_margin": f[MARGIN_COLS].to_numpy(float) @ coef["margin"],
        "pred_total": f[TOTAL_COLS].to_numpy(float) @ coef["total"],
    })
