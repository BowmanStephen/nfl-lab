# Week 5 previews, in plain English

**Updated Wed Oct 7, 6:30 PM CT.** DraftKings spreads and totals are from ESPN’s public scoreboard. Starting quarterbacks are from ESPN’s depth charts and game injury reports, checked against the repo’s schedule and depth chart.

**Honest note up top.** The model has not beaten the market in its holdout test (2022–2025 holdout: **48.8%** ATS, **51.0%** on totals, below the **52.4%** break-even at −110). That test only counted edges of 2+ points on the side or 3+ on the total.

This file is a Wednesday refresh of the week-5 previews. The official week-5 card is the Monday Oct 5 lock in `output/live/2026-week-05.json`. These leans do not change it. Not bets, not advice. The rows for this refresh are `pipeline/previews/2026_week5_preview_lines_wed.csv` and `pipeline/previews/2026_week5_preview_lines_wed.json`. The Monday file `pipeline/previews/2026_wk05_preview_lines.csv` stays as history. Kansas City and Carolina are on bye. Fifteen games, Thursday through Monday.

**How to read a card.** Kickoff is Central Time. “Market” is the current DraftKings line on ESPN, pulled **2026-10-07 18:30 CT**. “Model” is the QB-adjusted projected margin (positive means the home team wins by that many) and the projected total. A **preview lean** appears only when the locked rule fires: spread edge = |model spread − market spread| ≥ 2 points, or total edge ≥ 3 points. Every model figure is from the NFL Lab code on main (nflverse through 2026 week 4, walk-forward ratings, the locked starting-QB adjustment).

---

### Tampa Bay Buccaneers at Dallas Cowboys

**Thu Oct 8, 7:15 PM CT.** Market: **DAL -8.5**, total **47.5**. Model: **DAL by 3.5**, projected total **45.6**.

Dallas should win a closer game than the market price. The Cowboys’ offense has been excellent (about **+0.20 EPA/play**) and the defense has been leaky (**+0.19** allowed — higher is worse). Tampa’s offense has been bad (**-0.16**). With Baker Mayfield out, the model only makes Dallas a **3.5**-point favorite, so Tampa Bay getting **8.5** clears the 2-point line.

Baker Mayfield is **Out** (dislocated thumb; ESPN return date Oct 25). The depth chart still lists him as QB1, and the nflverse week-5 report leaves his status blank even though he did not practice. The schedule lists **Jalon Daniels**, and ESPN’s next available quarterback is Daniels, so this projection reruns the QB adjustment with Daniels. Dak Prescott starts for Dallas.

**Newcomer tip — EPA/play:** every snap has a “fair” point value before the ball is snapped. EPA is how much the play moved that number. Dallas’s **+0.20** offense means it is gaining about two-tenths of a point per snap on average.

**Preview lean (spread):** TB +8.5 — edge 5.0 pts

---

### Philadelphia Eagles at Jacksonville Jaguars

**Sun Oct 11, 8:30 AM CT.** Market: **JAX -7**, total **42.5**. Model: **JAX by 5.6**, projected total **47.0**.

Jacksonville should win. The Jaguars rate as one of the better teams so far (**+0.046** opponent-adjusted) and the model has them by about **5.6** at home with Trevor Lawrence. Philadelphia is near average (**-0.005**). The side is close to the market’s **7**, so there is no spread lean. The total is the gap: the model wants more points than **42.5**.

Jalen Hurts and Trevor Lawrence are the depth-chart starters, and neither is on the ESPN injury report.

**Newcomer tip — opponent-adjusted rating:** raw stats get credit, or blame, taken away for soft or tough schedules. JAX at **+0.046** is near the top of this slate; PHI at **-0.005** is the middle.

**Preview lean (total):** OVER 42.5 — edge 4.5 pts

---

### Chicago Bears at Green Bay Packers

**Sun Oct 11, 12:00 PM CT.** Market: **CHI -2.5**, total **45.5**. Model: **CHI by 3.1**, projected total **46.8**.

Chicago should win by about a field goal. The Bears rate better than Green Bay (**+0.036** vs **-0.004**), and with Caleb Williams starting the model has Chicago by **3.1**. The market already has the Bears **-2.5**. That gap is about half a point, and the totals are close too, so the locked rule stays quiet.

