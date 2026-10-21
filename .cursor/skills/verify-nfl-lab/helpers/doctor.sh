#!/usr/bin/env bash
# Read-only health check for nfl-lab verification. Exit 0 only when the
# instance is worth driving.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
cd "$ROOT"

PATH="${HOME}/.local/bin:${PATH}"

fail() { echo "doctor FAIL: $*" >&2; exit 1; }
ok() { echo "doctor OK: $*"; }

command -v uv >/dev/null || fail "uv not on PATH (install: curl -LsSf https://astral.sh/uv/install.sh | sh)"
command -v node >/dev/null || fail "node not on PATH"
command -v python3 >/dev/null || fail "python3 not on PATH"

ok "uv=$(uv --version) node=$(node -v) python3=$(python3 --version 2>&1)"

[[ -d .venv ]] || fail ".venv missing; run: uv sync"
uv run nfl-lab --help >/dev/null || fail "uv run nfl-lab --help failed"
ok "nfl-lab CLI resolves"

for f in \
  output/backtest/preregistration.json \
  output/backtest/locked_model.json \
  public/api/baseline.json \
  public/api/picks.json \
  public/api/summary.json \
  public/index.html \
  public/ledger.html
do
  [[ -f "$f" ]] || fail "missing required file: $f"
done
ok "frozen + published artifacts present"

# Holdout numbers must stay 48.8% / 51.0% — never regrade.
backtest_out="$(uv run nfl-lab backtest 2>&1)"
echo "$backtest_out" | grep -q '48.8%' || fail "backtest missing 48.8% spreads line"
echo "$backtest_out" | grep -q '51.0%' || fail "backtest missing 51.0% totals line"
ok "frozen holdout prints 48.8% / 51.0%"

if [[ -n "${VERIFY_URL:-}" ]]; then
  code="$(curl -s -o /dev/null -w '%{http_code}' "${VERIFY_URL%/}/index.html" || true)"
  [[ "$code" == "200" ]] || fail "VERIFY_URL ${VERIFY_URL} returned HTTP ${code}"
  ok "site responds 200 at ${VERIFY_URL}"
  # site.js must hydrate home-title away from the loading placeholder
  html="$(curl -s "${VERIFY_URL%/}/index.html")"
  echo "$html" | grep -q 'id="home-title"' || fail "home missing #home-title"
  echo "$html" | grep -q 'NFL' || fail "home missing NFL brand mark"
  ok "home HTML has brand + #home-title"
fi

if [[ -f "${VERIFY_RUN_DIR:-}/serve.pid" ]]; then
  pid="$(cat "${VERIFY_RUN_DIR}/serve.pid")"
  kill -0 "$pid" 2>/dev/null || fail "serve.pid $pid is not a live process"
  ok "serve pid $pid is alive (owned by this run)"
fi

echo "doctor: ready"
exit 0
