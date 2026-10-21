# Week 7 previews, in plain English

Lines as of Wed Oct 21, 6:17 PM CT (DraftKings via ESPN). Buffalo, Jacksonville, the Chargers and Washington are off. Times are Central. These are previews, not official picks. The official pick list is the card locked Tue Oct 20, 6:24 AM CT, in `output/live/2026-week-07.json`, not this page. A game marked as a preview check meets the locked rule on today's line: our model is 2 or more points from Vegas on the margin, or 3 or more on the total.

The 6 week-6 over/under picks were voided Oct 15, and over/unders are paused. A replay of weeks 1-4 with the corrected totals formula went 6-18. The original frozen-model record remains 10-19; the replay does not replace it. The spread picks stand. A total that clears 3 points is a preview check, not a pick.

The earlier version of the model did not beat the market in its 2022 to 2025 test: 48.8% on the margin and 51.0% on totals, short of the 52.4% break-even. The v2 model used here was not part of that test, so it has no proven record yet. Model numbers come from the NFL Lab code on main (model v2, nflverse through week 6, starting-QB adjustment), run Wednesday evening. Machine-readable lines: `pipeline/previews/2026-week-07-preview-lines.json`.

---

### New England Patriots at Chicago Bears

**Thu Oct 22, 7:15 PM CT.** Vegas says Chicago by 3, 50.5 total points. Our model says Chicago by 2.8, 44.5 total points.

**Preview check (not an official pick):** Fewer than 50.5 points

Chicago should win a close game at home, about a 58% chance, with Caleb Williams against Drake Maye. Both teams are 4-2, and our model and Vegas are 0.2 points apart on the margin. Where they split is the score. The model expects 44.5 total points, and Vegas has 50.5.

**Newcomer tip: the total.** The total is Vegas's guess at both teams' points added together. At 50.5, Vegas expects more scoring than our model does. The model is 6.0 points lower. Over/unders are paused, so that gap is a preview check, not a pick.

*Over/unders are paused, so this is a preview check, not a pick. The model is 6.0 points below the 50.5 total (3 needed). On the margin the gap is 0.2 points.*

---

### Pittsburgh Steelers at New Orleans Saints

**Sun Oct 25, 8:30 AM CT.** Vegas says Pittsburgh by 3.5, 44.5 total points. Our model says Pittsburgh by 4.4, 46.8 total points.

**Too close to call.**

Pittsburgh should win, about a 63% chance, with Aaron Rodgers against Tyler Shough. The Steelers are 4-2 and the Saints are 2-4. Our model and Vegas agree on the winner. The margin gap is under a point.

**Newcomer tip: success rate allowed.** A play is a success when it gains enough yards to stay on schedule for that down. Opponents have succeeded on about 49.5% of plays against the Saints, 32nd of 32. For a defense, lower is better.

*Pick under the rule: no. The model is 0.9 points from Vegas on the margin (2 needed) and 2.3 points on the total (3 needed).*

---

### Cincinnati Bengals at Baltimore Ravens

**Sun Oct 25, 12:00 PM CT.** Vegas says Cincinnati by 1.5, 48.5 total points. Our model says Baltimore by 8.0 with Lamar Jackson, or Baltimore by 2.7 with Tyler Huntley, and 48.7 total points either way.

**Preview check (not an official pick):** Baltimore wins, or loses by 1 at most

Baltimore should win. With Jackson, our model gives the Ravens about a 73% chance and has them winning by 8. With Huntley, it is about a 58% chance and Baltimore by 2.7. Vegas has moved the other way: Tuesday morning it had Baltimore by 3, and now it has Cincinnati by 1.5. Joe Burrow starts for Cincinnati. Baltimore is 4-2 and Cincinnati is 3-2.

The schedule still lists Tyler Huntley. ESPN's depth chart has Lamar Jackson at QB1, and ESPN lists him Questionable (ankle); he was a limited participant Wednesday. This morning's nflverse depth chart also has Jackson first. The nflverse week-7 report has no Out or Doubtful statuses, so the model's run uses Jackson. Tuesday's card used Huntley, because Jackson was listed Out on the week-6 report, and that card had no spread pick. We are not guessing who starts.