The nflverse schedule still lists Tyson Bagent. The latest depth chart has Caleb Williams at QB1, and the ESPN injury report for this game does not list him. This projection uses Williams against Jordan Love.

**Newcomer tip — success rate:** the share of plays that stay on schedule (enough yards for the down). Chicago’s offense succeeds on about **49%** of snaps; Green Bay’s on about **39%**.

**No preview lean** under the locked rule (need 2+ points on the spread or 3+ on the total).

---

### Cincinnati Bengals at Miami Dolphins

**Sun Oct 11, 12:00 PM CT.** Market: **CIN -6.5**, total **42.5**. Model: **CIN by 1.4**, projected total **45.5**.

Cincinnati should win a close game, not a touchdown game. The market has the Bengals **-6.5** on the road. The model has them by about **1.4**, because Miami’s home edge does not cover the gap in the team ratings. Joe Burrow against Malik Willis is a real talent gap, and the locked rule still wants Miami getting **6.5** and a higher total.

**Newcomer tip — the spread:** **-6.5** means Cincinnati is priced to win by a touchdown, short a half-point. Miami **+6.5** cashes if the Bengals win by a single score. The edge is the gap between that price and the model’s margin, and it has to be at least 2 points.

**Preview lean (spread):** MIA +6.5 — edge 5.1 pts · **Preview lean (total):** OVER 42.5 — edge 3.0 pts

---

### Cleveland Browns at New York Jets

**Sun Oct 11, 12:00 PM CT.** Market: **NYJ -1.5**, total **39.5**. Model: **CLE by 1.1**, projected total **44.6**.

Cleveland should be a slight favorite, and the market has it the other way. Both teams rate poorly (CLE **-0.025**, NYJ **-0.056**). The market makes the Jets home favorites at **-1.5**. The model slightly prefers Cleveland with Deshaun Watson over Geno Smith, and it wants more points than **39.5**.

Deshaun Watson and Geno Smith are the depth-chart starters, and neither is on the ESPN injury report.

**Newcomer tip — opponent-adjusted rating:** raw EPA gets corrected for who you played. The Jets are last on this slate at **-0.056**, which is why the model will not treat them as home favorites.

**Preview lean (spread):** CLE +1.5 — edge 2.6 pts · **Preview lean (total):** OVER 39.5 — edge 5.1 pts

---

### Houston Texans at Tennessee Titans

**Sun Oct 11, 12:00 PM CT.** Market: **HOU -7.5**, total **37.5**. Model: **HOU by 4.0**, projected total **44.7**.

Houston should win. Tennessee is the lowest-rated team on this slate (**-0.071**), and the market agrees with a Texans win at **-7.5**. The model is less sure about the margin (Houston by **4.0**) and much higher on the total than **37.5**. C.J. Stroud and Cam Ward are the starters.

**Newcomer tip — totals vs margin:** a total of **37.5** prices a slog. The projected total is **44.7**, more than 3 points higher, which is the locked over trigger. That is separate from who wins.

**Preview lean (spread):** TEN +7.5 — edge 3.5 pts · **Preview lean (total):** OVER 37.5 — edge 7.2 pts

---

### Indianapolis Colts at Pittsburgh Steelers

**Sun Oct 11, 12:00 PM CT.** Market: **PIT -2.5**, total **44.5**. Model: **PIT by 1.3**, projected total **45.9**.

Pittsburgh should be a small home favorite. The model has the Steelers by **1.3**, and the market has them **-2.5**. Daniel Jones against Aaron Rodgers barely moves the quarterback layer. The gap is **1.2** points on the spread and **1.4** on the total, so the locked rule does not fire. On Monday this was a spread lean at Indy **+2.5**; the refreshed margin is closer to the same line.

**Newcomer tip — home field in the model:** the locked home-field term is about **1.5** points. Pittsburgh’s edge here is mostly that home field, on two teams rated near each other.

**No preview lean** under the locked rule (need 2+ points on the spread or 3+ on the total).

---

### Las Vegas Raiders at New England Patriots

