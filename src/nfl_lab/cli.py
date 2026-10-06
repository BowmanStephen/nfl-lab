"""nfl-lab command line. One verb, a clear exit code."""
from __future__ import annotations

import argparse
import sys
import traceback

from .odds_espn import MissingLineError
from .refresh import print_backtest, run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nfl-lab",
        description="NFL Lab. Walk-forward margin model, live pick cards, ESPN DraftKings snapshots.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("refresh", help="Reload nflverse data, write ratings, teams, and the pick card.")
    sub.add_parser("pick-card", help="Snapshot this week's card before kickoff. Fails if a line is missing.")
    sub.add_parser("line-snapshot", help="Save pre-kickoff ESPN DraftKings lines for games inside the window.")
    sub.add_parser("backtest", help="Print the frozen 2022–2025 holdout. Does not recompute it.")
    sub.add_parser("refit-totals-signfix",
                   help="Refit the two totals numbers on 2016-2021 after the defense-sign fix.")
    sub.add_parser("report-card", help="Backtest 2026 weeks 1-4 walk-forward with the frozen model. Not official picks.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "backtest":
            print_backtest()
            return 0
        if args.cmd == "refit-totals-signfix":
            import json
            from .config import OUTPUT_DIR
            from .data_loader import load_pbp, load_schedules
            from .walkforward import TOTALS_SIGNFIX_PATH, refit_totals_signfix
            years = list(range(2013, 2022))  # 2013-15 only as priors for 2016
            locked = json.loads((OUTPUT_DIR / "backtest" / "locked_model.json").read_text())["locked_model"]
            out = refit_totals_signfix(load_pbp(years), load_schedules(years), locked, list(range(2016, 2022)))
            TOTALS_SIGNFIX_PATH.parent.mkdir(parents=True, exist_ok=True)
            TOTALS_SIGNFIX_PATH.write_text(json.dumps(out, indent=2) + "\n")
            print(json.dumps(out["tuning_window_before_after"], indent=2))
            return 0
        if args.cmd == "report-card":
            from .report_card import build
            out = build()
            print(f"spreads {out['spread']['wins']}-{out['spread']['losses']}-{out['spread']['pushes']}, "
                  f"totals {out['total']['wins']}-{out['total']['losses']}-{out['total']['pushes']}")
            return 0
        if args.cmd == "line-snapshot":
            run("line-snapshot")
            return 0
        run("refresh" if args.cmd == "refresh" else "pick-card")
        return 0
    except MissingLineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — exit 1 so Actions fails; keep the traceback
        traceback.print_exc()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
