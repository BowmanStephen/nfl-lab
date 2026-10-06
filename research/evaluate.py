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
  * The candidate runs in its own freshly spawned worker process that is fed rows
    strictly in time order, so it never holds a later play, score or any betting
    line in memory. Inside the worker, file reads outside the Python install,
    network sockets, subprocesses and ctypes are refused.
  * After scoring, a scramble test starts a brand-new worker on data whose future
    (plays, scores, lines) is scrambled and replays to a checkpoint week. Its answers
    must match the main pass exactly. Because the worker is only fed past rows, this
    mainly proves the harness itself never forwards a later row (and that the
    candidate is deterministic); if a harness change ever leaked, it would fail.

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
import multiprocessing as mp
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
SCRAMBLE_CHECKPOINT = (2017, 6)

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
# Schedule columns known before kickoff (given for the target week). temp/wind are left
# out: nflverse records the game-time weather, not the pre-kickoff forecast (past games
# in history.schedule still carry them). home_qb_id/away_qb_id are the actual starters,
# the same stand-in for the announced starter that src/nfl_lab/qb_adjust.py was
# validated with; a late QB switch is the one known soft spot.
PREGAME_COLS = [
    "game_id", "season", "game_type", "week", "gameday", "weekday", "gametime", "away_team",
    "home_team", "location", "away_rest", "home_rest", "div_game", "roof", "surface", "away_qb_id", "home_qb_id", "away_qb_name", "home_qb_name", "away_coach",
    "home_coach", "referee", "stadium_id",
]
OUTCOME_COLS = ["away_score", "home_score", "result", "total", "overtime", "temp", "wind"]
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


def target_games(data: Data, season: int, week: int) -> pd.DataFrame:
    s = data.sched
    m = (s["season"] == season) & (s["week"] == week) & (s["game_type"] == "REG")
    return s.loc[m, [c for c in PREGAME_COLS if c in s.columns]].reset_index(drop=True)


# ---------------------------------------------------------------- sandbox
# The candidate runs in a separate, freshly spawned worker process. The worker only
# ever holds the rows it has been sent, and rows are sent strictly in time order:
# before week W it has received every play/score before week W and nothing later.
# Inside the worker, an audit hook additionally refuses file reads outside the Python
# install, network sockets, subprocesses and ctypes. (An in-process hook is a
# tripwire, not a hard OS sandbox; program.md forbids trying to get around it.)
_GUARD = {"on": False, "extra": set()}
_ALLOWED_PREFIXES = tuple(
    str(Path(p).resolve()) for p in
    {sys.prefix, sys.base_prefix, sys.exec_prefix, *site.getsitepackages(), "/usr/lib", "/usr/local/lib",
     "/usr/share/zoneinfo", "/etc/localtime", "/dev/null", "/dev/urandom", "/proc/self"}
)
_BLOCKED_EVENTS = ("socket.__new__", "socket.connect", "socket.bind", "socket.sendto", "socket.sendmsg",
                   "socket.getaddrinfo", "socket.gethostbyname", "subprocess.Popen", "os.system",
                   "os.posix_spawn", "os.exec", "os.fork", "os.forkpty", "urllib.Request",
                   "ctypes.dlopen", "ctypes.dlsym", "ctypes.call_function")


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
        if p in _GUARD["extra"] or (p.startswith(_ALLOWED_PREFIXES) and not p.startswith(str(REPO) + os.sep + "research")
                                    and not p.startswith(str(REPO) + os.sep + "data")):
            return
        raise PermissionError(f"candidate may not read files outside the data it is passed: {p}")
    if event in _BLOCKED_EVENTS:
        raise PermissionError(f"candidate may not use {event}")


sys.addaudithook(_audit)


def _tb_text(e: BaseException) -> str:
    """Traceback without reading source files (the worker cannot open them)."""
    out, tb = [], e.__traceback__
    while tb is not None:
        out.append(f"  {tb.tb_frame.f_code.co_filename}:{tb.tb_lineno} in {tb.tb_frame.f_code.co_name}")
        tb = tb.tb_next
    return "\n".join(out + [f"{type(e).__name__}: {e}"])


def _worker_main(conn, cand_path: str, name: str) -> None:
    import importlib.util as iu
    try:
        spec = iu.spec_from_file_location(name, cand_path)
        mod = iu.module_from_spec(spec)
        _GUARD["extra"] = {str(Path(cand_path).resolve())}
        _GUARD["on"] = True
        spec.loader.exec_module(mod)
        _GUARD["extra"] = set()
        if not callable(getattr(mod, "predict", None)):
            raise TypeError(f"{cand_path} must define predict(history, games)")
        conn.send(("ok", None))
    except BaseException as e:  # noqa: BLE001
        conn.send(("err", _tb_text(e)))
        return
    pbp = sch = None
    while True:
        msg = conn.recv()
        if msg[0] == "stop":
            return
        if msg[0] == "data":
            pbp = msg[1] if pbp is None else pd.concat([pbp, msg[1]], ignore_index=True)
            sch = msg[2] if sch is None else pd.concat([sch, msg[2]], ignore_index=True)
            continue
        _, season, week, games = msg
        try:
            # Shallow copies (copy-on-write): in-place edits by the candidate cannot alter
            # the history the worker keeps for later weeks.
            h = History(season, week, pbp.copy(deep=False), sch.copy(deep=False))
            out = pd.DataFrame(mod.predict(h, games))
            conn.send(("ok", out))
        except BaseException as e:  # noqa: BLE001
            conn.send(("err", _tb_text(e)))


