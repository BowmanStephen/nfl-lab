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

function whenCT(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    weekday: "short", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit", timeZone: "America/Chicago",
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
        <p class="meta">Snapshotted ${esc(whenCT(g.pick_time.captured_at))} · ${esc(g.pick_time.provider)} · ${esc(g.pick_time.spread_display || "")}</p>
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

function noPickReason(game) {
  const s = game.selection;
  if (s.no_pick_reason) return s.no_pick_reason;
  return `No pick: locked rule (|spread edge| ${Math.abs(s.spread_edge).toFixed(1)} < 2 and |total edge| ${Math.abs(s.total_edge).toFixed(1)} < 3).`;
}

function noPickCards(games) {
  return games
    .filter((g) => !g.selection.spread_qualifies && !g.selection.total_qualifies)
    .map((g) => {
      const s = g.selection;
      return `<article class="card">
        <header><strong>${esc(g.away_team)} at ${esc(g.home_team)}</strong><span class="meta">No pick</span></header>
        <p>${esc(noPickReason(g))}</p>
        <div class="nums">
          <div><span>Model margin, home</span><b>${fmt(s.model_margin)}</b></div>
          <div><span>ESPN line, home</span><b>${fmt(g.pick_time.home_margin)}</b></div>
          <div><span>Spread edge</span><b>${fmt(s.spread_edge)}</b></div>
          <div><span>Model total</span><b>${Number(s.model_total).toFixed(1)}</b></div>
          <div><span>ESPN total</span><b>${Number(g.pick_time.total).toFixed(1)}</b></div>
          <div><span>Total edge</span><b>${fmt(s.total_edge)}</b></div>
        </div>
        <p class="meta">Starters used: ${esc(g.away_team)} ${esc(s.away_qb)}, ${esc(g.home_team)} ${esc(s.home_qb)}</p>
      </article>`;
    }).join("");
}

function showLock(card) {
  const label = $("lock-label");
  if (label && card.lock_label) label.textContent = card.lock_label;
  const note = $("holdout-note");
  if (note && card.holdout_note) note.textContent = card.holdout_note;
}

async function renderHome() {
  const card = await load("picks.json");
  $("kicker").textContent = `Week ${card.week} · ${card.season}`;
  showLock(card);
  $("health").textContent = card.health.line;
  const spreads = card.games.filter((g) => g.selection.spread_qualifies);
  const totals = card.games.filter((g) => g.selection.total_qualifies);
  const nopicks = card.games.filter((g) => !g.selection.spread_qualifies && !g.selection.total_qualifies);
  $("count").textContent = `${spreads.length} spread picks · ${totals.length} total picks · ${card.games.length} games snapshotted`;
  $("spreads").innerHTML = spreads.length ? spreadCards(card.games) : "<p>No spread pick cleared 2 points this week.</p>";
  $("totals").innerHTML = totals.length ? totalCards(card.games) : "<p>No total cleared 3 points this week.</p>";
  if ($("nopicks")) {
    $("nopicks").innerHTML = nopicks.length ? noPickCards(card.games) : "<p>Every snapshotted game cleared a pick.</p>";
  }
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
  showLock(card);
  $("live-health").textContent = card.health.line;
  const picks = card.games.filter((g) => g.selection.spread_qualifies || g.selection.total_qualifies);
  $("live").innerHTML = picks.map((g) => {
    const s = g.selection;
    const bits = [];
    if (s.spread_qualifies) bits.push(`${s.spread_pick}, ${Math.abs(s.spread_edge).toFixed(1)} pts off the spread`);
    if (s.total_qualifies) bits.push(`${s.total_pick}, ${Math.abs(s.total_edge).toFixed(1)} pts off the total`);
    return `<tr><td>${esc(g.away_team)} at ${esc(g.home_team)}</td><td>${esc(bits.join("; "))}</td><td>${esc(whenCT(g.pick_time.captured_at))}</td></tr>`;
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

function officialGames(card) {
  return card.games.map((g) => {
    const s = g.selection;
    const homeMargin = Number(g.pick_time.home_margin);
    let spreadPick = null;
    if (s.spread_qualifies) {
      const points = s.spread_pick === g.home_team ? -homeMargin : homeMargin;
      const text = `${points > 0 ? "+" : ""}${Math.abs(points % 1) < 0.05 ? Math.round(points) : points.toFixed(1)}`;
      spreadPick = `${s.spread_pick} ${text}`;
    }
    let totalPick = null;
    if (s.total_qualifies) {
      const word = s.total_pick === "over" ? "Over" : "Under";
      totalPick = `${word} ${Number(g.pick_time.total).toFixed(1)}`;
    }
    return {
      away: g.away_team,
      home: g.home_team,
      market_margin_home: -homeMargin,
      model_margin_home: s.model_margin,
      spread_edge: s.spread_edge,
      total_edge: s.total_edge,
      spread_pick: spreadPick,
      total_pick: totalPick,
      is_pick: Boolean(s.spread_qualifies || s.total_qualifies),
    };
  });
}

async function renderModel() {
  const [data, card] = await Promise.all([load("model.json"), load("picks.json")]);
  $("ratings-caption").textContent =
    "Points better than an average team on a neutral field. Built from EPA per play, adjusted for who each team played.";
  $("ratings-chart").innerHTML = powerChart(data.ratings);
  $("games-chart").innerHTML = gamesChart(officialGames(card));
  const caption = $("week5-caption");
  if (caption && card.lock_label) {
    caption.textContent = `${card.lock_label}. A pick lights up only when that card clears 2 points on the spread or 3 on the total.`;
  }
  $("winrate-chart").innerHTML = winRateChart(data.holdout);
  $("mae-chart").innerHTML = maeChart(data.holdout);
  const label = $("live-label");
  if (label) label.textContent = card.lock_label || "2026 live record";
  const meta = $("live-meta");
  if (meta && card.holdout_note) meta.textContent = card.holdout_note;
}

const page = document.body.dataset.page;
const run = {
  home: renderHome,
  ledger: renderLedger,
  teams: renderTeams,
  freshness: renderFreshness,
  model: renderModel,
}[page];
if (run) {
  run().catch((err) => {
    const slot = $("health") || $("when") || $("ratings-caption") || document.querySelector("main");
    if (slot) slot.textContent = `Could not load the latest JSON (${err.message}).`;
  });
}