**Sun Oct 11, 12:00 PM CT.** Market: **NE -3.5**, total **45.5**. Model: **NE by 3.1**, projected total **45.8**.

New England should win by about a field goal. The model has the Patriots by **3.1** at home with Drake Maye, and the market is **-3.5**. Kirk Cousins is the Raiders’ starter. The spread gap is **0.4** and the total gap is **0.3**.

**Newcomer tip — early-down EPA:** scoring drives are usually won on first and second down. New England’s early-down offense is about **-0.08** EPA/play; Las Vegas is about **-0.03**.

**No preview lean** under the locked rule (need 2+ points on the spread or 3+ on the total).

---

### Minnesota Vikings at New Orleans Saints

**Sun Oct 11, 12:00 PM CT.** Market: **MIN -1.5**, total **42.5**. Model: **MIN by 4.3**, projected total **46.0**.

Minnesota should win by more than a field goal. The Vikings rate better (**+0.027** vs NO **-0.034**), and Kyler Murray against Tyler Shough pushes the margin further, to Minnesota by **4.3**. The market only has the Vikings **-1.5**, so laying that number clears the 2-point line. On Monday the spread gap was under 2 points. It clears now. The total does too: model **46.0** against **42.5**.

Tyler Shough is **Questionable** (hand) on the ESPN injury report. This projection assumes he starts. If he does not, the quarterback piece of this number no longer applies.

**Newcomer tip — defense EPA allowed:** lower is better. Minnesota’s defense has allowed about **-0.21** EPA/play. That is a big reason they rate above the Saints.

**Preview lean (spread):** MIN -1.5 — edge 2.8 pts · **Preview lean (total):** OVER 42.5 — edge 3.5 pts

---

### New York Giants at Washington Commanders

**Sun Oct 11, 12:00 PM CT.** Market: **WSH -3.5**, total **42.5**. Model: **WAS by 5.1**, projected total **44.4**.

Washington should win at home. Both teams still sit near the bottom on team rating (WAS **-0.040**, NYG **-0.050**), but Jayden Daniels as the starter swings the quarterback layer toward the Commanders. The model has Washington by **5.1**. The market is **-3.5**, a **1.6**-point gap, and the totals are **1.9** apart. Both are short of the locked line.

Jayden Daniels is the depth-chart QB1 and he is not on the ESPN injury report for this game. ESPN’s Wednesday note says he fully practiced and is expected to play, three weeks after a dislocated elbow. Jameis Winston is the Giants’ starter. Monday’s preview used Athan Kaliakmanis because Daniels was still listed out. This one uses Daniels.

**Newcomer tip — why the quarterback note matters:** the team rating blends whoever has played. The QB adjustment re-aims the margin at the starter going into this game. Monday’s number and this number are different because the starter changed.

**No preview lean** under the locked rule (need 2+ points on the spread or 3+ on the total).

---

### Denver Broncos at Los Angeles Chargers

**Sun Oct 11, 3:05 PM CT.** Market: **DEN -3.5**, total **41.5**. Model: **DEN by 2.6**, projected total **46.7**.

Denver should win a close road game. The Broncos rate clearly better (**+0.040** vs LAC **-0.010**) and the market has them **-3.5**. Bo Nix against Justin Herbert is close to that price (model: Denver by **2.6**). The disagreement is the total: model **46.7** against **41.5**.

**Newcomer tip — explosive play rate:** the share of plays that gain 20 or more passing or 10 or more rushing. Denver’s offense is explosive on about **5.3%** of snaps; the Chargers’ on about **6.1%**. Big plays swing weeks. EPA is the steadier measure.

**Preview lean (total):** OVER 41.5 — edge 5.2 pts

---

### Detroit Lions at Arizona Cardinals

**Sun Oct 11, 3:25 PM CT.** Market: **DET -5.5**, total **54.5**. Model: **DET by 1.3**, projected total **45.9**.

Detroit should win a one-score game. The Lions rate a bit better than Arizona (**+0.011** vs **-0.023**), and Jared Goff against Jacoby Brissett fits that. The market has Detroit **-5.5** and a **54.5** total. The model wants Detroit by **1.3** and a total of **45.9**. Both clear the locked rule.

