"""One iteration of the research loop: score the committed candidate, keep or revert, log it.
READ-ONLY for the loop agent.

    git commit -m "exp: <idea>" -- research/candidate.py
    uv run python research/step.py "<one-line description>"
    uv run python research/step.py --simplification "<description>"   # change only deletes/simplifies code

Rules applied here (not by the agent):
  * HEAD must be one commit on top of the last logged state that changes ONLY
    research/candidate.py. The harness files must match origin/main.
  * Runs research/evaluate.py (TUNE 2016-2019 only) with a hard timeout.
  * keep    if tune_score beats the best kept score so far by more than MIN_GAIN
            points, or, with --simplification, is no worse than that best + MIN_GAIN
            (always measured against the best ever kept, so it cannot ratchet worse).
    discard otherwise, crash if the run fails or times out, leak if the scramble test fails.
    Anything but keep is reverted with `git reset --hard HEAD~1` (the experiment commit only).
  * Saves the experiment's diff to research/experiments/<commit>.diff, appends one row
    to research/results.tsv, and commits just those files.
The first run on an empty log is the baseline: HEAD is scored as is and kept.
GATE (2020-2021) is never run here.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RESEARCH = Path(__file__).resolve().parent
REPO = RESEARCH.parent
RESULTS = RESEARCH / "results.tsv"
RUN_LOG = RESEARCH / "run.log"
EXPERIMENTS = RESEARCH / "experiments"   # one .diff per experiment, kept or not
HEADER = ["commit", "time_ct", "tune_score", "margin_mae", "total_mae", "ats_hit_info", "total_hit_info",
          "status", "eval_s", "description"]
PROTECTED = ["research/evaluate.py", "research/step.py", "research/gate.py",
             "research/reference_main.py", "research/program.md"]
MIN_GAIN = 0.001    # points of tune_score
TIMEOUT_S = 600


def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def rows() -> list[dict]:
    if not RESULTS.exists():
        return []
    lines = [l for l in RESULTS.read_text().splitlines() if l.strip()]
    return [dict(zip(HEADER, l.split("\t"))) for l in lines[1:]]


def append(row: dict) -> None:
    if not RESULTS.exists() or not RESULTS.read_text().strip():
        RESULTS.write_text("\t".join(HEADER) + "\n")
    clean = {k: str(row.get(k, "")).replace("\t", " ").replace("\n", " ") for k in HEADER}
    with RESULTS.open("a") as fh:
        fh.write("\t".join(clean[k] for k in HEADER) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("description")
    ap.add_argument("--simplification", action="store_true")
    a = ap.parse_args()

    if git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("working tree has uncommitted changes: commit the candidate edit first")
    on_main = subprocess.run(["git", "cat-file", "-e", "origin/main:research/evaluate.py"],
                             cwd=REPO, capture_output=True).returncode == 0
    if on_main:
        changed = git("diff", "--name-only", "origin/main", "HEAD", "--", *PROTECTED)
        if changed:
            raise SystemExit(f"harness files differ from origin/main ({changed}); restore them")

    log = rows()
    kept = [r for r in log if r["status"] == "keep"]
    baseline = not kept
    if not baseline:
        files = git("diff", "--name-only", "HEAD~1", "HEAD").split()
        if files != ["research/candidate.py"]:
            raise SystemExit(f"HEAD must change only research/candidate.py (it changes {files})")
    commit = git("rev-parse", "--short=7", "HEAD")
    logged = ["research/results.tsv"]
    if not baseline:
        # Archive the experiment's diff so every row stays reproducible after a revert
        # or a squash merge (the commit itself may become unreachable).
        EXPERIMENTS.mkdir(exist_ok=True)
        (EXPERIMENTS / f"{commit}.diff").write_text(
            git("show", "--format=%H%n%s%n", "HEAD", "--", "research/candidate.py") + "\n")
        logged.append(f"research/experiments/{commit}.diff")

    t0 = time.time()
    try:
        with RUN_LOG.open("w") as fh:
            rc = subprocess.run([sys.executable, str(RESEARCH / "evaluate.py")], cwd=REPO,
                                stdout=fh, stderr=subprocess.STDOUT, timeout=TIMEOUT_S).returncode
    except subprocess.TimeoutExpired:
        rc = -9
    secs = time.time() - t0
    out = RUN_LOG.read_text()
    vals = dict(re.findall(r"^(\w+):\s+(\S+)", out, flags=re.M))

    row = {"commit": commit, "time_ct": datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d %H:%M"),
           "eval_s": f"{secs:.0f}", "description": a.description}
    if vals.get("scramble_test") == "FAIL":
        status = "leak"
    elif rc != 0 or "tune_score" not in vals:
        status = "crash"
    else:
        score = float(vals["tune_score"])
        best = min(float(r["tune_score"]) for r in kept) if kept else None
        if baseline:
            status = "keep"
        elif score < best - MIN_GAIN or (a.simplification and score <= best + MIN_GAIN):
            status = "keep"
        else:
            status = "discard"
        row.update({k: vals.get(k, "") for k in ("tune_score", "margin_mae", "total_mae",
                                                  "ats_hit_info", "total_hit_info")})
    if status in ("crash", "leak"):
        row.update({"tune_score": "0", "margin_mae": "0", "total_mae": "0"})
    row["status"] = status

    if baseline and status == "keep" and not log:
        append({"commit": "market", "time_ct": row["time_ct"], "tune_score": vals.get("market_score", ""),
                "margin_mae": vals.get("market_margin_mae", ""), "total_mae": vals.get("market_total_mae", ""),
                "status": "reference", "description": "closing lines on the same TUNE games (reference, not a target)"})
    if status != "keep":
        if baseline:
            raise SystemExit(f"baseline run failed ({status}); see {RUN_LOG}")
        git("reset", "--hard", "HEAD~1")
    append(row)
    git("add", *logged)
    git("commit", "-q", "-m", f"research log: {status} {commit} {a.description}"[:120], "--", *logged)

    best_now = min((r for r in rows() if r["status"] == "keep"), key=lambda r: float(r["tune_score"]))
    print(f"{status}: {commit} tune_score={row.get('tune_score')} (best {best_now['tune_score']} @ {best_now['commit']}) "
          f"in {secs:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
