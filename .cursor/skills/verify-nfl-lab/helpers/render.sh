#!/usr/bin/env bash
# Headless DOM render of a published page via tests/render_site.mjs.
# Captures the JSON field map a visitor would see after site.js runs.
# Usage: render.sh <home|ledger|model> [nowIso]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
cd "$ROOT"

PAGE="${1:-home}"
NOW="${2:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

case "$PAGE" in
  home|ledger|model) ;;
  *) echo "usage: render.sh <home|ledger|model> [nowIso]" >&2; exit 2 ;;
esac

if [[ -z "${VERIFY_RUN_DIR:-}" ]]; then
  RUN_ID="${VERIFY_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
  VERIFY_RUN_DIR="${ROOT}/.cursor/skills/verify-nfl-lab/runs/${RUN_ID}"
fi
EVIDENCE="${VERIFY_EVIDENCE_DIR:-${VERIFY_RUN_DIR}/artifacts/render-${PAGE}}"
mkdir -p "$EVIDENCE"

OUT="${EVIDENCE}/fields.json"
node tests/render_site.mjs public "$NOW" "$PAGE" >"$OUT"

{
  echo "page=${PAGE}"
  echo "now=${NOW}"
  echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "fields=${OUT}"
} >"${EVIDENCE}/meta.txt"

echo "evidence=${EVIDENCE}"
# Print a short proof summary for the agent transcript
python3 - "$OUT" "$PAGE" <<'PY'
import json, sys
path, page = sys.argv[1:3]
data = json.load(open(path))[page]
# Key proof fields by page
keys = {
  "home": ["home-title", "picks-h", "games", "kicker"],
  "ledger": ["spread-rec", "total-rec", "live-health", "tr-tiles"],
  "model": ["ratings-h", "record-h", "live-label"],
}[page]
print(f"page={page} fields={len(data)}")
for k in keys:
    if k not in data:
        print(f"MISSING {k}")
        sys.exit(1)
    text = (data[k].get("text") or "")[:120]
    print(f"  {k}: {text!r}")
PY
