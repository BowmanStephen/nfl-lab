# This week's picks

Home (`/`, `index.html`) shows this week's locked-rule picks next to Vegas, after `site.js` loads `public/api/picks.json` and related API JSON.

## Sub-features

- `home-hydrate` replaces the loading title with the real week headline.
- `home-picks-list` fills `#games` with non-placeholder rows when picks exist.
- `home-nav` exposes Primary nav with `This week` current.

## How to get to it (user POV)

- Open the site root / `index.html`.
- Choose `This week` in the Primary nav (already current on home).
- Choose the brand mark `NFL/LAB` from another page.

## Driving it with verify-nfl-lab

Preconditions:

- `helpers/serve.sh start` succeeded; `VERIFY_URL` is set.
- `helpers/doctor.sh` passes with `VERIFY_URL`.
- Committed `public/api/picks.json` and `public/api/summary.json` exist.

- **Open home.** Load `${VERIFY_URL}/index.html`. Run `node .cursor/skills/verify-nfl-lab/helpers/browser_shot.mjs "$VERIFY_URL" /index.html "$VERIFY_RUN_DIR/artifacts/this-week-picks"`. Snapshot shows `mark` containing `NFL` and `loading: false`.
- **Headless cross-check.** Run `.cursor/skills/verify-nfl-lab/helpers/render.sh home`. `fields.json` includes `home-title` whose text is not the loading placeholder, and `picks-h` text `Our picks`.
- **Proof.** Artifacts under `$VERIFY_RUN_DIR/artifacts/this-week-picks/` (PNG + `snapshot.json`) and/or `…/artifacts/render-home/fields.json` show a hydrated title and the NFL/LAB brand.

## Gotchas

- Raw HTML still says `Loading this week's picks…` until `site.js` runs — a bare `curl` of HTML is not proof of hydration.
- `#games` starts with a placeholder `li`; count only `.game-row:not(.placeholder)`.
- Do not rewrite `public/api/picks.json` to invent rows for a green proof.
