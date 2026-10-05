const $ = (id) => document.getElementById(id);

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

function fmt(n, digits = 1) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  return (v > 0 ? "+" : "") + v.toFixed(digits);
}

function when(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    weekday: "short", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit", timeZone: "America/New_York",
    timeZoneName: "short",
  });
}

async function load(name) {
  const res = await fetch(`api/${name}`);
  if (!res.ok) throw new Error(`${name} (${res.status})`);
  return res.json();
}

function gapChart(model, line) {
  const max = Math.max(8, Math.abs(model), Math.abs(line));
  const row = (label, value, cls) => {
    const pct = Math.min(50, (Math.abs(value) / max) * 50);
    const side = value >= 0 ? "pos" : "neg";
    return `<div class="gap-row"><span>${label}</span><div class="gap-track"><i class="${side} ${cls}" style="width:${pct}%"></i></div><b>${fmt(value)}</b></div>`;
  };
  return `<div class="gap">${row("Model", model, "")}${row("Line", line, "line")}</div>`;
}

function spark(weekly) {
  const vals = (weekly || []).map((w) => w.off_epa).filter((v) => v != null);
  if (vals.length < 2) return "";
  const w = 112, h = 28;
  const min = Math.min(...vals), max = Math.max(...vals);
  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * w;
    const y = h - 3 - ((v - min) / (max - min || 1)) * (h - 6);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline points="${pts}"/></svg>`;
}

function epaBar(value, kind) {
  const clamped = Math.max(-0.3, Math.min(0.3, Number(value) || 0));
  const pct = (Math.abs(clamped) / 0.3) * 50;
  const side = clamped >= 0 ? "pos" : "neg";
  return `<div class="bar"><i class="${side} ${kind}" style="width:${pct}%"></i></div>`;
}

function spreadCards(games) {
  return games
    .filter((g) => g.selection.spread_qualifies)
    .sort((a, b) => Math.abs(b.selection.spread_edge) - Math.abs(a.selection.spread_edge))
    .map((g) => {
      const s = g.selection;
      const line = g.pick_time.home_margin;
      const side = s.spread_pick === g.home_team ? g.home_team : g.away_team;
      const notes = (s.qb_notes || []).map((n) => `<p class="note">${esc(n)}</p>`).join("");
      return `<article class="card">
        <header><strong>${esc(g.away_team)} at ${esc(g.home_team)}</strong><span class="meta">${esc(when(g.kickoff_utc))}</span></header>
        <p class="side">${esc(side)} ${fmt(s.spread_pick === g.home_team ? -line : line)}</p>
        <div class="nums">
          <div><span>Model margin, home</span><b>${fmt(s.model_margin)}</b></div>
          <div><span>ESPN line, home</span><b>${fmt(line)}</b></div>
          <div><span>Edge</span><b>${fmt(Math.abs(s.spread_edge))}</b></div>
        </div>
        ${gapChart(s.model_margin, line)}
        <p class="meta">Snapshotted ${esc(when(g.pick_time.captured_at))} · ${esc(g.pick_time.provider)} · ${esc(g.pick_time.spread_display || "")}</p>
        <p class="meta">Starters used: ${esc(g.away_team)} ${esc(s.away_qb)}, ${esc(g.home_team)} ${esc(s.home_qb)}</p>
        ${notes}
      </article>`;
    }).join("");
}

function totalCards(games) {
  return games
    .filter((g) => g.selection.total_qualifies)
    .sort((a, b) => Math.abs(b.selection.total_edge) - Math.abs(a.selection.total_edge))
    .map((g) => {
      const s = g.selection;
      return `<article class="card">
        <header><strong>${esc(g.away_team)} at ${esc(g.home_team)}</strong><span class="meta">${esc(s.total_pick)} ${Number(g.pick_time.total).toFixed(1)}</span></header>
        <div class="nums">
          <div><span>Model total</span><b>${Number(s.model_total).toFixed(1)}</b></div>
          <div><span>ESPN total</span><b>${Number(g.pick_time.total).toFixed(1)}</b></div>
          <div><span>Edge</span><b>${fmt(Math.abs(s.total_edge))}</b></div>
        </div>
      </article>`;
    }).join("");
}

async function renderHome() {
  const card = await load("picks.json");
  $("kicker").textContent = `Week ${card.week} · ${card.season}`;
  $("health").textContent = card.health.line;
  const spreads = card.games.filter((g) => g.selection.spread_qualifies);
  const totals = card.games.filter((g) => g.selection.total_qualifies);
  $("count").textContent = `${spreads.length} spread picks · ${totals.length} total picks · ${card.games.length} games snapshotted`;
  $("spreads").innerHTML = spreads.length ? spreadCards(card.games) : "<p>No spread pick cleared 2 points this week.</p>";
  $("totals").innerHTML = totals.length ? totalCards(card.games) : "<p>No total cleared 3 points this week.</p>";
}

function record(r) {
  if (!r || r.win_rate == null) return "—";
  return `${r.wins}–${r.losses}–${r.pushes} (${(100 * r.win_rate).toFixed(1)}%)`;
}

async function renderLedger() {
  const [base, card] = await Promise.all([load("baseline.json"), load("picks.json")]);
  $("spread-rec").textContent = record(base.spread);
  $("total-rec").textContent = record(base.total);
  $("seasons").innerHTML = base.per_season.map((row) =>
    `<tr><td>${row.season}</td><td>${record(row.spread)}</td><td>${record(row.total)}</td></tr>`
  ).join("");
  $("live-health").textContent = card.health.line;
  const picks = card.games.filter((g) => g.selection.spread_qualifies || g.selection.total_qualifies);
  $("live").innerHTML = picks.map((g) => {
    const s = g.selection;
    const bits = [];
    if (s.spread_qualifies) bits.push(`${s.spread_pick}, ${Math.abs(s.spread_edge).toFixed(1)} pts off the spread`);
    if (s.total_qualifies) bits.push(`${s.total_pick}, ${Math.abs(s.total_edge).toFixed(1)} pts off the total`);
    return `<tr><td>${esc(g.away_team)} at ${esc(g.home_team)}</td><td>${esc(bits.join("; "))}</td><td>${esc(when(g.pick_time.captured_at))}</td></tr>`;
  }).join("");
}

async function renderTeams() {
  const data = await load("teams.json");
  $("through").textContent = `2026 regular season through week ${data.through_week}. Partial season.`;
  $("teams").innerHTML = data.teams.map((t, i) => `
    <article class="team" id="${esc(t.team)}">
      <div>
        <strong>${i + 1}. ${esc(t.name)}</strong>
        <div class="meta">${esc(t.team)} · rating ${fmt(t.rating, 3)}</div>
        ${spark(t.weekly)}
      </div>
      <div class="bars">
        <div class="bar-row"><span>Off</span>${epaBar(t.off_epa, "")}<b>${fmt(t.off_epa, 3)}</b></div>
        <div class="bar-row"><span>Def</span>${epaBar(-(t.def_epa || 0), "def")}<b>${fmt(t.def_epa, 3)}</b></div>
        <div class="meta">Success rate ${t.off_success == null ? "—" : (100 * t.off_success).toFixed(1)}% offense</div>
      </div>
    </article>`).join("");
}

async function renderFreshness() {
  const data = await load("freshness.json");
  const stale = new Date(data.stale_after).getTime() < Date.now();
  if (stale) {
    $("stale").hidden = false;
    $("stale").textContent = "This page is stale. The last refresh is older than 36 hours.";
  }
  $("when").textContent = when(data.generated_at);
  $("files").innerHTML = data.files.map((f) =>
    `<tr><td><code>${esc(f.path)}</code></td><td>${esc(when(f.updated_at))}</td><td>${f.bytes}</td><td><code>${esc(f.sha256.slice(0, 12))}</code></td></tr>`
  ).join("");
}


function fmtPct(rate) {
  return `${(100 * rate).toFixed(1)}%`;
}

function powerChart(ratings) {
  const maxAbs = Math.max(6, ...ratings.map((r) => Math.abs(r.points)));
  const rowH = 22;
  const padL = 36;
  const padR = 48;
  const padT = 8;
  const padB = 22;
  const W = 640;
  const H = padT + ratings.length * rowH + padB;
  const mid = padL + (W - padL - padR) / 2;
  const usable = (W - padL - padR) / 2;
  const x = (pts) => mid + (pts / maxAbs) * usable;

  const bars = ratings.map((r, i) => {
    const y = padT + i * rowH + 4;
    const x0 = mid;
    const x1 = x(r.points);
    const left = Math.min(x0, x1);
    const width = Math.max(2, Math.abs(x1 - x0));
    return `
      <rect class="track" x="${padL}" y="${y}" width="${W - padL - padR}" height="12" rx="6"/>
      <rect x="${left.toFixed(1)}" y="${y}" width="${width.toFixed(1)}" height="12" rx="6" fill="${esc(r.color)}" opacity="0.92"/>
      <text class="team-abbr" x="${padL - 8}" y="${y + 10}" text-anchor="end">${esc(r.team)}</text>
      <text class="pts" x="${W - padR + 8}" y="${y + 10}">${r.points > 0 ? "+" : ""}${r.points.toFixed(1)}</text>`;
  }).join("");

  const ticks = [-6, -3, 0, 3, 6].filter((t) => Math.abs(t) <= maxAbs + 0.01);
  const tickMarks = ticks.map((t) => {
    const tx = x(t);
    return `<line class="axis-line" x1="${tx}" y1="${padT}" x2="${tx}" y2="${H - padB + 2}"/>
      <text class="pts" x="${tx}" y="${H - 6}" text-anchor="middle">${t > 0 ? "+" : ""}${t}</text>`;
  }).join("");

  return `<svg class="power-chart" viewBox="0 0 ${W} ${H}" role="presentation" aria-hidden="true">
    ${tickMarks}
    <line class="zero" x1="${mid}" y1="${padT - 2}" x2="${mid}" y2="${H - padB + 4}"/>
    <text class="zero-label" x="${mid - 8}" y="${H - 6}" text-anchor="end">worse</text>
    <text class="zero-label" x="${mid + 8}" y="${H - 6}" text-anchor="start">better</text>
    ${bars}
  </svg>`;
}

function gameScale(market, model) {
  const maxAbs = Math.max(12, Math.abs(market), Math.abs(model)) + 1;
  const W = 320, H = 36, y = 16;
  const pad = 18;
  const x = (v) => pad + ((v + maxAbs) / (2 * maxAbs)) * (W - 2 * pad);
  const mid = x(0);
  // draw market under, model on top when close
  return `<svg class="game-scale" viewBox="0 0 ${W} ${H}" role="presentation" aria-hidden="true">
    <line class="rail" x1="${pad}" y1="${y}" x2="${W - pad}" y2="${y}"/>
    <line class="zero" x1="${mid}" y1="6" x2="${mid}" y2="26"/>
    <circle class="dot-market" cx="${x(market).toFixed(1)}" cy="${y}" r="5.5"/>
    <circle class="dot-model" cx="${x(model).toFixed(1)}" cy="${y}" r="5.5"/>
    <text class="tick-label" x="${pad}" y="34" text-anchor="start">away</text>
    <text class="tick-label" x="${W - pad}" y="34" text-anchor="end">home</text>
  </svg>`;
}

function gamesChart(games) {
  return games.map((g) => {
    const pickBits = [];
    if (g.spread_pick) pickBits.push(g.spread_pick);
    if (g.total_pick) pickBits.push(g.total_pick.replace("OVER", "Over").replace("UNDER", "Under"));
    const edgeBits = [];
    if (Math.abs(g.spread_edge) >= 2) edgeBits.push(`${Math.abs(g.spread_edge).toFixed(1)} off spread`);
    if (Math.abs(g.total_edge) >= 3) edgeBits.push(`${Math.abs(g.total_edge).toFixed(1)} off total`);
    const tag = g.is_pick
      ? (pickBits.join(" · ") || "Pick")
      : "No pick";
    // market_margin_home is the home spread (negative = home favored); flip it to a home margin for plotting
    const mktHome = -g.market_margin_home;
    const byLine = (m) => Math.abs(m) < 0.05 ? "even" : `${m > 0 ? g.home : g.away} by ${Math.abs(m).toFixed(1).replace(/\.0$/, "")}`;
    const sub = g.is_pick && edgeBits.length ? edgeBits.join(" · ") : `Line: ${byLine(mktHome)} · Model: ${byLine(g.model_margin_home)}`;
    return `<div class="game-row${g.is_pick ? " is-pick" : ""}">
      <div class="match">${esc(g.away)} @ ${esc(g.home)}<small>${esc(tag)}</small></div>
      ${gameScale(mktHome, g.model_margin_home)}
      <div class="edge-tag">${esc(sub)}</div>
    </div>`;
  }).join("");
}

function winRateChart(holdout) {
  const W = 320, H = 200;
  const padL = 44, padR = 16, padT = 24, padB = 36;
  const chartW = W - padL - padR;
  const chartH = H - padT - padB;
  const max = 0.65;
  const rows = [
    { label: "Spreads", rate: holdout.spread_win_rate, detail: `${holdout.spread_wins}–${holdout.spread_losses}–${holdout.spread_pushes}` },
    { label: "Totals", rate: holdout.total_win_rate, detail: `${holdout.total_wins}–${holdout.total_losses}–${holdout.total_pushes}` },
  ];
  const barW = 64;
  const gap = (chartW - rows.length * barW) / (rows.length + 1);
  const y = (rate) => padT + chartH - (rate / max) * chartH;
  const breakY = y(holdout.breakeven);

  const bars = rows.map((r, i) => {
    const x = padL + gap + i * (barW + gap);
    const top = y(r.rate);
    const h = padT + chartH - top;
    const below = r.rate < holdout.breakeven;
    return `
      <rect class="${below ? "bar-miss" : "bar-fill"}" x="${x}" y="${top}" width="${barW}" height="${h}" rx="8"/>
      <text class="val" x="${x + barW / 2}" y="${top - 8}" text-anchor="middle">${fmtPct(r.rate)}</text>
      <text class="label" x="${x + barW / 2}" y="${H - 18}" text-anchor="middle">${esc(r.label)}</text>
      <text class="axis" x="${x + barW / 2}" y="${H - 4}" text-anchor="middle">${esc(r.detail)}</text>`;
  }).join("");

  return `<svg class="rate-bar" viewBox="0 0 ${W} ${H}" role="presentation" aria-hidden="true">
    <line class="break" x1="${padL}" y1="${breakY}" x2="${W - padR}" y2="${breakY}"/>
    <text class="axis" x="${W - padR}" y="${breakY - 6}" text-anchor="end">Break-even ${fmtPct(holdout.breakeven)}</text>
    ${bars}
  </svg>`;
}

function maeChart(holdout) {
  const W = 320, H = 200;
  const padL = 44, padR = 16, padT = 28, padB = 36;
  const chartW = W - padL - padR;
  const chartH = H - padT - padB;
  const max = 12;
  const rows = [
    { label: "Model", val: holdout.model_mae_margin },
    { label: "Market", val: holdout.market_mae_margin },
  ];
  const barW = 64;
  const gap = (chartW - rows.length * barW) / (rows.length + 1);
  const y = (v) => padT + chartH - (v / max) * chartH;

  const bars = rows.map((r, i) => {
    const x = padL + gap + i * (barW + gap);
    const top = y(r.val);
    const h = padT + chartH - top;
    const cls = i === 0 ? "bar-miss" : "bar-fill";
    return `
      <rect class="${cls}" x="${x}" y="${top}" width="${barW}" height="${h}" rx="8"/>
      <text class="val" x="${x + barW / 2}" y="${top - 8}" text-anchor="middle">${r.val.toFixed(2)}</text>
      <text class="label" x="${x + barW / 2}" y="${H - 14}" text-anchor="middle">${esc(r.label)}</text>`;
  }).join("");

  return `<svg class="mae-bar" viewBox="0 0 ${W} ${H}" role="presentation" aria-hidden="true">
    <text class="axis" x="${padL}" y="14">Avg miss on final margin (pts)</text>
    ${bars}
  </svg>`;
}

async function renderModel() {
  const data = await load("model.json");
  $("ratings-caption").textContent =
    "Points better than an average team on a neutral field. Built from EPA per play, adjusted for who each team played.";
  $("ratings-chart").innerHTML = powerChart(data.ratings);
  $("games-chart").innerHTML = gamesChart(data.games);
  $("winrate-chart").innerHTML = winRateChart(data.holdout);
  $("mae-chart").innerHTML = maeChart(data.holdout);
  const live = data.live_2026;
  $("live-slot").querySelector(".live-label").textContent =
    live.label.charAt(0).toUpperCase() + live.label.slice(1);
}


/* 2026 so far: backtest report card */
function rcRec(r) {
  return r ? `${r.wins}-${r.losses}-${r.pushes}` : "n/a";
}

function rcPct(r) {
  return r && r.win_rate != null ? fmtPct(r.win_rate) : "n/a";
}

function rcNum(v, digits = 1) {
  return Number(v).toFixed(digits).replace(/\.0$/, "");
}

function rcRateChart(rc) {
  const W = 320, H = 200;
  const padL = 44, padR = 16, padT = 24, padB = 36;
  const chartW = W - padL - padR;
  const chartH = H - padT - padB;
  const max = 0.7;
  const rows = [
    { label: "Spreads", r: rc.spread },
    { label: "Totals", r: rc.total },
  ];
  const barW = 64;
  const gap = (chartW - rows.length * barW) / (rows.length + 1);
  const y = (rate) => padT + chartH - (rate / max) * chartH;
  const breakY = y(rc.breakeven);
  const bars = rows.map((row, i) => {
    const x = padL + gap + i * (barW + gap);
    const top = y(row.r.win_rate);
    const h = padT + chartH - top;
    const cls = row.r.win_rate < rc.breakeven ? "bar-miss" : "bar-fill";
    return `
      <rect class="${cls}" x="${x}" y="${top}" width="${barW}" height="${h}" rx="8"/>
      <text class="val" x="${x + barW / 2}" y="${top - 8}" text-anchor="middle">${fmtPct(row.r.win_rate)}</text>
      <text class="label" x="${x + barW / 2}" y="${H - 18}" text-anchor="middle">${esc(row.label)}</text>
      <text class="axis" x="${x + barW / 2}" y="${H - 4}" text-anchor="middle">${esc(rcRec(row.r))}</text>`;
  }).join("");
  return `<svg class="rate-bar" viewBox="0 0 ${W} ${H}" role="presentation" aria-hidden="true">
    <line class="break" x1="${padL}" y1="${breakY}" x2="${W - padR}" y2="${breakY}"/>
    <text class="axis" x="${W - padR}" y="${breakY - 6}" text-anchor="end">Break-even ${fmtPct(rc.breakeven)}</text>
    ${bars}
  </svg>`;
}

function rcDots(games, kind) {
  const ruleCol = kind === "spread" ? "spread_bet_locked_rule" : "total_bet_locked_rule";
  const outCol = kind === "spread" ? "spread_outcome" : "total_outcome";
  return games.filter((g) => g[ruleCol]).map((g) => {
    const o = g[outCol];
    const call = kind === "spread" ? g.spread_pick : g.total_pick;
    const word = o === "win" ? "covered" : o === "loss" ? "lost" : "pushed";
    const tip = `${g.away_team} at ${g.home_team}: ${call} ${word}`;
    return `<i class="rc-dot ${esc(o)}" title="${esc(tip)}"><span class="sr">${esc(tip)}</span></i>`;
  }).join("");
}

function rcWeeks(rc) {
  const head = `<div class="rc-week rc-week-head" aria-hidden="true"><span></span><span>Spreads</span><span>Totals</span></div>`;
  return head + rc.weekly.map((w) => {
    const games = rc.games.filter((g) => g.week === w.week);
    return `<div class="rc-week">
      <span class="rc-wk">Week ${w.week}</span>
      <div class="rc-cell"><div class="rc-dots">${rcDots(games, "spread")}</div><b>${esc(rcRec(w.spread))}</b></div>
      <div class="rc-cell"><div class="rc-dots">${rcDots(games, "total")}</div><b>${esc(rcRec(w.total))}</b></div>
    </div>`;
  }).join("");
}

function rcLesson(l, rc) {
  const N = (t) => `the ${rc.names[t] || t}`;
  const cap = (x) => x.charAt(0).toUpperCase() + x.slice(1);
  const by = (m) => `${m > 0 ? N(l.home) : N(l.away)} by ${rcNum(Math.abs(m))}`;
  let saw = "", happened = "", number = "";
  if (l.kind === "spread") {
    const pickLine = l.pick === l.home ? -l.line_home_margin : l.line_home_margin;
    const pickMargin = l.pick === l.home ? l.actual_home_margin : -l.actual_home_margin;
    saw = `The line had ${by(l.line_home_margin)}. The model had ${by(l.model_home_margin)}, ${rcNum(Math.abs(l.edge))} points away from the line, so it would have taken ${N(l.pick)} at ${pickLine > 0 ? "+" : ""}${rcNum(pickLine)}.`;
    happened = `${l.final}. ${cap(N(l.pick))} ${l.outcome === "win" ? "covered" : "did not cover"}.`;
    if (l.outcome === "win") {
      const dog = rc.spread_underdog_calls;
      number = `${dog.bets} of the model's ${rc.spread.bets} spread calls were on the underdog, and those went ${rcRec(dog)}. The model pulls every team hard toward average, so it rarely believes in a big favorite. Here that paid: ${N(l.pick)} were getting ${rcNum(Math.abs(pickLine))} points and ${pickMargin > 0 ? "won by" : "lost by only"} ${Math.abs(pickMargin)}.`;
    } else {
      number = `Same squeeze, other side. A ${rcNum(Math.abs(l.line_home_margin))}-point favorite looked like a ${rcNum(Math.abs(l.model_home_margin))}-point favorite to the model. The line missed the final margin by ${rcNum(l.line_miss_pts)} points. The model missed by ${rcNum(l.model_miss_pts)}.`;
    }
  } else {
    const side = l.pick === "over" ? "over" : "under";
    const sideRec = rc.total_by_side[side];
    const [pa, pb] = rc.proj_total_range;
    const [la, lb] = rc.line_total_range;
    const mu = l.model_used;
    const offPts = rc.points_per_combined_off * (mu[l.home].off_epa + mu[l.away].off_epa);
    const defPts = -rc.points_per_combined_off * (mu[l.home].def_epa + mu[l.away].def_epa);
    const stingy = mu[l.home].def_epa < mu[l.away].def_epa ? l.home : l.away;
    saw = `The line was ${rcNum(l.line_total)} points. The model expected ${rcNum(l.model_total)}, ${rcNum(Math.abs(l.edge))} points ${l.edge > 0 ? "higher" : "lower"}, so it would have taken the ${side}.`;
    happened = `${l.final}, ${l.actual_total} points in all. That is ${rcNum(l.line_miss_pts)} ${l.actual_total < l.line_total ? "under" : "over"} the line.`;
    number = `Every model total in weeks 1 to 4 landed between ${rcNum(pa)} and ${rcNum(pb)}, while the lines ran from ${rcNum(la)} to ${rcNum(lb)}. So low lines drew ${side}s, and ${side}s went ${rcRec(sideRec)}. Part of the reason is in the totals math itself: a defense that allows less adds projected points instead of taking them away. Here the two offenses ${offPts < 0 ? "took" : "added"} ${rcNum(Math.abs(offPts))} ${offPts < 0 ? "off" : ""}, and the defenses, led by ${N(stingy)}, ${defPts > 0 ? "added" : "took"} ${rcNum(Math.abs(defPts))} ${defPts > 0 ? "back" : "off"}.`;
  }
  return `<article class="rc-lesson">
    <p class="rc-tag ${l.outcome === "win" ? "hit" : "miss"}">${esc(l.label)}</p>
    <h3>${esc(l.matchup)}</h3>
    <p class="meta">Week ${l.week}</p>
    <dl>
      <div><dt>What the model saw</dt><dd>${esc(saw)}</dd></div>
      <div><dt>What happened</dt><dd>${esc(happened)}</dd></div>
    </dl>
    <p class="lesson"><span>The number</span>${esc(number.replace(/\s+/g, " ").replace(/ ,/g, ","))}</p>
  </article>`;
}

