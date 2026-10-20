# Frozen holdout CLI

`uv run nfl-lab backtest` prints the spent 2022–2025 holdout. It must not recompute or rewrite ledger files. Users (and agents) use this to confirm the historical bar is unchanged.

## Sub-features

- `backtest-print` exits 0 and prints spreads **48.8%** and totals **51.0%**.
- `backtest-read-only` leaves `output/backtest/` untouched.

## How to get to it (user POV)

- Run `uv run nfl-lab backtest` from the repo root (documented in README).

## Driving it with verify-nfl-lab

Preconditions:

- `uv sync` done; doctor passes (URL optional).
- Record mtimes or checksums of `output/backtest/preregistration.json` and `output/backtest/locked_model.json` before the run if claiming read-only proof.

- **Print holdout.** Run `.cursor/skills/verify-nfl-lab/helpers/cli.sh backtest`. Exit code `0`. Stdout contains `48.8%` and `51.0%` and the phrase that live proof is 2026 from week 5.
- **Confirm immutability.** Re-hash the two backtest JSON files; they must match the pre-run hashes.
- **Proof.** `$VERIFY_RUN_DIR/artifacts/cli-backtest/stdout.txt` plus `meta.txt` with `exit_code=0`.

## Gotchas

- `helpers/cli.sh` refuses `refresh` / `pick-card` / etc. Do not bypass it to “verify” those verbs here.
- Formatting uses a special dash in `2022–2025`; grep for `48.8%` / `51.0%`, not a brittle full-line match.
- Never “fix” a failing percentage by editing the ledger.
