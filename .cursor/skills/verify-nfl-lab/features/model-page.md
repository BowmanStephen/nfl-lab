# Model page

`model.html` (“How it works”) shows team power ratings and the week’s model-vs-Vegas panel from published API JSON.

## Sub-features

- `model-ratings` populates `#ratings-h` / `#ratings-chart`.
- `model-record` shows `#record-h` and live slot copy.
- `model-nav` reachable via Primary nav `How it works`.

## How to get to it (user POV)

- Choose `How it works` in the Primary nav.
- Open `model.html` directly.

## Driving it with verify-nfl-lab

Preconditions:

- Site up; doctor passes.
- `public/api/model.json` and `public/api/teams.json` exist.

- **Open model.** Run `node .cursor/skills/verify-nfl-lab/helpers/browser_shot.mjs "$VERIFY_URL" /model.html "$VERIFY_RUN_DIR/artifacts/model-page"` **or** `.cursor/skills/verify-nfl-lab/helpers/render.sh model`.
- **Observe.** `ratings-h` text is `Team power` (or the live caption site.js sets); `record-h` / `live-label` are present and non-placeholder.
- **Proof.** `render-model/fields.json` or browser `snapshot.json` + PNG under the artifacts dir.

## Gotchas

- Charts are SVG drawn client-side; headless `render_site.mjs` proves text fields, not pixel-perfect chart geometry. Use Chrome when chart visibility matters.
- Drive `/model.html` on the Python static server (no Vercel cleanUrl rewrite).
