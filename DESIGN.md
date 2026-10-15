# NFL Lab design system

The site's look comes from Stephen's Design Collection
(https://design-collection-sigma.vercel.app). It borrows that archive's
print-edition feel: warm paper, near-black ink, Georgia for display and
reading, a monospace face for labels and numbers, thin rules instead of boxes,
and a lot of white space. Everything uses system fonts, so there is nothing to
license or download.

## Which part of the archive this uses

The archive asks you to start from one project need. NFL Lab is a stats site
people read, so it follows two routes:

- **Dashboard or activity overview** (editions 019 Calm systems, 023 Database
  overview, 028 Usage across time). The archive's first step for this route is
  to decide what every metric, state and colour means before styling. That is
  the colour table below. From 019: compact status rows, and colour only for
  state. From 023: every chart keeps its own heading. From 028: the week-by-week
  dot grid keeps a legend you can see.
- **Reading continuity** (edition 024). Recaps, previews and the glossary share
  one calm reading column with the same rhythm on every page.

## What each colour means

Colour is only used for state. Identity, like model versus line or one team
versus another, is shown with solid ink versus an outline.

| Token | Means | Where |
| --- | --- | --- |
| `--ink` | the model, structure, anything above average | model dots and bars, rules, text |
| outline in `--line-mark` | the betting line | hollow rings and outlined bars |
| `--down` | below average | power bars to the left of zero |
| `--hit` | meets the pick rule, covered, above break-even | pick rows, win dots, records above 52.4% |
| `--miss` | lost, below break-even | loss squares, records below 52.4% |
| `--caution` | not the official record, or a caveat | backtest note, spent holdout, QB notes |

Colour never works alone. Wins are circles, losses are squares and pushes are
rings. Pick rows also say what the pick is, and every record prints its number
and says whether it is above or below break-even.

Dark mode swaps paper and ink and uses lighter versions of the same state
colours. Every text colour passes 4.5:1 and every chart mark passes 3:1 in both
modes.

## Type

Changed Oct 2026 with the approved home redesign (Apple Sports style, one row
per game). The palette above stays; the type is now one sans family.

- One family site-wide: `system-ui, -apple-system, "Segoe UI", Roboto,
  "Helvetica Neue", Arial, sans-serif`. No Georgia, no monospace. The old
  `--serif` and `--mono` tokens point at the same stack.
- Page titles (`h1`): 28px, bold. The home title retains its responsive
  `--fs-home-title` scale, `clamp(2rem, 5.5vw, 3.6rem)`, and 14ch measure.
  Section heads 20px.
- Game rows: team names 17px semibold.
- Body: 16px, line height 1.5.
- Captions, labels and footer text: 13.5px, never smaller.
- Every number uses `font-variant-numeric: tabular-nums`.
- Headings are sentence case and state the takeaway ("Week 5: who we think
  wins", "Week 5 is final"). No uppercase labels.
- Tokens: `--fs-h1` 28px, `--fs-call` 17px, `--fs-body` 16px, `--fs-small`
  13.5px, `--lh` 1.5, `--tap` 44px.
- Home disclosure rows show a muted Show details/Hide details label with a
  chevron. The short helper introduces spread picks and lean labels; row
  details explain the saved line's required result and the 3.5-point strong
  lean cutoff. These are display explanations; picks and rules stay locked.
- Up next matchup and saved-line text may wrap for larger text settings.
- Our model and our pick use one accent, `--accent` (= `--hit`). Vegas stays
  neutral grey (`--vegas` = `--muted` #55584f). `--line-mark` #7d7e74 (3.6:1)
  is for graphics only, never text. Right is green with "✓ Right", wrong is
  red with "✗ Wrong"; colour is never used alone.
- Home page states: pre, live, awaiting, final, stale, error, empty.
- Contrast on the paper background (computed, WCAG): ink 15.35, muted/Vegas
  6.31, right 6.32, wrong 5.69, caution 6.02. Dark mode: muted 7.51,
  right 9.89, wrong 7.87, caution 9.17.
- Tap targets are at least 44px tall. All times are Central Time.

## Layout

- One masthead on every page, with a thin ink rule under it. The primary nav is
  the five links from the home redesign (This week, Last week, Teams, How it
  works, Glossary), at least 44px tall. On a phone those links wrap onto a
  second line instead of scrolling sideways. The wordmark is a 44px target too.
- Section heads open with a full-width ink rule.
- Pick cards sit on a shelf grid that goes from one column on phones to three on
  wide screens.
- On wide screens, recap and preview entries put a monospace label in a left
  margin (kickoff time, or the entry number) and keep the text in a 40rem column.

## Charts

- Team power is HTML rows, not a scaled SVG, so labels stay readable on a phone.
- The weekly model-versus-line chart uses HTML dots on one margin scale: solid
  ink for the model and a hollow ring for the line.
- Win-rate and average-miss bars are square-cornered SVG with values inside the
  bars and a text label for screen readers.

## Decision log

**Pick card layout.** We compared three versions using the real locked TB at
DAL pick: a dossier card, a ledger row and a boxed box score. The dossier card
won. It keeps the pick as the biggest thing on the card, it has room for the
model-versus-line bars, snapshot time and QB notes, and it matches the
archive's edition cards. The ledger row had no room for the QB notes, and the
boxed version's border fought the thin-rule style and squeezed the kickoff time
on phones. One lesson from the comparison: uppercase mono is only for short
labels, never full sentences.

**Motion.** None beyond 150ms colour and underline changes on hover, and those
turn off with reduced motion. This is a reference site people come back to, so
animation would get old fast.

**Images.** None. Team logos are trademarked, and stock photos would be filler.

## Left on purpose (web interface guidelines audit)

- Headings stay in sentence case, and the copy stays as written. The site's
  plain-English voice wins over Title Case and copy rules.
- No `aria-live` region. Pages fill in from JSON right after the HTML loads.
  Announcing whole pick cards and charts as they arrive would be noise. If a
  load fails, the error message takes the place of the loading text (on the
  ledger, which has no loading slot, it takes the place of the page body).
- The skip link's target (`main`) gets no focus ring. Focus does move there, and
  a ring around the whole page body would look like an error.
- Labels and captions are at least 13.5px. They stay short and high-contrast.
  Navigation links stay a step larger (15px).
- No `translate="no"` on team codes. That would mean touching content markup on
  every page.


**Home Thursday hero.** The home page leads with locked picks and the honest record, not a lab dump. Primary nav keeps Picks, Model, 2026 so far, Week 5 previews, Week 4 recaps, and Glossary; Ledger, Teams, and Freshness sit in the footer. Each pick card puts the side and price largest, then a two-column Line vs Model call block (outline identity for the line, solid ink for the model), then the edge. No-picks stay below and quieter. Charts stay on `/model`.