**Newcomer tip: early-down EPA.** EPA, expected points added, measures how much a play changed a team's chances of scoring. First and second down set up everything else. Baltimore gains about +0.14 expected points per early-down play, 5th in the league. Cincinnati is at about +0.01, 13th.

*The margin check is a preview, not an official pick, with either quarterback. With Jackson the model is 9.5 points from Wednesday's line. With Huntley it is 4.2. Both clear the 2 needed. Tuesday's official card has no spread pick. Over/unders are paused. The total gap is 0.2 points.*

---

### Cleveland Browns at Tennessee Titans

**Sun Oct 25, 12:00 PM CT.** Vegas says Cleveland by 1.5, 37.5 total points. Our model says Cleveland by 2.2, 39.3 total points.

**Too close to call.**

Cleveland should win a low-scoring game, about a 57% chance, with Deshaun Watson against Cam Ward. The Browns are 4-2 and have scored 106 points. The Titans are 1-5, have scored 84, and rate last of 32. Our model and Vegas are under a point apart.

**Newcomer tip: EPA per play.** Tennessee's offense is about −0.13 expected points per play, 31st of 32. A negative number means the average play made scoring less likely. That is a big part of a 37.5 total, the lowest of the week.

*Pick under the rule: no. The model is 0.7 points from Vegas on the margin (2 needed) and 1.8 points on the total (3 needed).*

---

### Indianapolis Colts at Minnesota Vikings

**Sun Oct 25, 12:00 PM CT.** Vegas says Minnesota by 6.5, 41.5 total points. Our model says Minnesota by 8.2, 43.1 total points.

**Too close to call.**

Minnesota should win at home, about a 73% chance, with Kyler Murray against Daniel Jones. The Vikings are 5-0 and have allowed 64 points in five games, the fewest in the league. Indianapolis is 2-4. Our model has Minnesota winning by more than Vegas does, and the gap is under 2 points.

**Newcomer tip: success rate allowed.** Minnesota's defense lets opponents succeed on about 32% of plays, the lowest in the league. For a defense, lower is better.

*Pick under the rule: no. The model is 1.7 points from Vegas on the margin (2 needed) and 1.6 points on the total (3 needed).*

---

### Miami Dolphins at New York Jets

**Sun Oct 25, 12:00 PM CT.** Vegas says the Jets by 4.5, 39.5 total points. Our model says the Jets by 2.5, 42.1 total points.

**Too close to call.**

The Jets should win, about a 58% chance, with Geno Smith against Malik Willis. Miami is 0-5 and has scored 70 points in five games, the fewest in the league. Our model agrees with Vegas on the winner and is just short of the 2 points that would make it a spread pick.

**Newcomer tip: pass rate over expected.** Given the down, distance and score, a typical team passes a certain share of the time. Miami passes about 11.5 percentage points less than that, last of 32.

*Pick under the rule: no. The margin gap is 1.98 points, just short of 2. The total gap is 2.6 points, short of 3.*

---

### New York Giants at Houston Texans

**Sun Oct 25, 12:00 PM CT.** Vegas says Houston by 10.5, 42.5 total points. Our model says Houston by 6.7 with Jameis Winston, or Houston by 8.3 with J.J. McCarthy, and 45.3 total points either way.

**Preview check (not an official pick):** The Giants win, or lose by 10 at most

Houston should win. With Winston, our model gives the Texans about a 69% chance and has them winning by 6.7. With McCarthy, it is about a 74% chance and Houston by 8.3. Vegas has Houston by 10.5, so the Giants' side is the one past the line either way. The Giants are 3-2-1 and Houston is 2-4. C.J. Stroud starts for Houston.

The model's run uses Jameis Winston, because this morning's nflverse depth chart still had him at QB1 and the week-7 report has no Out or Doubtful statuses. The schedule now lists J.J. McCarthy. ESPN's depth chart this evening has McCarthy at QB1 and Winston second, and ESPN reports that coach John Harbaugh said Wednesday that McCarthy will start. Tuesday's locked card also used Winston, at Houston by 10, and that spread pick stands. We are not guessing who starts.

**Newcomer tip: opponent-adjusted rating.** A team's raw stats get corrected for who it has played, so beating weak teams counts for less. After that correction, Houston sits 14th of 32 and the Giants 31st. The 3-2-1 record makes the Giants look stronger than that rating.