async function renderReportCard() {
  const [rc, model] = await Promise.all([load("report_card.json"), load("model.json")]);
  const be = fmtPct(rc.breakeven);
  const verdict = (r) => (r.win_rate > rc.breakeven ? `above the ${be} break-even` : `below the ${be} break-even`);
  $("rec-caption").textContent =
    `${rc.games_graded} games graded. A call counts when the model is ${rc.rule.spread_edge_min}+ points off the spread or ${rc.rule.total_edge_min}+ off the total. Break-even at standard odds is ${be}.`;
  $("rc-hero").innerHTML = [
    ["Spreads", rc.spread], ["Totals", rc.total],
  ].map(([label, r]) => `<div class="rc-big ${r.win_rate > rc.breakeven ? "up" : "down"}">
      <span>${label}</span>
      <b>${rcRec(r)}</b>
      <p>${rcPct(r)}, ${verdict(r)}</p>
    </div>`).join("");
  $("rc-winrate").innerHTML = rcRateChart(rc);
  const all = rc.all_games_model_side;
  $("rc-context").innerHTML = `${maeChart({ model_mae_margin: rc.model_mae_margin, market_mae_margin: rc.market_mae_margin })}
    <p class="meta">If it had taken a side in every game, not just the big gaps: spreads ${rcRec(all.spread)} (${rcPct(all.spread)}), totals ${rcRec(all.total)} (${rcPct(all.total)}). The line still guessed final margins better.</p>`;
  $("rc-weeks").innerHTML = rcWeeks(rc);
  $("rc-lessons").innerHTML = rc.lessons.map((l) => rcLesson(l, rc)).join("");

  const lc = rc.leak_check;
  const h = model.holdout;
  const pending = rc.pending.length
    ? `<p>${rc.pending.map((p) => esc(p.matchup)).join(", ")} had not finished when this ran, so it is not graded.</p>` : "";
  $("rc-honest").innerHTML = `
    <p>Each week, the model only saw games already played. Week 3 used weeks 1 and 2. Week 4 used weeks 1 through 3. The settings were tuned on ${rc.model.fit_on_seasons[0]} to ${rc.model.fit_on_seasons[rc.model.fit_on_seasons.length - 1]} and frozen before any of this.</p>
    <p>We tested it. For each week, we swapped every play from that week onward for random numbers (${lc.map((x) => x.plays_poisoned.toLocaleString("en-US")).join(", ")} plays for weeks ${lc.map((x) => x.week).join(", ")}) and ran it again. That week's numbers did not move at all. Scrambling earlier weeks did move weeks 3 and 4, so the test can catch a leak.</p>
    <p>Weeks 1 and 2 ran on ${rc.model.prior_seasons[0]} to ${rc.model.prior_seasons[2]} alone. With one game per team, the model's strength-of-schedule step cancels out, so 2026 games start counting in week 3.</p>
    <p>Lines are nflverse closing numbers, used only to grade. This is the same model as the 2022 to 2025 test (${fmtPct(h.spread_win_rate)} on spreads, ${fmtPct(h.total_win_rate)} on totals), without the starting-QB adjustment the live card uses. Four weeks is a small sample in either direction.</p>
    ${pending}`;
  const t = new Date(rc.generated_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/Chicago" });
  $("rc-foot").textContent = `Backtest generated ${t} CT. Closing lines and final scores from nflverse. Research record, not a bet slip.`;
}

const page = document.body.dataset.page;
const run = {
  home: renderHome,
  ledger: renderLedger,
  teams: renderTeams,
  freshness: renderFreshness,
  model: renderModel,
  "report-card": renderReportCard,
}[page];
if (run) {
  run().catch((err) => {
    const slot = $("health") || $("when") || $("ratings-caption") || $("rec-caption") || document.querySelector("main");
    if (slot) slot.textContent = `Could not load the latest JSON (${err.message}).`;
  });
}
