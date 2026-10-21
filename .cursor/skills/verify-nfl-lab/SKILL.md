---
name: verify-nfl-lab
description: "Drive NFL Lab the way a user does: static site in public/ plus read-only nfl-lab CLI. Use when proving picks/ledger/holdout/site behavior after a change — never to mutate live cards or retune."
---

# Verify NFL Lab

NFL Lab is a research ledger: a static site (`public/`) fed by `uv run nfl-lab`, with frozen 2022–2025 holdout numbers and immutable live pick cards. This skill proves user-visible behavior without rewriting picks or the spent ledger.

## Surfaces

| Surface | What the user touches | How we drive it |
|---|---|---|
| **Site (primary)** | `public/*.html` + `public/api/*.json` (also on Vercel) | Local static server + Chrome CDP shot / headless `render_site.mjs` |
| **CLI (primary)** | `uv run nfl-lab …` | `helpers/cli.sh` (read-only verbs only) |
| **Pytest (supporting)** | Invariants agents must not break | `uv run pytest` on named suites |

Do **not** drive `refresh`, `pick-card`, `line-snapshot`, `report-card`, `calibrate`, or `refit-totals-signfix` through this skill. Those write cards, APIs, or coefficients. AGENTS.md: never edit a committed pick or pick-time line; never regrade the holdout.

## Launch

From the repo root:

```bash
export PATH="$HOME/.local/bin:$PATH"
uv sync
export VERIFY_RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
export VERIFY_RUN_DIR=".cursor/skills/verify-nfl-lab/runs/${VERIFY_RUN_ID}"
mkdir -p "$VERIFY_RUN_DIR"

# Start an isolated site on 127.0.0.1:<ephemeral>
eval "$(.cursor/skills/verify-nfl-lab/helpers/serve.sh start | tee /dev/stderr | grep -E '^VERIFY_')"
# Sets VERIFY_RUN_DIR and VERIFY_URL in the printed lines — re-export them:
export VERIFY_RUN_DIR VERIFY_URL
# Prefer reading the files the helper wrote:
export VERIFY_URL="$(cat "${VERIFY_RUN_DIR}/serve.url")"
```

Ready means `curl -s -o /dev/null -w '%{http_code}' "${VERIFY_URL}/index.html"` is `200` and `#home-title` exists in the HTML. The helper already waits for that.

There is no long-lived CLI server. For CLI proofs, `uv sync` once, then each `helpers/cli.sh` invocation is its own process.

**Teardown** (does not delete evidence under `$VERIFY_RUN_DIR/artifacts/`):

```bash
.cursor/skills/verify-nfl-lab/helpers/serve.sh stop
```

## Doctor

Run first whenever anything looks off:

```bash
export PATH="$HOME/.local/bin:$PATH"
VERIFY_URL="${VERIFY_URL:-}" VERIFY_RUN_DIR="${VERIFY_RUN_DIR:-}" \
  .cursor/skills/verify-nfl-lab/helpers/doctor.sh
```

Doctor checks: `uv`/`node`/`python3`, `.venv`, `nfl-lab --help`, frozen files, `nfl-lab backtest` still prints **48.8%** / **51.0%**, and (when `VERIFY_URL` is set) HTTP 200 + brand markup. Refuse to drive if doctor fails.

## Drive

Read `.cursor/skills/verify-nfl-lab/features/README.md`, then the feature file for the journey. Conventions:

- Prefer element **ids** (`#home-title`, `#games`, `#spread-rec`, `#live-health`) and nav accessible names (`Primary`, `More pages`).
- Site proof: either headless render **or** real Chrome — both are valid; Chrome is required when claiming screenshot proof.
- CLI proof: only `backtest` and `--help` via `helpers/cli.sh`.
- Never mutate `output/live/*` or `output/backtest/*` to make a journey pass.

Helpers (all under `.cursor/skills/verify-nfl-lab/helpers/`, all executable):

```bash
./helpers/doctor.sh
./helpers/serve.sh start|stop|status
./helpers/cli.sh backtest
./helpers/render.sh home|ledger|model
node ./helpers/browser_shot.mjs "$VERIFY_URL" /index.html "$VERIFY_RUN_DIR/artifacts/home-browser"
```

## Evidence

Proof lives in `$VERIFY_RUN_DIR/artifacts/<name>/` and **survives** cleanup:

| Kind | Files |
|---|---|
| CLI | `stdout.txt`, `stderr.txt`, `meta.txt` (includes exit code) |
| Headless render | `fields.json`, `meta.txt` |
| Browser | `page.png`, `snapshot.json`, `meta.txt` |

Proof standards:

- Exercise the real user path (open the page / run the CLI verb a user would).
- Capture the action and the resulting state (hydrated title / holdout line), not only “server returned 200”.
- Side effects: for CLI, assert exit code and stdout contents; for site, assert DOM fields or screenshot text. Do not edit JSON fixtures to match.
- Mocks: none for site/CLI verification. Network-backed `refresh` is out of scope.

## Cleanup

```bash
.cursor/skills/verify-nfl-lab/helpers/serve.sh stop
```

Kill only the PID in `$VERIFY_RUN_DIR/serve.pid` (the helper does this). Never `pkill -f http.server`. Leave `$VERIFY_RUN_DIR/artifacts/` intact.

## Isolation

- Each run uses its own `VERIFY_RUN_DIR` and ephemeral loopback port.
- Do not drive a server you did not start.
- Two agents may run side by side; they must not share `VERIFY_RUN_DIR` or assume a fixed port.
- Chrome uses a disposable `--user-data-dir` under `/tmp` (removed after the shot).

## Safe pytest spot-check (optional)

When a change touches model/publish/immutability invariants:

```bash
uv run pytest tests/test_report_card_frozen.py tests/test_walkforward_no_peek.py tests/test_safe_to_fail.py tests/test_published_numbers.py -q
```

Pytest is supporting evidence, not a substitute for driving a mapped feature.