*Pick under the rule: yes, on the margin, with either quarterback. With Winston the model is 3.8 points from Vegas. With McCarthy it is 2.2. Both clear the 2 needed. The official spread pick stands. The total gap is 2.8 points, short of 3. Over/unders are paused.*

---

### San Francisco 49ers at Atlanta Falcons

**Sun Oct 25, 12:00 PM CT.** Vegas says San Francisco by 3, 49.5 total points. Our model says San Francisco by 5.5, 47.7 total points.

**Preview check (not an official pick):** San Francisco wins by 4 or more

San Francisco should win, about a 66% chance, with Brock Purdy against Michael Penix Jr. The 49ers are 6-0 and rate 1st of 32. Atlanta is 2-4. Tuesday morning Vegas had San Francisco by 3.5. Our model has them winning by more than today's line.

**Newcomer tip: success rate.** A play is a success when it gains enough yards to stay on schedule for that down. San Francisco's offense stays on schedule on about 52% of plays, 1st of 32.

*Pick under the rule: yes, on the margin. The model is 2.5 points past Vegas's 3 (2 needed). The official spread pick stands. The total gap is 1.8 points, so no. Over/unders are paused.*

---

### Tampa Bay Buccaneers at Carolina Panthers

**Sun Oct 25, 12:00 PM CT.** Vegas says Carolina by 3, 44.5 total points. Our model says Tampa Bay by 2.1 with Baker Mayfield, or Carolina by 2.5 with Jalon Daniels, and 46.7 total points either way.

**No official pick.**

Who wins depends on Tampa Bay's quarterback. With Mayfield, our model makes the Buccaneers slight favorites, about a 56% chance, and that is 5.1 points from Carolina's line. With Daniels, it has Carolina by 2.5, about a 58% chance, close to Vegas. Tampa Bay is 1-5 and Carolina is 3-2. Bryce Young starts for Carolina.

ESPN lists Mayfield Questionable (thumb). He was a full participant Wednesday, and ESPN's depth chart still has him at QB1, with Daniels second. This morning's nflverse depth chart has the same order. The schedule lists Daniels. The model's run uses Mayfield, because the week-7 report has no Out or Doubtful statuses. Tuesday's card used Daniels, because Mayfield was listed Out on the week-6 report, and that card had no spread pick. We are not guessing who starts.

**Newcomer tip: EPA per play.** Tampa Bay's offense is about −0.13 expected points per play, 30th of 32. A negative number means the average play made scoring less likely.

*The margin depends on the quarterback and is not an official pick: with Mayfield the gap is 5.1 points, with Daniels it is 0.5. The total gap is 2.2 points, short of 3. Over/unders are paused.*

---

### Denver Broncos at Arizona Cardinals

**Sun Oct 25, 3:05 PM CT.** Vegas says Denver by 4.5, 43.5 total points. Our model says Denver by 5.9, 45.5 total points.

**Too close to call.**

Denver should win, about a 67% chance, with Bo Nix against Jacoby Brissett. The Broncos are 4-2 and the Cardinals are 2-4. Arizona has allowed 178 points, tied with New Orleans for the most in the league. Our model has Denver winning by a bit more than Vegas does.

**Newcomer tip: EPA per pass allowed.** Arizona gives up about +0.27 expected points every time the other team passes, 30th of 32. For a defense, a positive number is bad: the offense is usually moving toward points.

*Pick under the rule: no. The model is 1.4 points from Vegas on the margin (2 needed) and 2.0 points on the total (3 needed).*

---

### Green Bay Packers at Detroit Lions

**Sun Oct 25, 3:25 PM CT.** Vegas says Detroit by 3, 53.5 total points. Our model says Detroit by 4.4, 50.7 total points.

**Too close to call.**

Detroit should win at home, about a 63% chance, with Jared Goff against Jordan Love. The Lions' offense ranks 3rd in EPA per play and their defense ranks last. The Packers are 4-2. Our model and Vegas agree Detroit wins, and they are 1.4 points apart. The model expects fewer points than the 53.5 total.

