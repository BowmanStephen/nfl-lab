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

const page = document.body.dataset.page;
const run = { home: renderHome, ledger: renderLedger, teams: renderTeams, freshness: renderFreshness }[page];
if (run) {
  run().catch((err) => {
    const slot = $("health") || $("when") || document.querySelector("main");
    if (slot) slot.textContent = `Could not load the latest JSON (${err.message}).`;
  });
}
