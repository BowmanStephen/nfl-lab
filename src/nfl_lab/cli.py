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
    sub.add_parser("report-card", help="Backtest 2026 weeks 1-4 walk-forward with the frozen model. Not official picks.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "backtest":
            print_backtest()
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
