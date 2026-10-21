# Track record

Ledger (`ledger.html`) shows the 2026 live record tiles and the spent 2022–2025 holdout percentages a visitor reads under “For bettors”.

## Sub-features

- `ledger-live-health` fills `#live-health` from published summary/saved weeks.
- `ledger-holdout` shows `#spread-rec` / `#total-rec` matching the frozen baseline (~48.8% / ~51.0%).
- `ledger-entry` reachable from footer `Track record`.

## How to get to it (user POV)

- Choose `Track record` under footer nav `More pages`.
- Open `/ledger` (clean URL) or `ledger.html` directly.

## Driving it with verify-nfl-lab

Preconditions:

- Site up at `VERIFY_URL`; doctor passes.
- `public/api/baseline.json` present (committed).

- **Open ledger.** Run `node .cursor/skills/verify-nfl-lab/helpers/browser_shot.mjs "$VERIFY_URL" /ledger.html "$VERIFY_RUN_DIR/artifacts/track-record"`. Snapshot `h1` mentions the model / winner framing; `spread` / `live` fields are non-empty after hydration (script reads `#spread-rec` and `#live-health`).
- **Headless cross-check.** Run `.cursor/skills/verify-nfl-lab/helpers/render.sh ledger`. Require `spread-rec` and `total-rec` text to include `48.8` and `51.0` (or the formatted equivalents site.js prints from baseline), and `live-health` not equal to `…`.
- **Proof.** Artifact texts match the frozen holdout story; do not edit `baseline.json`.

## Gotchas

- The live 2026 record and the spent holdout are different blocks — prove both if claiming full ledger health.
- Totals may be paused in copy (`#totals-void-note`); that note is expected, not a failure.
- Clean URLs need the server to map `/ledger` → `ledger.html`; this helper serves files as-is, so drive `/ledger.html` unless you add rewrite scaffolding.
