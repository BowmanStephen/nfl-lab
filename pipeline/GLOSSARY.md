# NFL Lab — plain-English glossary (site copy)

## EPA per play (Expected Points Added)
Every spot on the field is worth some number of points before the snap: 1st-and-10 at your own 25 is worth about +1; 1st-and-goal at the 1 is worth about +5.5. EPA is how much one play changed that number. An 8-yard gain on 3rd-and-7 is big plus EPA; the same 8 yards on 3rd-and-12 is minus, because you still have to punt.
**College cousin:** CFBD's PPA is the same idea with a college-trained model. Same math, different league.
**Good / bad:** Offense +0.10 per play is top-tier; −0.10 is bottom-tier. For defense, lower is better.

## Success rate
Did the play keep the offense on schedule? Counts as a success if it gains 40% of the needed yards on 1st down, 60% on 2nd, 100% on 3rd/4th (nflverse uses "EPA > 0", which lines up closely).
**Why both:** EPA rewards big plays; success rate rewards consistency. A team with high EPA but low success rate is living on explosives.

## Explosive play rate
Share of plays that gain 20+ yards passing or 10+ rushing. Explosives are swingy week to week, so the model leans on EPA and success rate more.

## Early-down EPA
EPA on 1st and 2nd down only. Third downs are noisy; early downs predict future scoring better.

## Pass rate over expected (PROE)
How often a team throws compared with what an average team would do in the same down, distance, score and clock. Positive = pass-happy.

## QB EPA + CPOE
EPA per dropback (what the QB's plays were worth) plus Completion % Over Expected (did he complete throws that were harder than average). Best single-number QB summary in public data.

## Opponent-adjusted rating
Raw EPA, corrected for who you played. Beating up three bad defenses gets marked down.

## The spread and "edge"
The spread is the market's guess at the final margin. The model's **edge** = model margin minus market margin. NFL Lab only makes a pick when the edge is **2+ points on the spread** or **3+ points on the total**.

## Break-even: 52.4%
Standard bets cost $110 to win $100. You need to win 52.4% just to break even. Below that loses money.

## Closing line value (CLV)
Did the line move toward our pick between when we picked and kickoff? Sharp bettors consistently get better numbers than the close. It's the earliest honest sign of a real edge, long before win-loss means anything.

## How the record is scored
- Picks are saved with a timestamp **before kickoff** and never edited.
- Graded only at the end of the regular season, on 100+ picks.
- It must pass **all three**: above 52.4% vs the spread, line moves our way on more than 55% of picks, and an average closing-line move in our favor.
- Past seasons 2022–2025 were graded once: 48.8% on spreads, 51.0% on totals. Not good enough yet, and the site says so.

## NFL equivalents of your college ratings
| College (CFBD) | NFL |
| --- | --- |
| PPA / WEPA | EPA per play (nflverse) |
| SRS | SRS (same idea, scoring margin adjusted for schedule) |
| Elo | nfelo / 538-style Elo |
| FPI | ESPN NFL FPI |
| SP+ | No public twin; DVOA (FTN) is closest, paid |
| Havoc, line yards | Mostly college-only; NFL uses pressure rate and rush yards over expected (NGS) |
