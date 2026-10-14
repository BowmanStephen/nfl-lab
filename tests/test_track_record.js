const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const { buildTrackRecord } = require("../public/assets/site.js");

function played(partial) {
  return {
    week: 5,
    gameday: "2026-10-12",
    away_team: "TB",
    home_team: "DAL",
    model_margin: 3,
    home_score: 20,
    away_score: 10,
    spread_qualifies: false,
    spread_outcome: null,
    total_active: false,
    total_outcome: null,
    ...partial,
  };
}

function week6Slate() {
  const games = [];
  for (let i = 0; i < 14; i += 1) {
    games.push(played({
      week: 6,
      gameday: "2026-10-18",
      away_team: `A${i}`,
      home_team: `H${i}`,
      model_margin: 1,
      home_score: null,
      away_score: null,
      spread_qualifies: i < 4,
      spread_outcome: null,
      total_active: i < 6,
      total_outcome: null,
    }));
  }
  return games;
}

function bugFixture() {
  const graded = [
    played({ away_team: "TB", home_team: "DAL", spread_qualifies: true, spread_outcome: "win" }),
    played({ away_team: "SF", home_team: "SEA", model_margin: -2, home_score: 10, away_score: 20, spread_qualifies: true, spread_outcome: "win" }),
    played({ away_team: "CLE", home_team: "NYJ", spread_qualifies: true, spread_outcome: "loss" }),
    played({ away_team: "HOU", home_team: "TEN", spread_qualifies: true, spread_outcome: "loss" }),
    played({ away_team: "IND", home_team: "PIT", spread_qualifies: true, spread_outcome: "loss" }),
    played({ away_team: "DET", home_team: "ARI", spread_qualifies: true, spread_outcome: "loss" }),
    played({ away_team: "CIN", home_team: "MIA", home_score: 31, away_score: 24, spread_qualifies: true, spread_outcome: "push" }),
  ];
  // A finished week can still have a game with no score. That leftover must
  // not join the current week's unplayed count.
  const leftover = played({
    away_team: "BUF",
    home_team: "LA",
    home_score: null,
    away_score: null,
    spread_qualifies: true,
    spread_outcome: null,
    total_active: true,
    total_outcome: null,
  });
  return {
    rc: {
      names: {},
      games: [
        { week: 4, gameday: "2026-10-04", away_team: "NYJ", home_team: "CHI", proj_margin: 3, home_score: 21, away_score: 14 },
        { week: 6, gameday: "2026-10-18", away_team: "XX", home_team: "YY", proj_margin: 1, home_score: null, away_score: null },
      ],
    },
    saved: {
      season: 2026,
      current_week: 6,
      weeks: [
        { week: 5, games: [...graded, leftover] },
        { week: 6, games: week6Slate() },
      ],
    },
  };
}

test("week 5 saved spreads count, and leftovers stay out of the current week", () => {
  const { rc, saved } = bugFixture();
  const view = buildTrackRecord(rc, saved);
  const still = "Week 6: 14 games have not been played yet, with 4 locked spreads and 6 locked totals still to play.";

  assert.equal(view.spread.num, "2-4-1");
  assert.equal(view.remaining.week, 6);
  assert.equal(view.remaining.games, 14);
  assert.equal(view.remaining.spreads, 4);
  assert.equal(view.remaining.totals, 6);
  assert.match(view.scope, /That starts in week 5\./);
  assert.ok(view.scope.includes(still));
  assert.ok(view.spread.gloss.includes(still));
  assert.equal(view.scope.includes("4 games are left to play"), false);
  assert.equal(view.spread.gloss.includes("4 games are left to play"), false);
  assert.match(view.scope, /The model got 1 of 1 right\./);

  const week5 = view.weeks.find((w) => w.week === 5);
  const week6 = view.weeks.find((w) => w.week === 6);
  assert.equal(week5.live, true);
  assert.equal(week6.live, true);
  assert.equal(week6.games.length, 14);
  assert.equal(week6.pending, 14);
});

test("a current week with nothing left omits the remaining sentence", () => {
  const view = buildTrackRecord({ games: [] }, {
    current_week: 6,
    weeks: [{
      week: 6,
      games: [played({
        week: 6,
        spread_qualifies: true,
        spread_outcome: "win",
        home_score: 24,
        away_score: 17,
      })],
    }],
  });
  assert.equal(view.spread.num, "1-0-0");
  assert.equal(view.remaining.games, 0);
  assert.equal(view.spread.gloss, "Did the pick beat the betting line?");
  assert.equal(view.scope.includes("not been played yet"), false);
});

test("published saved weeks include the week 5 record and current-week leftovers only", () => {
  const saved = JSON.parse(fs.readFileSync(path.join(__dirname, "../public/api/saved_weeks.json"), "utf8"));
  const view = buildTrackRecord({ games: [], names: {} }, saved);
  const week5 = saved.weeks.find((w) => w.week === 5);
  const outcomes = week5.games.filter((g) => g.spread_qualifies).map((g) => g.spread_outcome);
  assert.equal(outcomes.filter((o) => o === "win").length, 2);
  assert.equal(outcomes.filter((o) => o === "loss").length, 4);
  assert.equal(outcomes.filter((o) => o === "push").length, 1);

  const tally = { win: 0, loss: 0, push: 0 };
  for (const week of saved.weeks) {
    for (const game of week.games) {
      if (game.spread_qualifies && tally[game.spread_outcome] != null) tally[game.spread_outcome] += 1;
    }
  }
  assert.equal(view.spread.num, `${tally.win}-${tally.loss}-${tally.push}`);
  assert.notEqual(view.spread.num, "0-0-0");

  const current = saved.weeks.find((w) => w.week === saved.current_week);
  const unplayed = (g) => g.home_score == null || g.away_score == null;
  assert.deepEqual(view.remaining, {
    week: saved.current_week,
    games: current.games.filter(unplayed).length,
    spreads: current.games.filter((g) => g.spread_qualifies && !g.spread_outcome).length,
    totals: current.games.filter((g) => g.total_active && !g.total_outcome).length,
  });
  const still = view.spread.gloss.replace("Did the pick beat the betting line? ", "");
  assert.ok(view.scope.includes(still));
  assert.match(view.scope, /That starts in week 5\./);
});
