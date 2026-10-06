"""Fixed evaluation for the NFL Lab overnight research loop. READ-ONLY for the loop agent.

    uv run python research/evaluate.py            # score research/candidate.py on TUNE
    uv run python research/evaluate.py --prepare  # (re)build the local data cache only

What it does
  * Loads play-by-play and schedules for 2010-2021 from a local cache
    (research/.cache/, built once from nflverse). Nothing after 2021 is ever
    downloaded, cached, or accepted: 2022-2025 was the spent holdout and 2026 is live.
  * Walks forward week by week through the TUNE seasons (2016-2019). For each week
    it hands the candidate ONLY what was known before that week's kickoffs:
    every play and every final score from earlier weeks/seasons, plus the week's
    matchups (teams, site, rest, roof, weather, listed starting QBs). No betting
    lines are ever passed in, and no outcome of the target week.
  * While the candidate runs, file reads outside the Python install, network
    access, and subprocesses are blocked.
  * After scoring, a scramble test re-asks the candidate for past weeks with every
    later play and score scrambled in memory. Any change in its answers = leakage.

Score (lower is better), on every REG-season TUNE game:

    tune_score = mean(|pred_margin - actual_margin|) + mean(|pred_total - actual_total|)

    margin = home_score - away_score, total = home_score + away_score, in points.

The market (closing spread_line / total_line) is printed on the same games as a
reference line. ATS and totals hit rates are printed for information only; they are
never part of the objective.

GATE seasons (2020-2021) are not scored here. research/gate.py uses this module's
walkforward() once per night; the loop agent must not run it.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import os
import site
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True

RESEARCH = Path(__file__).resolve().parent
REPO = RESEARCH.parent
CACHE = RESEARCH / ".cache"
CANDIDATE_PATH = RESEARCH / "candidate.py"

# ---------------------------------------------------------------- fixed split
FIRST_DATA_SEASON = 2010            # earliest season loaded (priors for 2013+ training rows)
MAX_SEASON = 2021                   # hard ceiling. 2022-2025 = spent holdout, 2026 = live.
TUNE = (2016, 2017, 2018, 2019)     # the loop sees and optimizes these
GATE = (2020, 2021)                 # gate.py only, once per night, pass/fail only
SCRAMBLE_CHECKPOINTS = ((2017, 6), (2019, 12))

TEAM_FIX = {"STL": "LA", "SD": "LAC", "OAK": "LV", "LAR": "LA", "WSH": "WAS"}

# Play-by-play columns the candidate may see. Nothing derived from betting lines
# (no spread_line / total_line / vegas_* columns).
PBP_COLS = [
    "game_id", "season", "week", "season_type", "posteam", "defteam", "home_team", "away_team",
    "play_type", "down", "ydstogo", "yardline_100", "qtr", "game_seconds_remaining",
    "half_seconds_remaining", "score_differential", "posteam_score", "defteam_score",
    "yards_gained", "epa", "ep", "wp", "success", "pass", "rush", "qb_dropback", "qb_kneel",
    "qb_spike", "qb_scramble", "sack", "interception", "fumble_lost", "touchdown", "first_down",
    "penalty", "penalty_yards", "air_yards", "yards_after_catch", "cpoe", "qb_epa", "xpass",
    "pass_oe", "passer_id", "passer", "rusher_id", "rusher", "receiver_id", "field_goal_result",
    "kick_distance", "extra_point_result", "special", "drive", "fixed_drive", "fixed_drive_result",
    "shotgun", "no_huddle",
]
# Schedule columns known before kickoff (given for the target week).
PREGAME_COLS = [
    "game_id", "season", "game_type", "week", "gameday", "weekday", "gametime", "away_team",
    "home_team", "location", "away_rest", "home_rest", "div_game", "roof", "surface", "temp",
    "wind", "away_qb_id", "home_qb_id", "away_qb_name", "home_qb_name", "away_coach",
    "home_coach", "referee", "stadium_id",
]
OUTCOME_COLS = ["away_score", "home_score", "result", "total", "overtime"]
LINE_COLS = ["spread_line", "total_line"]  # grading reference only, never passed in


def _check_seasons(seasons) -> tuple[int, ...]:
    seasons = tuple(int(s) for s in seasons)
    bad = [s for s in seasons if s > MAX_SEASON or s < FIRST_DATA_SEASON + 3]
    if bad:
        raise SystemExit(f"refusing seasons {bad}: research may only score 2013-{MAX_SEASON}")
    return seasons


# ---------------------------------------------------------------- data cache
def _norm(df: pd.DataFrame) -> pd.DataFrame:
    for c in ("posteam", "defteam", "home_team", "away_team"):
        if c in df.columns:
            df[c] = df[c].replace(TEAM_FIX)
    return df


def prepare(force: bool = False) -> None:
    """Download 2010-2021 only, trim to allowed columns, write research/.cache/."""
    import nflreadpy as nfl

    CACHE.mkdir(exist_ok=True)
    pbp_path, sch_path = CACHE / "pbp.parquet", CACHE / "schedules.parquet"
    if force or not pbp_path.exists():
        frames = []
        for y in range(FIRST_DATA_SEASON, MAX_SEASON + 1):
            d = nfl.load_pbp([y]).to_pandas()
            frames.append(d[[c for c in PBP_COLS if c in d.columns]])
            print(f"pbp {y}: {len(d)} plays", flush=True)
        pbp = _norm(pd.concat(frames, ignore_index=True))
        assert pbp["season"].max() <= MAX_SEASON
        pbp.to_parquet(pbp_path, index=False)
    if force or not sch_path.exists():
        s = nfl.load_schedules(list(range(FIRST_DATA_SEASON, MAX_SEASON + 1))).to_pandas()
        s = _norm(s[s["season"].between(FIRST_DATA_SEASON, MAX_SEASON)].copy())
        s = s[[c for c in PREGAME_COLS + OUTCOME_COLS + LINE_COLS if c in s.columns]]
        s.to_parquet(sch_path, index=False)


@dataclass
class Data:
    pbp: pd.DataFrame        # sorted by key
    pbp_key: np.ndarray
    sched: pd.DataFrame      # completed games, sorted by key
    sched_key: np.ndarray


def _key(season, week) -> np.ndarray:
    # POST weeks are numbered after REG weeks, so season*100+week orders every game.
    return np.asarray(season, dtype=np.int64) * 100 + np.asarray(week, dtype=np.int64)


def load() -> Data:
    if not (CACHE / "pbp.parquet").exists() or not (CACHE / "schedules.parquet").exists():
        prepare()
    pbp = pd.read_parquet(CACHE / "pbp.parquet")
    sch = pd.read_parquet(CACHE / "schedules.parquet")
    pbp = pbp[pbp["season"] <= MAX_SEASON]
    sch = sch[(sch["season"] <= MAX_SEASON) & sch["home_score"].notna()]
    assert pbp["season"].max() <= MAX_SEASON and sch["season"].max() <= MAX_SEASON
    pbp = pbp.assign(_k=_key(pbp["season"], pbp["week"])).sort_values("_k", kind="stable")
    sch = sch.assign(_k=_key(sch["season"], sch["week"])).sort_values(["_k", "game_id"], kind="stable")
    pk, sk = pbp.pop("_k").to_numpy(), sch.pop("_k").to_numpy()
    return Data(pbp.reset_index(drop=True), pk, sch.reset_index(drop=True), sk)


# ---------------------------------------------------------------- what the candidate gets
@dataclass(frozen=True)
class History:
    """Everything known before kickoff of `season`/`week`."""
    season: int
    week: int
    pbp: pd.DataFrame        # all plays (REG and POST) from earlier weeks and seasons, 2010+
    schedule: pd.DataFrame   # all completed games before this week, with final scores, no lines


def history(data: Data, season: int, week: int) -> History:
    k = int(_key(season, week))
    n_p = int(np.searchsorted(data.pbp_key, k, side="left"))
    n_s = int(np.searchsorted(data.sched_key, k, side="left"))
    sched = data.sched.iloc[:n_s].drop(columns=LINE_COLS, errors="ignore")
    h = History(season, week, data.pbp.iloc[:n_p], sched)
    assert len(h.pbp) == 0 or int(_key(h.pbp["season"].iloc[-1], h.pbp["week"].iloc[-1])) < k
    return h


def target_games(data: Data, season: int, week: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    s = data.sched
    m = (s["season"] == season) & (s["week"] == week) & (s["game_type"] == "REG")
    full = s.loc[m]
    public = full[[c for c in PREGAME_COLS if c in full.columns]].reset_index(drop=True)
    return public, full


# ---------------------------------------------------------------- sandbox for candidate calls
_GUARD = {"on": False, "extra": set()}
_ALLOWED_PREFIXES = tuple(
    str(Path(p).resolve()) for p in
    {sys.prefix, sys.base_prefix, sys.exec_prefix, *site.getsitepackages(), "/usr/lib", "/usr/local/lib",
     "/usr/share/zoneinfo", "/etc/localtime", "/dev/null", "/dev/urandom", "/proc/self"}
)
_BLOCKED_EVENTS = ("socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system",
                   "os.posix_spawn", "os.exec", "os.fork", "urllib.Request")


def _audit(event: str, args) -> None:
    if not _GUARD["on"]:
        return
    if event == "open":
        path = args[0]
        if isinstance(path, int):
            return
        try:
            p = str(Path(os.fsdecode(path)).resolve())
        except Exception:
            return
        if p in _GUARD["extra"] or (p.startswith(_ALLOWED_PREFIXES) and not p.startswith(str(CACHE))):
            return
        raise PermissionError(f"candidate may not read files outside the data it is passed: {p}")
    if event in _BLOCKED_EVENTS:
        raise PermissionError(f"candidate may not use {event}")


sys.addaudithook(_audit)


@contextlib.contextmanager
def guarded(extra_paths=()):
    _GUARD["extra"] = {str(Path(p).resolve()) for p in extra_paths}
    _GUARD["on"] = True
    try:
        yield
    finally:
        _GUARD["on"] = False
        _GUARD["extra"] = set()


def load_candidate(path: Path = CANDIDATE_PATH, name: str = "candidate"):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    with guarded([path]):
        spec.loader.exec_module(mod)
    if not callable(getattr(mod, "predict", None)):
        raise SystemExit(f"{path} must define predict(history, games)")
    return mod


def _call(mod, data: Data, season: int, week: int) -> pd.DataFrame:
    games, _ = target_games(data, season, week)
    h = history(data, season, week)
    with guarded():
        out = mod.predict(h, games.copy())
    out = pd.DataFrame(out)
    need = {"game_id", "pred_margin", "pred_total"}
    if not need <= set(out.columns):
        raise ValueError(f"predict() must return columns {sorted(need)}")
    out = out[["game_id", "pred_margin", "pred_total"]].copy()
    if set(out["game_id"]) != set(games["game_id"]) or out["game_id"].duplicated().any():
        raise ValueError(f"{season} wk{week}: predict() must return exactly one row per game")
    vals = out[["pred_margin", "pred_total"]].to_numpy(dtype=float)
    if not np.isfinite(vals).all():
        raise ValueError(f"{season} wk{week}: non-finite prediction")
    return out


def walkforward(mod, seasons, data: Data | None = None) -> pd.DataFrame:
    """Week-by-week predictions for every REG game of `seasons`, in time order."""
    seasons = _check_seasons(seasons)
    data = data or load()
    rows = []
    for s in sorted(seasons):
        weeks = sorted(data.sched.loc[(data.sched["season"] == s) & (data.sched["game_type"] == "REG"), "week"].unique())
        for w in weeks:
            rows.append(_call(mod, data, s, int(w)))
    pred = pd.concat(rows, ignore_index=True)
    g = data.sched[data.sched["season"].isin(seasons) & (data.sched["game_type"] == "REG")]
    g = g[["game_id", "season", "week", "home_score", "away_score", "spread_line", "total_line"]]
    out = g.merge(pred, on="game_id", how="left", validate="one_to_one")
    out["margin"] = out["home_score"] - out["away_score"]
    out["total_points"] = out["home_score"] + out["away_score"]
    return out


# ---------------------------------------------------------------- scoring
def score(df: pd.DataFrame) -> dict:
    mm = float(np.mean(np.abs(df["pred_margin"] - df["margin"])))
    mt = float(np.mean(np.abs(df["pred_total"] - df["total_points"])))
    ln = df.dropna(subset=LINE_COLS)
    kmm = float(np.mean(np.abs(ln["spread_line"] - ln["margin"])))
    kmt = float(np.mean(np.abs(ln["total_line"] - ln["total_points"])))

    def hit(edge, res):  # res = actual - line; info only
        m = (edge != 0) & (res != 0)
        return float(((edge[m] > 0) == (res[m] > 0)).mean()), int(m.sum())

    ats, n_ats = hit(ln["pred_margin"] - ln["spread_line"], ln["margin"] - ln["spread_line"])
    tot, n_tot = hit(ln["pred_total"] - ln["total_line"], ln["total_points"] - ln["total_line"])
    return {"score": mm + mt, "margin_mae": mm, "total_mae": mt, "n_games": int(len(df)),
            "market_score": kmm + kmt, "market_margin_mae": kmm, "market_total_mae": kmt,
            "n_market_games": int(len(ln)), "ats_hit_info": ats, "ats_n": n_ats,
            "total_hit_info": tot, "total_n": n_tot}


# ---------------------------------------------------------------- leakage scramble test
def _scrambled(data: Data, season: int, week: int, seed: int) -> Data:
    """Same data, but every play and score at/after (season, week) is scrambled."""
    rng = np.random.default_rng(seed)
    k = int(_key(season, week))
    p, s = data.pbp.copy(), data.sched.copy()
    fp, fs = data.pbp_key >= k, data.sched_key >= k
    for c in ("epa", "success", "yards_gained", "qb_epa", "wp", "ep", "touchdown", "posteam_score", "defteam_score"):
        if c in p.columns:
            v = p.loc[fp, c].to_numpy(copy=True)
            p.loc[fp, c] = rng.permutation(v) * (1 if c == "success" or c == "touchdown" else -1.7)
    for c in ("home_score", "away_score"):
        s.loc[fs, c] = rng.integers(0, 60, int(fs.sum())).astype(float)
    s.loc[fs, "result"] = s.loc[fs, "home_score"] - s.loc[fs, "away_score"]
    s.loc[fs, "total"] = s.loc[fs, "home_score"] + s.loc[fs, "away_score"]
    return Data(p, data.pbp_key, s, data.sched_key)


def scramble_test(mod, data: Data, preds: pd.DataFrame, checkpoints=SCRAMBLE_CHECKPOINTS) -> tuple[bool, str]:
    """Re-predict checkpoint weeks with the future scrambled. Answers must not move."""
    for i, (s, w) in enumerate(checkpoints):
        if s not in set(preds["season"]):
            continue
        base = preds[(preds["season"] == s) & (preds["week"] == w)].set_index("game_id")
        _STATE["data"] = _scrambled(data, s, w, seed=i)
        try:
            again = _call(mod, _STATE["data"], s, w).set_index("game_id").loc[base.index]
        finally:
            _STATE["data"] = data
        diff = float(np.max(np.abs(again[["pred_margin", "pred_total"]].to_numpy()
                                   - base[["pred_margin", "pred_total"]].to_numpy())))
        if diff > 1e-6:
            return False, f"{s} wk{w} predictions moved by {diff:.4f} when later games were scrambled"
    return True, "ok"


_STATE: dict = {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prepare", action="store_true", help="build research/.cache and exit")
    ap.add_argument("--force", action="store_true", help="with --prepare: re-download")
    a = ap.parse_args()
    if a.prepare:
        prepare(force=a.force)
        print("cache ready:", CACHE)
        return 0

    t0 = time.time()
    data = _STATE["data"] = load()
    t_load = time.time() - t0
    mod = load_candidate()
    preds = walkforward(mod, TUNE, data)
    t_wf = time.time() - t0
    sc = score(preds)
    ok, why = scramble_test(mod, data, preds)
    print("---")
    print(f"tune_score:        {sc['score']:.4f}")
    print(f"margin_mae:        {sc['margin_mae']:.4f}")
    print(f"total_mae:         {sc['total_mae']:.4f}")
    print(f"n_games:           {sc['n_games']}")
    print(f"market_score:      {sc['market_score']:.4f}   (reference only: closing lines, same games)")
    print(f"market_margin_mae: {sc['market_margin_mae']:.4f}")
    print(f"market_total_mae:  {sc['market_total_mae']:.4f}")
    print(f"ats_hit_info:      {sc['ats_hit_info']:.4f}   (n={sc['ats_n']}, information only)")
    print(f"total_hit_info:    {sc['total_hit_info']:.4f}   (n={sc['total_n']}, information only)")
    print(f"scramble_test:     {'pass' if ok else 'FAIL'}   ({why})")
    print(f"load_seconds:      {t_load:.1f}")
    print(f"eval_seconds:      {time.time() - t0:.1f}   (walk-forward done at {t_wf:.1f})")
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