Jordan Love is Questionable (back) on ESPN's injury report. He was a limited participant Wednesday. The schedule, ESPN's depth chart and the nflverse depth chart all still have him at QB1, so this number uses Love. Tyrod Taylor is next on both depth charts. If Taylor starts, the model has Detroit by 9.1 instead of 4.4, which is 6.1 points past Vegas's 3 and would meet the spread rule. We are not guessing who starts.

**Newcomer tip: explosive plays.** An explosive play is a pass of 20 or more yards or a run of 15 or more. Green Bay's defense allows one on about 3.4% of snaps, the fewest in the league.

*Pick under the rule: no, with Love. The gap is 1.4 points on the margin and 2.8 on the total. If Taylor starts, the margin gap would be 6.1 points. That is not the number this page uses.*

---

### Los Angeles Rams at Las Vegas Raiders

**Sun Oct 25, 3:25 PM CT.** Vegas says the Rams by 4.5, 48.5 total points. Our model says the Rams by 4.5, 47.2 total points.

**Too close to call.**

The Rams should win, about a 63% chance, with Matthew Stafford against Kirk Cousins. Our model and Vegas land on the same margin, the Rams by 4.5. The Rams are 2-4 and the Raiders are 3-3, so the record alone does not say this.

**Newcomer tip: opponent-adjusted rating.** A team's results get corrected for who it has played, and prior seasons still count for something. After that, the Rams rate 3rd of 32. The Raiders rate 26th.

*Pick under the rule: no. The margin gap is 0.0 points. The total gap is 1.3 points.*

---

### Kansas City Chiefs at Seattle Seahawks

**Sun Oct 25, 7:20 PM CT.** Vegas says Seattle by 2.5, 42.5 total points. Our model says Seattle by 1.0 with Sam Darnold, or Kansas City by 2.0 with Drew Lock, and 44.5 total points either way.

**No official pick.**

Who wins is close, and it depends on Seattle's quarterback. With Darnold, our model has Seattle by 1.0, about a 53% chance, which is 1.5 points short of Vegas. With Lock, it has Kansas City by 2.0, about a 56% chance, and that would clear the spread rule. The Chiefs are 5-0. Seattle is 3-3, and its defense ranks 2nd in EPA allowed per play. Patrick Mahomes starts for Kansas City.

The schedule lists Drew Lock. ESPN's depth chart has Sam Darnold at QB1 and Lock second, and ESPN lists Lock Questionable (elbow). This morning's nflverse depth chart has the same order, so the model's run uses Darnold. Tuesday's card used Darnold and had no spread pick. We are not guessing who starts.

**Newcomer tip: rushing EPA.** Most runs lose a little expected value, so 27 of 32 teams are below zero per run. Kansas City is above it, at about +0.10 per run, 1st of 32.

*The margin depends on the quarterback and is not an official pick: with Darnold the gap is 1.5 points, with Lock it is 4.5. The total gap is 2.0 points, short of 3. Over/unders are paused.*

---

### Dallas Cowboys at Philadelphia Eagles

**Mon Oct 26, 7:15 PM CT.** Vegas says Dallas by 4.5, 44.5 total points. Our model says Philadelphia by 0.5, 47.3 total points.

**Preview check (not an official pick):** Philadelphia wins, or loses by 4 at most

Our model says Philadelphia, barely, about a 52% chance at home, with Tanner McKee against Dak Prescott. That is not a strong side. The gap is the number: Vegas has Dallas by 4.5, and the model is 5.0 points away from that line, on Philadelphia's side. Dallas is 2-4 with one of the league's better offenses and one of its worst defenses. Philadelphia is 2-4, and its offense ranks near the bottom.

The schedule still lists Jalen Hurts. ESPN's depth chart has Tanner McKee at QB1, and Hurts is on injured reserve (calf). The nflverse depth chart has the same order. This number uses McKee. Tuesday's card used McKee, and the official spread pick stands.

**Newcomer tip: EPA per pass allowed.** Dallas gives up about +0.33 expected points every time the other team passes, last of 32. For a defense, a positive number is bad: the offense is usually moving toward points.

*Pick under the rule: yes, on the margin. The model is 5.0 points from Vegas's Dallas by 4.5 (2 needed). The official spread pick stands. The total gap is 2.8 points, short of 3. Over/unders are paused.*
