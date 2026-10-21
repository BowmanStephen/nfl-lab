#!/usr/bin/env bash
# Run a safe nfl-lab CLI verb and capture stdout/stderr/exit into the evidence dir.
# Usage: cli.sh <verb> [extra args...]
# Allowed verbs for verification: backtest, --help
# Forbidden by default: refresh, pick-card, line-snapshot, report-card, calibrate, refit-totals-signfix
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
PATH="${HOME}/.local/bin:${PATH}"
cd "$ROOT"

VERB="${1:-}"
shift || true

if [[ -z "$VERB" ]]; then
  echo "usage: cli.sh <backtest|--help> ..." >&2
  exit 2
fi

case "$VERB" in
  backtest|--help|-h|help) ;;
  refresh|pick-card|line-snapshot|report-card|calibrate|refit-totals-signfix)
    echo "cli.sh refuses '$VERB': it writes cards, APIs, or retunes. Use pytest + read-only verbs only." >&2
    exit 3
    ;;
  *)
    echo "cli.sh unknown verb '$VERB' (allowed: backtest, --help)" >&2
    exit 2
    ;;
esac

if [[ -z "${VERIFY_RUN_DIR:-}" ]]; then
  RUN_ID="${VERIFY_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
  VERIFY_RUN_DIR="${ROOT}/.cursor/skills/verify-nfl-lab/runs/${RUN_ID}"
fi
EVIDENCE="${VERIFY_EVIDENCE_DIR:-${VERIFY_RUN_DIR}/artifacts/cli-${VERB}}"
mkdir -p "$EVIDENCE"

OUT="${EVIDENCE}/stdout.txt"
ERR="${EVIDENCE}/stderr.txt"
META="${EVIDENCE}/meta.txt"

set +e
if [[ "$VERB" == "--help" || "$VERB" == "-h" || "$VERB" == "help" ]]; then
  uv run nfl-lab --help >"$OUT" 2>"$ERR"
  code=$?
else
  uv run nfl-lab "$VERB" "$@" >"$OUT" 2>"$ERR"
  code=$?
fi
set -e

{
  echo "verb=${VERB}"
  echo "exit_code=${code}"
  echo "cwd=${ROOT}"
  echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "stdout=${OUT}"
  echo "stderr=${ERR}"
} >"$META"

echo "exit_code=${code}"
echo "evidence=${EVIDENCE}"
cat "$OUT"
exit "$code"
