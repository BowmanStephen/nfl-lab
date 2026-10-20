# NFL Lab verification map

Maintained source for verifying user-facing NFL Lab behavior. Read this index before driving, then open the matching feature file.

## Baseline preconditions

- Repo root is the working directory.
- `export PATH="$HOME/.local/bin:$PATH"` and `uv sync` have succeeded.
- `VERIFY_RUN_DIR` points at a disposable run directory under `.cursor/skills/verify-nfl-lab/runs/`.
- For site features: `helpers/serve.sh start` has set `VERIFY_URL`, and `helpers/doctor.sh` passes with that URL.
- Never drive a static server or Chrome profile this run did not start.
- Never write to `output/live/` or `output/backtest/` during verification.

## Driving conventions

- Start every recipe from the baseline unless its preconditions say otherwise.
- Prefer element ids and ARIA landmark/nav names over CSS position.
- Treat helper invocations as literal.
- Site: `helpers/render.sh` (headless DOM) and/or `helpers/browser_shot.mjs` (Chrome).
- CLI: `helpers/cli.sh`.
- Cleanup stops the server; keep artifacts under `$VERIFY_RUN_DIR/artifacts/`.

## Proof and skip reporting

- Capture the user action and the resulting state.
- UI proof: hydrated text (not the “Loading…” placeholder) plus, for Chrome journeys, a PNG with the NFL/LAB mark visible.
- CLI proof: command, stdout, stderr, exit code.
- Record the feature ID and entry point on every artifact (`meta.txt`).
- If an entry point is unreachable, report failure with the unmet precondition — do not claim a different path verified it.

## Feature entry contract

Each feature file: H1, one paragraph, then exactly four H2s — `Sub-features`, `How to get to it (user POV)`, `Driving it with verify-nfl-lab`, `Gotchas`.

## Features

- [This week's picks](./this-week-picks.md) — home page hydrated picks and close games.
- [Track record](./track-record.md) — ledger page live health + spent holdout tiles.
- [Frozen holdout CLI](./frozen-holdout-cli.md) — `nfl-lab backtest` prints 48.8% / 51.0% without recomputing.
- [Model page](./model-page.md) — how-it-works ratings and record charts load from published API JSON.