**Newcomer tip — when the total looks high:** **54.5** still prices a track meet. The projected total is **45.9**, built from both teams’ offensive and defensive EPA. An **8.6**-point gap clears the 3-point line.

**Preview lean (spread):** ARI +5.5 — edge 4.2 pts · **Preview lean (total):** UNDER 54.5 — edge 8.6 pts

---

### San Francisco 49ers at Seattle Seahawks

**Sun Oct 11, 3:25 PM CT.** Market: **SEA -2.5**, total **45.5**. Model: **SF by 0.3**, projected total **48.0**.

San Francisco should be the better team, and at this price that means taking the points. The 49ers are the highest-rated team on the slate (**+0.068**), with an offense at about **+0.27 EPA/play**. Seattle is solid (**+0.029**) and the market makes the Seahawks **-2.5** at home. With Sam Darnold starting, the model only has the 49ers by **0.3**, which still clears the 2-point line on SF **+2.5**. The total gap is **2.5**, short of 3.

The nflverse schedule still lists Drew Lock. The depth chart and ESPN have Sam Darnold as the starter, and he is not on the injury report. This projection uses Darnold. Brock Purdy starts for San Francisco.

**Newcomer tip — pass EPA:** San Francisco’s passing sits around **+0.54** EPA per pass play. That is the unit carrying a top rating after four weeks.

**Preview lean (spread):** SF +2.5 — edge 2.8 pts

---

### Baltimore Ravens at Atlanta Falcons

**Sun Oct 11, 7:20 PM CT.** Market: **ATL -3.5**, total **43.5**. Model: **BAL by 0.1**, projected total **46.6**.

This is a toss-up on the model, with Baltimore a tenth of a point in front. Team ratings still lean to the Ravens (**+0.037** vs Atlanta **-0.012**): before quarterbacks, the model had Baltimore by about **2.5**. Plugging in Lamar Jackson and Michael Penix Jr. pulls it to Baltimore by **0.1**. The market has gone the other way and now has Atlanta **-3.5** (on Monday it was Baltimore **-2.5**). Baltimore getting **3.5** clears the 2-point line, and the total clears 3 (model **46.6** against **43.5**).

Lamar Jackson is not on the ESPN injury report for this game. On Monday he was listed questionable. Michael Penix Jr. is Atlanta’s depth-chart QB1 and is not listed either. The schedule and the depth chart agree on both starters, so this projection uses them. The line moved about six points toward Atlanta anyway.

**Newcomer tip — walk-forward:** each week’s rating uses only games already played. Wednesday’s ratings include Monday night’s completed week-4 game, Falcons 45, Saints 24. That game is why Atlanta’s rating rose and New Orleans’s fell. Opponent adjustment then shifted the other teams a little.

**Preview lean (spread):** BAL +3.5 — edge 3.6 pts · **Preview lean (total):** OVER 43.5 — edge 3.1 pts

---

### Buffalo Bills at Los Angeles Rams

**Mon Oct 12, 7:15 PM CT.** Market: **LAR -3**, total **54.5**. Model: **LA by 4.3**, projected total **47.9**.

The Rams should win at home. They are near the top of the ratings (**+0.061**) and the model has them by about **4.3** with Matthew Stafford. Buffalo is strong too (**+0.028**) with Josh Allen. The market is only **-3**, a **1.3**-point gap, short of a spread lean. The total is the loud one: market **54.5**, model **47.9**.

**Newcomer tip — a big total:** the model’s total is offensive and defensive EPA turned into points. It has no separate bump for a Monday night game. A **6.6**-point gap under **54.5** means this offense-and-defense mix is not priced like a 54.

**Preview lean (total):** UNDER 54.5 — edge 6.6 pts

---

*Model run through 2026 week 4 on the code in `src/nfl_lab/`, locked coefficients unchanged. Tampa Bay’s margin is the same adjustment rerun with Jalon Daniels, because ESPN lists Baker Mayfield out. Spreads in the raw files use the home-team betting line (negative means the home team is favored). The sentences above name the favorite. Lines and injury listings checked Wednesday, Oct 7, 2026, 6:30 PM CT.*
