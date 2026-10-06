"""Nightly GATE check on 2020-2021. Run ONCE per night by the person or job that
started the loop, on the night's best candidate. THE LOOP AGENT MUST NEVER RUN THIS.

    uv run python research/gate.py                 # candidate = research/candidate.py at HEAD
    uv run python research/gate.py --candidate abc1234

It walks forward through 2020-2021 with the same harness as evaluate.py (same data
rules, same sandbox, same scramble test) for two models:
  * the candidate, and
  * the reference: the candidate from the most recent `pass` row in
    research/gate_log.tsv, or research/reference_main.py (main's live model form)
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
HEADER = ["date_ct", "candidate", "reference", "result", "note"]
GATE_SCRAMBLE = ((2020, 6), (2021, 12))


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


def module_at(rev: str, name: str, tmp: Path):
    path = tmp / f"{name}.py"
    path.write_text(git("show", f"{rev}:research/candidate.py") + "\n")
    return E.load_candidate(path, name)


def gate_score(mod, data) -> tuple[float, bool]:
    preds = E.walkforward(mod, E.GATE, data)
    ok, _ = E.scramble_test(mod, data, preds, GATE_SCRAMBLE)
    return E.score(preds)["score"], ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidate", default="HEAD", help="git revision whose research/candidate.py is gated")
    ap.add_argument("--force", action="store_true", help="allow a second gate run on the same date")
    a = ap.parse_args()

    now = datetime.now(ZoneInfo("America/Chicago"))
    today = now.strftime("%Y-%m-%d")
    if not a.force and any(r["date_ct"].startswith(today) for r in log_rows()):
        raise SystemExit(f"the gate already ran on {today}; it runs once per night")

    cand = git("rev-parse", "--short=7", a.candidate)
    passed = [r for r in log_rows() if r["result"] == "pass"]
    data = E._STATE["data"] = E.load()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        c_mod = module_at(cand, "gate_candidate", tmp)
        if passed:
            ref_label = passed[-1]["candidate"]
            r_mod = module_at(ref_label, "gate_reference", tmp)
        else:
            ref_label = "main-model-form"
            r_mod = E.load_candidate(E.RESEARCH / "reference_main.py", "gate_reference")
        c_score, c_ok = gate_score(c_mod, data)
        r_score, _ = gate_score(r_mod, data)

    if not c_ok:
        result, note = "fail", "scramble test failed"
    elif c_score <= r_score:
        result, note = "pass", "no worse than reference on 2020-2021"
    else:
        result, note = "fail", "worse than reference on 2020-2021"
    if not LOG.exists() or not LOG.read_text().strip():
        LOG.write_text("\t".join(HEADER) + "\n")
    with LOG.open("a") as fh:
        fh.write("\t".join([now.strftime("%Y-%m-%d %H:%M"), cand, ref_label, result, note]) + "\n")
    git("add", "research/gate_log.tsv")
    git("commit", "-q", "-m", f"research gate: {result} {cand} vs {ref_label}")
    print(f"GATE {result}: {cand} vs {ref_label} ({note})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