class Worker:
    """One candidate in its own spawned process, fed data strictly in time order."""

    def __init__(self, cand_path: Path, name: str, data: Data):
        ctx = mp.get_context("spawn")
        self.conn, child = ctx.Pipe()
        self.proc = ctx.Process(target=_worker_main, args=(child, str(cand_path), name), daemon=True)
        self.proc.start()
        child.close()
        self.data, self.sent_p, self.sent_s, self.last_key = data, 0, 0, -1
        self._reply(f"loading {cand_path.name}")

    def _reply(self, what: str):
        try:
            status, payload = self.conn.recv()
        except (EOFError, OSError) as e:
            raise RuntimeError(f"candidate worker died while {what} (exit code {self.proc.exitcode})") from e
        if status != "ok":
            raise RuntimeError(f"candidate failed while {what}:\n{payload}")
        return payload

    def predict(self, season: int, week: int) -> pd.DataFrame:
        k = int(_key(season, week))
        if k <= self.last_key:
            raise RuntimeError("weeks must be requested in time order")
        self.last_key = k
        d = self.data
        n_p = int(np.searchsorted(d.pbp_key, k, side="left"))
        n_s = int(np.searchsorted(d.sched_key, k, side="left"))
        assert n_p == 0 or d.pbp_key[n_p - 1] < k
        pbp_new = d.pbp.iloc[self.sent_p:n_p]
        sch_new = d.sched.iloc[self.sent_s:n_s].drop(columns=LINE_COLS, errors="ignore")
        self.conn.send(("data", pbp_new, sch_new))
        self.sent_p, self.sent_s = n_p, n_s
        games = target_games(d, season, week)
        self.conn.send(("predict", season, week, games))
        out = self._reply(f"predicting {season} week {week}")
        need = {"game_id", "pred_margin", "pred_total"}
        if not need <= set(out.columns):
            raise ValueError(f"predict() must return columns {sorted(need)}")
        out = out[["game_id", "pred_margin", "pred_total"]].copy()
        if set(out["game_id"]) != set(games["game_id"]) or out["game_id"].duplicated().any():
            raise ValueError(f"{season} wk{week}: predict() must return exactly one row per game")
        if not np.isfinite(out[["pred_margin", "pred_total"]].to_numpy(dtype=float)).all():
            raise ValueError(f"{season} wk{week}: non-finite prediction")
        return out

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.conn.send(("stop",))
        self.proc.join(5)
        if self.proc.is_alive():
            self.proc.kill()


def _weeks(data: Data, season: int) -> list[int]:
    s = data.sched
    return sorted(int(w) for w in s.loc[(s["season"] == season) & (s["game_type"] == "REG"), "week"].unique())


def walkforward(cand_path: Path, seasons, data: Data, name: str = "candidate") -> pd.DataFrame:
    """Week-by-week predictions for every REG game of `seasons`, in time order."""
    seasons = _check_seasons(seasons)
    w = Worker(cand_path, name, data)
    try:
        rows = [w.predict(s, wk) for s in sorted(seasons) for wk in _weeks(data, s)]
    finally:
        w.close()
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
    """Same data, but every play, score and line at/after (season, week) is scrambled."""
    rng = np.random.default_rng(seed)
    k = int(_key(season, week))
    p, s = data.pbp.copy(), data.sched.copy()
    fp, fs = data.pbp_key >= k, data.sched_key >= k
    for c in ("epa", "success", "yards_gained", "qb_epa", "wp", "ep", "touchdown", "posteam_score", "defteam_score"):
        if c in p.columns:
            v = p.loc[fp, c].to_numpy(dtype=float, copy=True)
            p.loc[fp, c] = rng.permutation(v) * (1.0 if c in ("success", "touchdown") else -1.7)
    for c in ("home_score", "away_score", "spread_line", "total_line"):
        s.loc[fs, c] = rng.integers(0, 60, int(fs.sum())).astype(float)
    s.loc[fs, "result"] = s.loc[fs, "home_score"] - s.loc[fs, "away_score"]
    s.loc[fs, "total"] = s.loc[fs, "home_score"] + s.loc[fs, "away_score"]
    return Data(p, data.pbp_key, s, data.sched_key)


def scramble_test(cand_path: Path, data: Data, preds: pd.DataFrame, checkpoint: tuple[int, int],
                  name: str = "candidate") -> tuple[bool, str]:
    """A brand-new worker replays up to `checkpoint` on data whose future is scrambled.
    Its answers for that week must equal the main pass's answers exactly. With the
    time-ordered worker this checks the harness's own slicing and the candidate's
    determinism; the isolation itself is what keeps the future out of reach."""
    s, w = checkpoint
    base = preds[(preds["season"] == s) & (preds["week"] == w)].set_index("game_id")
    scr = _scrambled(data, s, w, seed=s * 100 + w)
    wk = Worker(cand_path, name, scr)
    try:
        for ww in _weeks(scr, s):  # warm the same weeks of the season as the main pass did
            if ww > w:
                break
            again = wk.predict(s, ww)
    finally:
        wk.close()
    again = again.set_index("game_id").loc[base.index]
    diff = float(np.max(np.abs(again[["pred_margin", "pred_total"]].to_numpy()
                               - base[["pred_margin", "pred_total"]].to_numpy())))
    if diff > 1e-6:
        return False, f"{s} wk{w} predictions moved by {diff:.4f} when later games were scrambled"
    return True, "ok"


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
    data = load()
    t_load = time.time() - t0
    preds = walkforward(CANDIDATE_PATH, TUNE, data)
    t_wf = time.time() - t0
    sc = score(preds)
    ok, why = scramble_test(CANDIDATE_PATH, data, preds, SCRAMBLE_CHECKPOINT)
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
