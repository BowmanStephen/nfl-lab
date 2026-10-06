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

- Display: Georgia 400, tight letter spacing, large sizes (`h1` up to 6.25rem).
- Reading: Georgia at 18px, set relative to the browser default so user font
  settings still apply.
- Labels: monospace, small caps, used for short labels only. Long sentences
  never go in uppercase mono.
- Numbers in data (the figures under each pick, tables, chart values):
  monospace with tabular figures so columns line up. Display numbers, like the
  pick itself or a season record, keep the Georgia display type.

## Layout

- One masthead on every page, with a thin ink rule under it. On phones the nine
  links become a 3 by 3 grid with 44px tap targets.
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
- Some monospace labels are 11–13.5px, under the 14px some guides suggest
  (navigation and status lines are 14–15px). They are short, high-contrast and
  never carry a whole sentence.
- No `translate="no"` on team codes. That would mean touching content markup on
  every page.
