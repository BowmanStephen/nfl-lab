const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const { buildTrackRecord, totalsArePaused } = require("../public/assets/site.js");

const PAUSED_NOTE = "Over/under picks are paused while we fix that model.";
const OPEN_SENTENCE = "Week 6: 14 games to go, with 4 locked spreads and 6 locked totals riding on them.";
const PAUSED_SENTENCE = "Week 6: 14 games to go, with 4 locked spreads riding on them.";

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
  const view = buildTrackRecord(rc, saved, { totalsPaused: false });
  const still = OPEN_SENTENCE;

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

test("paused totals leave locked spreads in the week sentence", () => {
  const { rc, saved } = bugFixture();
  assert.equal(totalsArePaused(saved, PAUSED_NOTE), true);
  const view = buildTrackRecord(rc, saved, { totalsPaused: totalsArePaused(saved, PAUSED_NOTE) });
  assert.equal(view.remaining.games, 14);
  assert.equal(view.remaining.spreads, 4);
  assert.equal(view.remaining.totals, 6);
  assert.ok(view.scope.includes(PAUSED_SENTENCE));
  assert.ok(view.spread.gloss.includes(PAUSED_SENTENCE));
  assert.equal(view.scope.includes("locked totals"), false);
  assert.equal(view.spread.gloss.includes("locked totals"), false);
});

test("active totals stay in the week sentence when over/unders are not paused", () => {
  const { rc, saved } = bugFixture();
  assert.equal(totalsArePaused(saved, ""), false);
  const view = buildTrackRecord(rc, saved, { totalsPaused: totalsArePaused(saved, "") });
  assert.ok(view.scope.includes(OPEN_SENTENCE));
  assert.ok(view.spread.gloss.includes(OPEN_SENTENCE));
});

test("an earlier week does not pause the current week", () => {
  const saved = {
    current_week: 6,
    weeks: [
      { week: 5, games: [played({ total_active: true })] },
      { week: 6, games: week6Slate().map((g) => ({ ...g, total_active: false })) },
    ],
  };
  assert.equal(totalsArePaused(saved, PAUSED_NOTE), false);
});

test("the live pause signal is TOTALS_PAUSED_NOTE plus an active total", () => {
  const src = fs.readFileSync(path.join(__dirname, "../public/assets/site.js"), "utf8");
  const hasNote = /const TOTALS_PAUSED_NOTE\s*=\s*["'][^"']+["']/.test(src);
  const { rc, saved } = bugFixture();
  assert.equal(totalsArePaused(saved), hasNote);
  const view = buildTrackRecord(rc, saved);
  const sentence = hasNote ? PAUSED_SENTENCE : OPEN_SENTENCE;
  assert.ok(view.scope.includes(sentence));
  assert.ok(view.spread.gloss.includes(sentence));
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

test("winner record combines saved weeks and excludes ties, no calls, and unfinished games", () => {
  const view = buildTrackRecord({
    games: [
      { week: 4, proj_margin: 3, home_score: 21, away_score: 14 },
      { week: 5, proj_margin: -3, home_score: 21, away_score: 14 },
    ],
  }, {
    current_week: 6,
    weeks: [
      { week: 5, games: [
        played({ model_margin: 3 }),
        played({ model_margin: -3 }),
        played({ home_score: 17, away_score: 17 }),
        played({ model_margin: 0 }),
        played({ home_score: null }),
      ] },
      { week: 6, games: [
        played({ week: 6, model_margin: -3, home_score: 10, away_score: 20 }),
        played({ week: 6, model_margin: 3, home_score: 10, away_score: 20 }),
        played({ week: 6, home_score: null, away_score: null }),
        played({ week: 6, away_score: null }),
      ] },
    ],
  });

  // Winner calls count even when they do not qualify as spread picks.
  // Look-back games and duplicate report-card weeks must not enter the tile.
  assert.equal(view.winner.num, "2 of 4");
  assert.equal(view.winner.gloss, "50% right. Did the team the model had ahead win?");
  assert.match(view.scope, /1 tie is left out because nobody won\./);
  assert.equal(view.remaining.games, 2);
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

  const winnerCalls = saved.weeks.flatMap((week) => week.games).filter((game) =>
    game.home_score != null && game.away_score != null
    && game.home_score !== game.away_score && game.model_margin);
  const correctCalls = winnerCalls.filter((game) => game.model_margin > 0
    ? game.home_score > game.away_score
    : game.away_score > game.home_score);
  assert.ok(winnerCalls.some((game) => game.week < saved.current_week));
  assert.equal(view.winner.num, `${correctCalls.length} of ${winnerCalls.length}`);

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
