"""Nightly GATE check on 2020-2021. Run ONCE per night by the person or job that
started the loop, on the night's best candidate. THE LOOP AGENT MUST NEVER RUN THIS.

    uv run python research/gate.py                 # candidate = research/candidate.py at HEAD
    uv run python research/gate.py --candidate abc1234

It walks forward through 2020-2021 with the same harness as evaluate.py (same data
rules, same sandbox, same scramble test) for two models:
  * the candidate, and
  * the reference: the candidate.py version (by git blob id) from the most recent
    `pass` row in research/gate_log.tsv, or research/reference_main.py (main's live model form)
    if nothing has passed yet.
PASS means the candidate's 2020-2021 score (margin MAE + total MAE) is no worse than
the reference's and its scramble test passed. Only a commit with a PASS row may be
proposed for merging into the live model, and that merge is still Stephen's call.

It appends one line to research/gate_log.tsv and commits it. No GATE numbers are
printed or logged, so the loop never learns anything from 2020-2021 but one bit a night.
Refuses to run twice on the same date (America/Chicago) unless --force.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate as E  # noqa: E402

LOG = E.RESEARCH / "gate_log.tsv"
HEADER = ["date_ct", "candidate", "candidate_blob", "reference", "result", "note"]
GATE_SCRAMBLE = (2020, 6)


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=E.REPO, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def log_rows() -> list[dict]:
    if not LOG.exists():
        return []
    lines = [l for l in LOG.read_text().splitlines() if l.strip()]
    return [dict(zip(HEADER, l.split("\t"))) for l in lines[1:]]


def file_from_blob(blob: str, name: str, tmp: Path) -> Path:
    """Write a candidate.py version, by git blob id (survives squash merges), to a temp file."""
    path = tmp / f"{name}.py"
    path.write_text(git("cat-file", "-p", blob) + "\n")
    return path


def gate_score(path: Path, name: str, data) -> tuple[float, bool]:
    preds = E.walkforward(path, E.GATE, data, name)
    ok, _ = E.scramble_test(path, data, preds, GATE_SCRAMBLE, name)
    return E.score(preds)["score"], ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidate", default="HEAD", help="git revision whose research/candidate.py is gated")
    ap.add_argument("--force", action="store_true", help="allow a second gate run on the same date")
    a = ap.parse_args()

    if git("diff", "--cached", "--name-only"):
        raise SystemExit("the git index has staged changes; commit or unstage them before running the gate")
    now = datetime.now(ZoneInfo("America/Chicago"))
    today = now.strftime("%Y-%m-%d")
    if not a.force and any(r["date_ct"].startswith(today) for r in log_rows()):
        raise SystemExit(f"the gate already ran on {today}; it runs once per night")

    # Label with the commit that last changed candidate.py, and pin the exact file by blob id.
    cand = git("log", "-1", "--format=%h", "--abbrev=7", a.candidate, "--", "research/candidate.py")
    blob = git("rev-parse", "--short=12", f"{a.candidate}:research/candidate.py")
    passed = [r for r in log_rows() if r["result"] == "pass"]
    data = E.load()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        c_path = file_from_blob(blob, "gate_candidate", tmp)
        if passed:
            ref_label = f"{passed[-1]['candidate']} (last pass)"
            r_path = file_from_blob(passed[-1]["candidate_blob"], "gate_reference", tmp)
        else:
            ref_label = "main-model-form"
            r_path = E.RESEARCH / "reference_main.py"
        c_score, c_ok = gate_score(c_path, "gate_candidate", data)
        r_score, _ = gate_score(r_path, "gate_reference", data)

    if not c_ok:
        result, note = "fail", "scramble test failed"
    elif c_score <= r_score:
        result, note = "pass", "no worse than reference on 2020-2021"
    else:
        result, note = "fail", "worse than reference on 2020-2021"
    if not LOG.exists() or not LOG.read_text().strip():
        LOG.write_text("\t".join(HEADER) + "\n")
    with LOG.open("a") as fh:
        fh.write("\t".join([now.strftime("%Y-%m-%d %H:%M"), cand, blob, ref_label, result, note]) + "\n")
    git("add", "research/gate_log.tsv")
    git("commit", "-q", "-m", f"research gate: {result} {cand} vs {ref_label}", "--", "research/gate_log.tsv")
    print(f"GATE {result}: {cand} vs {ref_label} ({note})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
