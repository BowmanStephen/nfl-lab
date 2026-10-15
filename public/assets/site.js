const $ = (id) => document.getElementById(id);

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

// One abbreviation on the page. Saved cards keep nflverse codes (the Rams are
// "LA"); readers see LAR, and the Chargers stay LAC. Every visible team code
// goes through displayTeam.
//
// The model page's rating rows use the short names "LA Rams" and "LA Chargers".
// displayTeam rewrites those labels too ("Los Angeles Rams" / "Los Angeles
// Chargers") so the chart does not print LA next to LAR. Display only: the
// ratings JSON still stores team "LA", which grading and line matching need.
const DISPLAY_TEAM = {
  LA: "LAR",
  "LA Rams": "Los Angeles Rams",
  "LA Chargers": "Los Angeles Chargers",
};

function displayTeam(code) {
  if (code == null) return "";
  const text = String(code);
  return Object.prototype.hasOwnProperty.call(DISPLAY_TEAM, text) ? DISPLAY_TEAM[text] : text;
}

function displaySpread(text) {
  const raw = String(text ?? "");
  const space = raw.indexOf(" ");
  if (space === -1) return displayTeam(raw);
  return displayTeam(raw.slice(0, space)) + raw.slice(space);
}

function fmt(n, digits = 1) {
  if (n == null || Number.isNaN(Number(n))) return "n/a";
  const v = Number(n);
  return (v > 0 ? "+" : "") + v.toFixed(digits);
}

function when(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    weekday: "short", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit", timeZone: "America/Chicago",
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

function marginPlain(homeMargin, home, away) {
  const m = Number(homeMargin);
  const homeLabel = displayTeam(home);
  const awayLabel = displayTeam(away);
  if (!Number.isFinite(m)) return "n/a";
  if (Math.abs(m) < 0.05) return "pick'em";
  if (m > 0) return `${homeLabel} by ${Math.abs(m).toFixed(1)}`;
  return `${awayLabel} by ${Math.abs(m).toFixed(1)}`;
}

// Spread from the given side's point of view (negative = that side gives points).
function sideLine(game, side) {
  const line = Number(game.pick_time.home_margin);
  return side === game.home_team ? -line : line;
}

// Swap ASCII hyphen-minus before a number for a real minus sign (−) in display text.
function minusSign(text) {
  return String(text).replace(/-(?=\d)/g, "\u2212");
}

function pickLineDisplay(game, side) {
  const signed = sideLine(game, side);
  return `${displayTeam(side)} ${fmt(signed)}`;
}

function compareBlock(lineLabel, lineValue, modelLabel, modelValue) {
  return `<div class="compare" aria-label="Our model versus Vegas">
    <div class="compare-col compare-line">
      <span>Vegas says</span>
      <b>${esc(lineValue)}</b>
      <em>${esc(lineLabel)}</em>
    </div>
    <div class="compare-col compare-model">
      <span>Our model says</span>
      <b>${esc(modelValue)}</b>
      <em>${esc(modelLabel)}</em>
    </div>
  </div>`;
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
      const pickPrice = pickLineDisplay(g, side);
      const notes = (s.qb_notes || []).map((n) => `<p class="note">${esc(n)}</p>`).join("");
      const edge = Math.abs(s.spread_edge);
      return `<article class="card pick-card">
        <header><strong>${esc(displayTeam(g.away_team))} at ${esc(displayTeam(g.home_team))}</strong><span class="meta">${esc(when(g.kickoff_utc))}</span></header>
        <p class="side">${esc(pickPrice)}</p>
        ${compareBlock(
          `home margin ${fmt(line)}`,
          displaySpread(g.pick_time.spread_display || fmt(line)),
          `home margin ${fmt(s.model_margin)}`,
          marginPlain(s.model_margin, g.home_team, g.away_team),
        )}
        <p class="edge-line"><span>Gap</span><b>${fmt(edge)}</b><em>pts toward ${esc(displayTeam(side))}</em></p>
        <p class="meta">Line saved ${esc(whenCT(g.pick_time.captured_at))}, ${esc(g.pick_time.provider)}</p>
        <p class="meta">Starting QBs: ${esc(displayTeam(g.away_team))} ${esc(s.away_qb)}, ${esc(displayTeam(g.home_team))} ${esc(s.home_qb)}</p>
        ${notes}
      </article>`;
    }).join("");
}

function totalIsActive(selection) {
  return Boolean(selection.total_qualifies) && !selection.total_voided;
}

const TOTALS_PAUSED_NOTE = "We're not picking total points (over/under) right now while we fix that part of the model.";

function totalsVoidNotice(card) {
  const note = card.totals_void_note || "";
  const originalWeek6Note = "The 6 week-6 over/under picks were voided Oct 15: the over/under model went 6-18 on weeks 1-4, so we've paused over/unders. The spread picks stand.";
  if (card.season === 2026 && card.week === 6 && note === originalWeek6Note) {
    return "The 6 week-6 over/under picks were voided Oct 15, and over/unders are paused. "
      + "A replay of weeks 1-4 with the corrected totals formula went 6-18. "
      + "The original frozen-model record remains 10-19; the replay does not replace it. "
      + "The spread picks stand.";
  }
  return note;
}

// The week-6 void note already says over/unders are paused. A second sentence
// would repeat it. Future cards set totals_paused and have no void note.
function totalsPauseApplies(card) {
  if (!card || card.totals_void_note) return false;
  if (card.totals_paused) return true;
  return (card.games || []).some((g) => g.selection && totalIsActive(g.selection));
}

function showTotalsPause(card) {
  const paused = $("totals-paused");
  if (!paused) return;
  if (totalsPauseApplies(card)) {
    paused.hidden = false;
    paused.textContent = TOTALS_PAUSED_NOTE;
  } else {
    paused.hidden = true;
    paused.textContent = "";
  }
}

function totalCards(games) {
  return games
    .filter((g) => totalIsActive(g.selection))
    .sort((a, b) => Math.abs(b.selection.total_edge) - Math.abs(a.selection.total_edge))
    .map((g) => {
      const s = g.selection;
      const tot = Number(g.pick_time.total);
      const modelTot = Number(s.model_total);
      const edge = Math.abs(s.total_edge);
      const sideLabel = `${s.total_pick} ${tot.toFixed(1)}`;
      return `<article class="card pick-card">
        <header><strong>${esc(displayTeam(g.away_team))} at ${esc(displayTeam(g.home_team))}</strong><span class="meta">${esc(when(g.kickoff_utc))}</span></header>
        <p class="side">${esc(sideLabel)}</p>
        ${compareBlock(
          `Vegas total ${tot.toFixed(1)}`,
          tot.toFixed(1),
          `Our total ${modelTot.toFixed(1)}`,
          modelTot.toFixed(1),
        )}
        <p class="edge-line"><span>Gap</span><b>${fmt(edge)}</b><em>pts, ${esc(s.total_pick)}</em></p>
      </article>`;
    }).join("");
}

function noPickReason(game) {
  const s = game.selection;
  if (s.total_voided && !s.spread_qualifies) {
    const recorded = `${s.total_pick} ${Number(game.pick_time.total).toFixed(1)}`;
    return `We had ${recorded} on the total. It was voided and is not scored.`;
  }
  if (s.no_pick_reason) return s.no_pick_reason;
  return `No pick. Our model was ${Math.abs(s.spread_edge).toFixed(1)} points from Vegas on the margin (a pick needs 2) and ${Math.abs(s.total_edge).toFixed(1)} on the total (a pick needs 3).`;
}

function noPickCards(games) {
  return games
    .filter((g) => !g.selection.spread_qualifies && !totalIsActive(g.selection))
    .map((g) => {
      const s = g.selection;
      const label = s.total_voided ? "Voided total" : "No pick";
      return `<article class="card quiet-card">
        <header><strong>${esc(displayTeam(g.away_team))} at ${esc(displayTeam(g.home_team))}</strong><span class="meta">${esc(label)}</span></header>
        <p>${esc(noPickReason(g))}</p>
        <div class="nums nums-compact">
          <div><span>Spread gap</span><b>${fmt(s.spread_edge)}</b></div>
          <div><span>Total gap</span><b>${fmt(s.total_edge)}</b></div>
        </div>
      </article>`;
    }).join("");
}

function showLock(card) {
  const label = $("lock-label");
  if (label && card.lock_label) label.textContent = card.lock_label;
  const note = $("holdout-note");
  if (note && card.holdout_note) {
    note.textContent = card.holdout_note;
  }
  const voidNote = $("totals-void-note");
  if (voidNote) {
    if (card.totals_void_note) {
      voidNote.hidden = false;
      voidNote.textContent = totalsVoidNotice(card);
    } else {
      voidNote.hidden = true;
    }
  }
  const closeNote = $("close-fallback-note");
  if (closeNote) {
    if (card.close_fallback_note) {
      closeNote.hidden = false;
      closeNote.textContent = card.close_fallback_note;
    } else {
      closeNote.hidden = true;
    }
  }
}

function liveRecordLine(health) {
  if (!health) return "The 2026 record is unavailable.";
  if (!health.settled_picks) {
    return "No 2026 picks have been graded yet.";
  }
  const rate = health.cover_rate == null ? "" : ` (${(100 * health.cover_rate).toFixed(1)}%)`;
  return `The 2026 record so far is ${health.wins}-${health.losses}-${health.pushes}${rate}.`;
}

/* Home: one row per game. Build spec: critiques/nfl-lab/home-nav-build-spec.md */
const AGREE_WITHIN = 1.0; // display split only, not a data field
const HOUR = 3600 * 1000;
let homeNames = {};

function nowMs() {
  const q = new URLSearchParams(location.search).get("now");
  const t = q ? Date.parse(q) : NaN;
  return Number.isFinite(t) ? t : Date.now();
}

function fullName(abbr) { return homeNames[abbr] || displayTeam(abbr); }

function kickoffCT(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-US", {
    weekday: "short", hour: "numeric", minute: "2-digit", timeZone: "America/Chicago",
  }).replace(",", "") + " CT";
}

function timeTag(iso) {
  return `<time datetime="${esc(iso)}">${esc(kickoffCT(iso))}</time>`;
}

function vegasFavored(g) {
  const d = String((g.pick_time && g.pick_time.spread_display) || "");
  const team = d.split(" ")[0];
  if (team === g.home_team || team === g.away_team) return team;
  return Number(g.pick_time && g.pick_time.home_margin) > 0 ? g.home_team : g.away_team;
}

function modelPlain(g) {
  return marginPlain(g.selection.model_margin, fullName(g.home_team), fullName(g.away_team));
}

function homeSentence(g) {
  const s = g.selection;
  const pick = s.spread_pick;
  const mm = Number(s.model_margin);
  const modelFav = mm > 0 ? g.home_team : g.away_team;
  let x;
  if (pick && pick !== vegasFavored(g)) {
    x = modelFav === pick ? `${fullName(pick)} wins` : `${fullName(pick)} keeps it within ${Math.abs(mm).toFixed(1)}`;
  } else {
    x = modelPlain(g);
  }
  return `Our model says ${x}. Vegas says ${minusSign(displaySpread(g.pick_time.spread_display))}.`;
}

function pageState(card, fresh, now) {
  if (!card.games.length) return "empty";
  const kicks = card.games.map((g) => Date.parse(g.kickoff_utc));
  const scored = (g) => g.grading && g.grading.home_score != null;
  if (card.games.every(scored)) return "final";
  if (now < Math.min(...kicks)) return "pre";
  if (kicks.every((k) => k + 4 * HOUR < now)) return "awaiting";
  return "live";
}

function teamsLabel(g) {
  return `<span class="teams" aria-label="${esc(fullName(g.away_team))} at ${esc(fullName(g.home_team))}"><span class="chip">${esc(displayTeam(g.away_team))}</span> <span class="at" aria-hidden="true">@</span> <span class="chip">${esc(displayTeam(g.home_team))}</span></span>`;
}

function savedCT(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-US", {
    weekday: "short", hour: "numeric", minute: "2-digit", timeZone: "America/Chicago",
  }).replace(",", "") + " CT";
}

function detailList(g, withGap) {
  const s = g.selection;
  const rows = [
    ["Vegas says", `${displaySpread(g.pick_time.spread_display)} (saved ${savedCT(g.pick_time.captured_at_ct || g.pick_time.captured_at)})`],
    ["Our model says", modelPlain(g)],
  ];
  if (withGap) {
    rows.push(["How this pick wins", spreadResult(g)]);
    rows.push(["Model's gap vs Vegas", `${Math.abs(Number(s.spread_edge)).toFixed(1)} points toward ${fullName(s.spread_pick)}`]);
    rows.push(["Lean label", `${leanLabel(g)} means a model-versus-line gap ${Math.abs(Number(s.spread_edge)) >= STRONG_LEAN_EDGE ? `of ${STRONG_LEAN_EDGE} points or more` : `below ${STRONG_LEAN_EDGE} points`}.`]);
  }
  if (g.pre_kickoff && g.pre_kickoff.spread_display) rows.push(["Line before kickoff", displaySpread(g.pre_kickoff.spread_display)]);
  if (s.away_qb || s.home_qb) rows.push(["Quarterbacks", `${displayTeam(g.away_team)} ${s.away_qb || "not listed"} · ${displayTeam(g.home_team)} ${s.home_qb || "not listed"}`]);
  if (s.total_voided) rows.push(["Over/under", `Over/under pick pulled (${s.total_pick} ${Number(g.pick_time.total).toFixed(1)})`]);
  const notes = s.qb_notes || [];
  const qb = notes.length
    ? `<p class="small">QB note: ${esc(notes[0])}</p>${notes.length > 1 ? `<details class="more"><summary>More</summary>${notes.slice(1).map((n) => `<p class="small">${esc(n)}</p>`).join("")}</details>` : ""}`
    : "";
  return `<dl class="row-detail">${rows.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd class="num">${esc(v)}</dd></div>`).join("")}</dl>${qb}`;
}

function resultPill(g) {
  let o = g.grading && g.grading.spread_outcome;
  if (!o && g.grading && g.grading.actual_margin != null) {
    // fallback: compare final home margin with the pick-time line
    const line = Number(g.pick_time.home_margin);
    const am = Number(g.grading.actual_margin);
    const homeCover = am - line;
    const pickHome = g.selection.spread_pick === g.home_team;
    o = Math.abs(homeCover) < 1e-9 ? "push" : ((homeCover > 0) === pickHome ? "win" : "loss");
  }
  if (o === "win") return '<span class="result-pill right" aria-label="Our pick won">✓ Win</span>';
  if (o === "loss") return '<span class="result-pill wrong" aria-label="Our pick lost">✗ Loss</span>';
  if (o === "push") return '<span class="result-pill tie" aria-label="Tie, landed on the line">= Tie (landed on the line)</span>';
  return "";
}

// Plain-words pick for the collapsed row, e.g. "Take PHI −1.5" (real minus sign);
// a zero line reads "Take PHI (pick'em)".
function takeParts(g) {
  const side = g.selection.spread_pick;
  const shown = displayTeam(side);
  const signed = sideLine(g, side);
  if (!Number.isFinite(signed) || signed === 0) {
    return { text: `Take ${shown} (pick'em)`, spoken: `Take ${shown} pick'em` };
  }
  const n = Math.abs(signed).toFixed(1);
  return signed < 0
    ? { text: `Take ${shown} \u2212${n}`, spoken: `Take ${shown} minus ${n}` }
    : { text: `Take ${shown} +${n}`, spoken: `Take ${shown} plus ${n}` };
}
function takeText(g) { return takeParts(g).text; }
function takeTag(g) {
  const t = takeParts(g);
  return `<span class="take num"><span class="take-pick" aria-hidden="true">${esc(t.text)}</span><span class="sr-only">${esc(t.spoken)}</span></span>`;
}

function spreadResult(g) {
  const raw = g.pick_time && g.pick_time.home_margin;
  if (raw == null || String(raw).trim() === "" || !Number.isFinite(Number(raw))) {
    return "The saved spread is unavailable.";
  }
  const team = displayTeam(g.selection.spread_pick);
  const line = sideLine(g, g.selection.spread_pick);
  const points = Math.abs(line);
  if (line === 0) return `${team} must win. A tied game is a push, counted as neither a win nor a loss.`;
  if (line < 0) {
    const needed = Math.floor(points) + 1;
    return `${team} must win by ${needed} or more points.${Number.isInteger(points) ? ` A ${points}-point win is a push, counted as neither a win nor a loss.` : ""}`;
  }
  const allowed = Math.ceil(points) - 1;
  return `${team} can ${allowed > 0 ? `win, tie, or lose by up to ${allowed} ${allowed === 1 ? "point" : "points"}` : "win or tie"}.${Number.isInteger(points) ? ` A ${points}-point loss is a push, counted as neither a win nor a loss.` : ""}`;
}

function disclosureCue() {
  return '<span class="disclosure-cue"><span class="show-details">Show details</span><span class="hide-details">Hide details</span><svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true" focusable="false"><path d="m3 5 4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></span>';
}

function expander(g, cls, sentence, extra, detail, lead = "") {
  const id = String(g.game_id).replace(/[^\w-]/g, "");
  return `<li class="game-row ${cls}" id="b-${id}" tabindex="-1">
    <button class="row-toggle" id="toggle-${id}" aria-expanded="false" aria-controls="d-${id}">
${lead ? `      ${lead}\n` : ""}      <span class="row-top">${teamsLabel(g)}<span class="when">${extra}</span></span>
      <span class="call">${esc(sentence)}</span>
      ${disclosureCue()}
    </button>
    <div class="row-panel" id="d-${id}" role="region" aria-labelledby="toggle-${id}" hidden>${detail}</div>
  </li>`;
}

function isScored(g) {
  return Boolean(g.grading && g.grading.home_score != null && g.grading.away_score != null);
}

function scoreTag(g) {
  const gr = g.grading;
  return `<span class="final-score num">Final: ${esc(displayTeam(g.away_team))} ${esc(gr.away_score)} · ${esc(displayTeam(g.home_team))} ${esc(gr.home_score)}</span>`;
}

// Final score, "In progress", or the kickoff time in CT, from the saved card.
function statusTag(g, now) {
  if (isScored(g)) return scoreTag(g);
  const kick = Date.parse(g.kickoff_utc);
  if (Number.isFinite(kick) && kick <= now) {
    return kick + 4 * HOUR < now
      ? '<span class="tag">Final score coming</span>'
      : '<span class="tag">In progress</span>';
  }
  return timeTag(g.kickoff_utc);
}

// Display-only confidence label. Rule: |spread gap| >= 3.5 points (about a 60%
// modeled cover chance at the 13.38-point margin sigma) is a "strong lean";
// any other locked pick is a "lean". Does not change the pick or the data.
// Single source of truth for the cutoff; used by home, previews, and track record.
const STRONG_LEAN_EDGE = 3.5;
function leanLabel(g) {
  return Math.abs(Number(g.selection.spread_edge)) >= STRONG_LEAN_EDGE ? "Strong lean" : "Lean";
}
function leanTag(g) {
  const label = leanLabel(g);
  return `<span class="${label === "Strong lean" ? "lean strong" : "lean"}">${esc(label)}</span>`;
}

function gameRow(g, state, now) {
  if (state === "final" || isScored(g)) return finalRow(g);
  const started = statusTag(g, now) === timeTag(g.kickoff_utc) ? "" : ` ${statusTag(g, now)}`;
  const price = pickLineDisplay(g, g.selection.spread_pick);
  return expander(g, "pick-row", homeSentence(g),
    `${started ? started.trim() : timeTag(g.kickoff_utc)} ${leanTag(g)}`,
    `<p class="pick num">Pick: ${esc(price)}</p>${detailList(g, true)}`, takeTag(g));
}

function finalRow(g) {
  const gr = g.grading;
  const price = pickLineDisplay(g, g.selection.spread_pick);
  const am = Number(gr.actual_margin ?? (gr.home_score - gr.away_score));
  const winner = am === 0 ? null : (am > 0 ? g.home_team : g.away_team);
  const sentence = `We had ${fullName(g.selection.spread_pick)} ${price.split(" ").slice(1).join(" ")}. ${winner ? `${fullName(winner)} won by ${Math.abs(am)}.` : "It ended in a tie."}`;
  return expander(g, "pick-row final", sentence,
    `${scoreTag(g)} ${resultPill(g)}`,
    detailList(g, true));
}

function tooCloseRow(g, now = Date.now()) {
  const pulled = g.selection.total_voided
    ? ` Over/under pick pulled (${g.selection.total_pick} ${Number(g.pick_time.total).toFixed(1)}).`
    : "";
  return expander(g, "quiet", `Too close to call. Vegas says ${displaySpread(g.pick_time.spread_display)}; our model says ${modelPlain(g)}.${pulled}`,
    statusTag(g, now), detailList(g, false));
}

function agreeGroup(games, now = Date.now()) {
  if (!games.length) return "";
  const items = games.map((g) => {
    const id = String(g.game_id).replace(/[^\w-]/g, "");
    const pulled = g.selection.total_voided
      ? ` · Over/under pick pulled (${g.selection.total_pick} ${Number(g.pick_time.total).toFixed(1)})`
      : "";
    return `<li id="b-${id}" tabindex="-1">${esc(displayTeam(g.away_team))} @ ${esc(displayTeam(g.home_team))} · ${statusTag(g, now)} · Vegas ${esc(displaySpread(g.pick_time.spread_display))}, us ${esc(modelPlain(g))}${esc(pulled)}</li>`;
  }).join("");
  return `<li class="agree-group">
    <button class="row-toggle" id="b-agree" aria-expanded="false" aria-controls="d-agree"><span class="call">${games.length} games where we agree with Vegas</span>${disclosureCue()}</button>
    <div class="row-panel" id="d-agree" role="region" aria-labelledby="b-agree" hidden><ul>${items}</ul></div>
  </li>`;
}

function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function weekFromAnchor(id) {
  const match = /^b-\d{4}_(\d{2})_/.exec(id);
  return match ? Number(match[1]) : 0;
}

function showMissedPick(id) {
  const week = weekFromAnchor(id);
  const notices = $("notices");
  if (!week || !notices || notices.querySelector(".missed-pick")) return;
  const note = document.createElement("p");
  note.className = "missed-pick";
  note.setAttribute("role", "status");
  note.innerHTML = `That pick was from week ${week}, <a href="recaps/week${week}.html">see the recap →</a>`;
  notices.appendChild(note);
}

// Home "Our picks" are spread picks. A qualifying total is not one of them.
function isSpreadPick(g) {
  return Boolean(g.selection && g.selection.spread_qualifies);
}

function unplayedGame(g, now) {
  if (isScored(g)) return false;
  const kick = Date.parse(g.kickoff_utc);
  return Number.isFinite(kick) && kick > now;
}

// Keep the Up next row consistent with the site's shared team labels.
function upNextTeam(code) {
  return displayTeam(code);
}

function upNextMarkup(g) {
  const raw = String((g.pick_time && g.pick_time.spread_display) || "").trim();
  let vegas = "";
  if (raw) {
    const space = raw.indexOf(" ");
    const head = space === -1 ? raw : raw.slice(0, space);
    const rest = space === -1 ? "" : raw.slice(space);
    vegas = `Vegas says ${upNextTeam(head)}${rest}`;
  }
  const match = `${upNextTeam(g.away_team)} at ${upNextTeam(g.home_team)}`;
  const line = vegas ? `<span class="up-next-vegas">${esc(vegas)}</span>` : "";
  return `<p class="up-next-row"><span class="up-next-kicker">Up next</span><span class="up-next-game">${esc(match)}, ${timeTag(g.kickoff_utc)}</span>${line}</p>`;
}

function showUpNext(games, now) {
  const slot = $("up-next");
  if (!slot) return;
  const upcoming = games.filter((g) => unplayedGame(g, now))
    .sort((a, b) => Date.parse(a.kickoff_utc) - Date.parse(b.kickoff_utc));
  const next = upcoming[0];
  const kick = next ? Date.parse(next.kickoff_utc) : NaN;
  const sameKick = upcoming.filter((g) => Date.parse(g.kickoff_utc) === kick);
  if (!next || sameKick.some(isSpreadPick)) {
    slot.hidden = true;
    slot.innerHTML = "";
    return;
  }
  slot.hidden = false;
  slot.innerHTML = upNextMarkup(next);
}

function revealHash() {
  const id = (location.hash || "").slice(1);
  if (!id) return;
  let el = document.getElementById(id);
  if (!el) {
    showMissedPick(id);
    return;
  }
  const reduced = prefersReducedMotion();
  // Rows are built after load, so :target stays blank until the hash is applied again.
  if (!el.matches(":target")) {
    location.replace(location.pathname + location.search + location.hash);
    el = document.getElementById(id);
    if (!el) {
      showMissedPick(id);
      return;
    }
  }
  const panel = el.closest("[hidden]");
  if (panel) {
    panel.hidden = false;
    const btn = document.getElementById(panel.getAttribute("aria-labelledby") || "");
    if (btn) btn.setAttribute("aria-expanded", "true");
  }
  el.tabIndex = -1;
  el.scrollIntoView({ block: "center", behavior: reduced ? "auto" : "smooth" });
  el.focus({ preventScroll: true });
}

function bindToggles(root) {
  root.querySelectorAll(".row-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const open = btn.getAttribute("aria-expanded") === "true";
      btn.setAttribute("aria-expanded", String(!open));
      document.getElementById(btn.getAttribute("aria-controls")).hidden = open;
    });
  });
}

function showHomeError() {
  const main = $("main");
  main.innerHTML = `<div class="state-banner"><h1>We couldn't load this week's picks</h1><p>We couldn't load this week's picks. Try refreshing.</p><button type="button" class="retry" id="retry">Try again</button></div>`;
  $("retry").addEventListener("click", () => { location.reload(); });
}

async function recapExists(week, prefix = "") {
  try { const r = await fetch(`${prefix}recaps/week${week}.html`, { method: "HEAD" }); return r.ok; } catch { return false; }
}

async function previewExists(week) {
  try {
    const res = await fetch(`previews/week${week}.html`, { method: "HEAD" });
    return res.ok ? true : res.status === 404 ? false : null;
  } catch {
    return null;
  }
}

function previewLinkFor(week, pageExists) {
  if (pageExists) {
    return { href: `previews/week${week}.html`, text: `Read the week ${week} game previews` };
  }
  if (pageExists === false) {
    return { href: null, text: `Week ${week} previews are coming soon` };
  }
  return { href: null, text: `Week ${week} previews are temporarily unavailable. Try refreshing.` };
}

function renderPreviewLink(el, link) {
  if (!el || !link) return;
  if (link.href) {
    el.textContent = "";
    const a = document.createElement("a");
    a.href = link.href;
    a.textContent = link.text;
    el.appendChild(a);
    return;
  }
  el.textContent = link.text;
}

async function renderHome() {
  let card;
  let fresh = {};
  try {
    const [c, f, teams] = await Promise.all([
      load("picks.json"),
      load("freshness.json").catch(() => ({})),
      load("teams.json").catch(() => ({ teams: [] })),
    ]);
    card = c; fresh = f;
    homeNames = Object.fromEntries((teams.teams || []).map((t) => [t.team, t.name]));
  } catch (err) {
    showHomeError();
    return;
  }
  const now = nowMs();
  const state = pageState(card, fresh, now);
  const games = card.games.slice().sort((a, b) => Date.parse(a.kickoff_utc) - Date.parse(b.kickoff_utc));
  const picks = games.filter((g) => g.selection.spread_qualifies);
  const close = games.filter((g) => !g.selection.spread_qualifies && Math.abs(Number(g.selection.spread_edge)) >= AGREE_WITHIN);
  const agree = games.filter((g) => !g.selection.spread_qualifies && Math.abs(Number(g.selection.spread_edge)) < AGREE_WITHIN);
  const help = $("picks-help");
  if (help) help.hidden = !picks.length || state === "final";

  $("kicker").textContent = `Week ${card.week} · ${card.season}`;
  const h1 = {
    pre: `Week ${card.week}: who we think wins`,
    live: `Week ${card.week}: games underway`,
    awaiting: `Week ${card.week} is over`,
    final: `Week ${card.week} is final`,
    empty: `Week ${card.week}: who we think wins`,
  }[state];
  $("home-title").textContent = h1;
  document.title = `NFL Lab: ${h1}`;
  const provider = (games[0] && games[0].pick_time && games[0].pick_time.provider) || "DraftKings";
  $("updated").textContent = fresh.generated_at
    ? `Updated ${savedCT(fresh.generated_at)} · Lines from ${provider}`
    : `Lines from ${provider}`;

  const notices = [];
  if (fresh.stale_after && Date.parse(fresh.stale_after) < now) {
    notices.push(`<p class="notice">This page hasn't updated since ${esc(savedCT(fresh.generated_at))}.</p>`);
  }
  if (state === "awaiting") notices.push('<p class="notice">Results are being graded. Check back soon.</p>');
  $("notices").innerHTML = notices.slice(0, 2).join("");
  showUpNext(games, now);
  const voidNote = $("totals-void-note");
  if (voidNote) {
    if (card.totals_void_note) {
      voidNote.hidden = false;
      voidNote.textContent = totalsVoidNotice(card);
    } else {
      voidNote.hidden = true;
    }
  }

  if (state === "final") {
    let w = 0, l = 0, p = 0;
    picks.forEach((g) => { const o = resultPill(g); if (o.includes("right")) w++; else if (o.includes("wrong")) l++; else if (o) p++; });
    const recap = await recapExists(card.week);
    $("final-line").innerHTML = `Our picks went ${w}-${l}${p ? `-${p}` : ""}. ${recap ? `<a href="recaps/week${card.week}.html">See week ${card.week} recap →</a> ` : ""}Week ${card.week + 1} picks are coming.`;
    $("final-line").hidden = false;
  }

  if (state === "empty") {
    $("games").innerHTML = `<li class="empty-row"><p>No games on the card yet for week ${card.week}.</p></li>`;
    $("picks-h").hidden = true; $("close-h").hidden = true;
  } else {
    $("picks-h").textContent = `Our picks (${picks.length})`;
    $("games").innerHTML = picks.map((g) => gameRow(g, state, now)).join("");
    $("close-h").textContent = `Too close to call (${close.length})`;
    $("close-h").hidden = !close.length;
    $("close-games").innerHTML = close.map((g) => tooCloseRow(g, now)).join("") + agreeGroup(agree, now);
  }
  showTotalsPause(card);
  const prev = $("previews-link");
  if (prev) {
    previewExists(card.week).then((exists) => {
      renderPreviewLink(prev, previewLinkFor(card.week, exists));
    });
  }
  bindToggles($("main"));
  revealHash();
}

function record(r) {
  if (!r || r.win_rate == null) return "n/a";
  return `${r.wins}-${r.losses}-${r.pushes} (${(100 * r.win_rate).toFixed(1)}%)`;
}


// Track record. Saved picks are every official card in saved_weeks.json, from
// week 5 on. Unplayed games and open picks are the current week only, so a
// finished week cannot change the "still to play" counts.
function annotateTrackGame(g) {
  const played = g.home_score != null && g.away_score != null;
  let result = "pending";
  if (played) {
    const actual = g.home_score - g.away_score;
    if (actual === 0) result = "tie";
    else if (!g.margin) result = "nocall";
    else result = (actual > 0) === (g.margin > 0) ? "right" : "wrong";
  }
  return { ...g, said: g.margin > 0 ? g.home : g.away, result };
}

function savedTrackGames(saved) {
  const games = [];
  for (const week of (saved && saved.weeks) || []) {
    for (const g of week.games || []) {
      games.push(annotateTrackGame({
        week: g.week, gameday: g.gameday || null, away: g.away_team, home: g.home_team,
        margin: g.model_margin, home_score: g.home_score, away_score: g.away_score, live: true,
        spread_qualifies: Boolean(g.spread_qualifies), spread_outcome: g.spread_outcome ?? null,
        total_active: Boolean(g.total_active), total_outcome: g.total_outcome ?? null,
      }));
    }
  }
  return games;
}

// Older saved-week payloads predate explicit pause metadata.
function totalsPauseNote() {
  return typeof TOTALS_PAUSED_NOTE === "string" ? TOTALS_PAUSED_NOTE : "";
}

function totalsArePaused(saved, note) {
  const currentWeek = saved && saved.current_week;
  const weeks = (saved && saved.weeks) || [];
  const week = weeks.find((w) => w.week === currentWeek);
  if (week && Object.prototype.hasOwnProperty.call(week, "totals_paused")) {
    return Boolean(week.totals_paused);
  }
  const signal = note === undefined ? totalsPauseNote() : note;
  if (!signal) return false;
  return ((week && week.games) || []).some((g) => g.total_active);
}

function piece(n, singular, plural) {
  return `${n} ${n === 1 ? singular : plural}`;
}

function remainingSentence(rem, totalsPaused) {
  const showTotals = !totalsPaused;
  if (rem.week == null || (!rem.games && !rem.spreads && (totalsPaused || !rem.totals))) return "";
  const games = piece(rem.games, "game", "games");
  const spreads = piece(rem.spreads, "locked spread", "locked spreads");
  const riding = rem.games === 1 ? "it" : "them";
  if (!showTotals) {
    return `Week ${rem.week}: ${games} to go, with ${spreads} riding on ${riding}.`;
  }
  const totals = piece(rem.totals, "locked total", "locked totals");
  return `Week ${rem.week}: ${games} to go, with ${spreads} and ${totals} riding on ${riding}.`;
}

function buildTrackRecord(rc, saved, options) {
  const savedGames = savedTrackGames(saved);
  const savedWeeks = new Set(savedGames.map((g) => g.week));
  const look = [];
  for (const g of (rc && rc.games) || []) {
    if (savedWeeks.has(g.week)) continue;
    look.push(annotateTrackGame({
      week: g.week, gameday: g.gameday || null, away: g.away_team, home: g.home_team,
      margin: g.proj_margin, home_score: g.home_score, away_score: g.away_score, live: false,
      spread_qualifies: false, spread_outcome: null, total_active: false, total_outcome: null,
    }));
  }
  const games = [...look, ...savedGames];
  const count = (list, r) => list.filter((g) => g.result === r).length;
  const right = count(savedGames, "right");
  const wrong = count(savedGames, "wrong");
  const decided = right + wrong;
  const pct = decided ? `${Math.round((100 * right) / decided)}%` : "none yet";
  const outcome = (r) => savedGames.filter((g) => g.spread_qualifies && g.spread_outcome === r).length;
  const sw = outcome("win"), sl = outcome("loss"), sp = outcome("push");
  const currentWeek = saved && saved.current_week != null ? saved.current_week : null;
  const current = savedGames.filter((g) => g.week === currentWeek);
  const unplayed = (g) => g.home_score == null || g.away_score == null;
  const remaining = {
    week: currentWeek,
    games: current.filter(unplayed).length,
    spreads: current.filter((g) => g.spread_qualifies && !g.spread_outcome).length,
    totals: current.filter((g) => g.total_active && !g.total_outcome).length,
  };
  const totalsPaused = options && Object.prototype.hasOwnProperty.call(options, "totalsPaused")
    ? Boolean(options.totalsPaused)
    : totalsArePaused(saved);
  const still = remainingSentence(remaining, totalsPaused);
  const weeks = new Map();
  for (const g of games) {
    if (!weeks.has(g.week)) weeks.set(g.week, { week: g.week, live: g.live, right: 0, wrong: 0, ties: 0, pending: 0, games: [] });
    const w = weeks.get(g.week);
    w.games.push(g);
    if (g.result === "right") w.right += 1;
    else if (g.result === "wrong") w.wrong += 1;
    else if (g.result === "tie") w.ties += 1;
    else w.pending += 1;
  }
  const liveWeeks = [...new Set(savedGames.map((g) => g.week))].sort((a, b) => a - b);
  const testWeeks = [...new Set(look.map((g) => g.week))].sort((a, b) => a - b);
  const bits = [];
  if (liveWeeks.length) bits.push(`Both tiles count only picks saved before kickoff. That starts in week ${liveWeeks[0]}.`);
  const ties = count(savedGames, "tie");
  if (ties) bits.push(`${ties} tie${ties > 1 ? "s are" : " is"} left out because nobody won.`);
  if (still) bits.push(still);
  if (testWeeks.length) {
    const lr = count(look, "right");
    const ln = lr + count(look, "wrong");
    bits.push(`Weeks ${testWeeks[0]} to ${testWeeks[testWeeks.length - 1]} are a look back. Those picks were not posted ahead of time. The model got ${lr} of ${ln} right.`);
  }
  return {
    winner: {
      num: `${right} of ${decided}`,
      gloss: decided ? `${pct} right. Did the team the model had ahead win?` : "Did the team the model had ahead win?",
    },
    spread: {
      num: `${sw}-${sl}-${sp}`,
      gloss: still ? `Did the pick beat the betting line? ${still}` : "Did the pick beat the betting line?",
    },
    scope: bits.join(" "),
    remaining,
    weeks: [...weeks.values()].sort((a, b) => a.week - b.week),
  };
}

async function renderTrackRecord() {
  const [rc, saved] = await Promise.all([load("report_card.json"), load("saved_weeks.json")]);
  const nick = (t) => (rc.names && rc.names[t]) || t;
  const view = buildTrackRecord(rc, saved);
  const weeks = view.weeks;
  const tile = (label, num, gloss) =>
    `<div class="tr-tile"><p class="label">${label}</p><p class="num">${num}</p><p class="tile-gloss">${gloss}</p></div>`;
  $("tr-tiles").innerHTML =
    tile("Picked the winner", view.winner.num, view.winner.gloss) +
    tile("Against the spread", view.spread.num, view.spread.gloss);
  $("tr-scope").textContent = view.scope;

  $("tr-strip").innerHTML = weeks.slice(-5).map((w) => {
    const n = w.right + w.wrong;
    const ok = n && w.right / n > 0.5;
    const cls = n ? (ok ? "ok" : "no") : "";
    const sym = n ? (ok ? "✓" : "✗") : "·";
    const said = n ? `${w.right} of ${n} right` : "not played yet";
    const tag = w.live ? "saved before kickoff" : "look back";
    return `<li class="${cls}"><span class="wk">Week ${w.week}</span><span class="sym" aria-hidden="true">${sym}</span>${said}<span class="tag">${tag}</span></li>`;
  }).join("");

  const date = (d) => d ? new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }) : "";
  $("tr-games").innerHTML = [...weeks].reverse().map((w) => {
    const rows = w.games.map((g) => {
      const hs = g.home_score, as = g.away_score;
      let line, pill;
      if (g.result === "pending") {
        line = `Our model says ${esc(nick(g.said))}. ${esc(nick(g.away))} at ${esc(nick(g.home))} has not been played yet.`;
        pill = `<span class="pill even">Not played yet</span>`;
      } else if (g.result === "nocall") {
        line = `Our model called ${esc(nick(g.away))} at ${esc(nick(g.home))} even.`;
        pill = `<span class="pill even">No call</span>`;
      } else if (g.result === "tie") {
        line = `Our model said ${esc(nick(g.said))}. ${esc(nick(g.away))} and ${esc(nick(g.home))} tied ${hs}-${as}.`;
        pill = `<span class="pill even">= Tie</span>`;
      } else {
        const homeWon = hs > as;
        const winner = homeWon ? g.home : g.away;
        const loser = homeWon ? g.away : g.home;
        line = `Our model said ${esc(nick(g.said))}. <b>${esc(nick(winner))}</b> beat ${esc(nick(loser))} ${Math.max(hs, as)}-${Math.min(hs, as)}.`;
        pill = g.result === "right" ? `<span class="pill ok">✓ Right</span>` : `<span class="pill no">✗ Wrong</span>`;
      }
      return `<div class="tr-game"><p><span class="date">${esc(date(g.gameday))}</span>${line}</p>${pill}</div>`;
    }).join("");
    return `<section class="tr-week"><h3>Week ${w.week}${w.live ? "" : " · look back"}</h3>${rows}</section>`;
  }).join("");
}

async function renderLedger() {
  await renderTrackRecord();
  const [base, card] = await Promise.all([load("baseline.json"), load("picks.json")]);
  $("spread-rec").textContent = record(base.spread);
  $("total-rec").textContent = record(base.total);
  $("seasons").innerHTML = base.per_season.map((row) =>
    `<tr><td>${row.season}</td><td>${record(row.spread)}</td><td>${record(row.total)}</td></tr>`
  ).join("");
  showLock(card);
  $("live-health").textContent = card.health.line;
  const picks = card.games.filter((g) => g.selection.spread_qualifies || totalIsActive(g.selection));
  $("live").innerHTML = picks.map((g) => {
    const s = g.selection;
    const bits = [];
    if (s.spread_qualifies) bits.push(`${displayTeam(s.spread_pick)}, ${Math.abs(s.spread_edge).toFixed(1)} pts off the spread (${leanLabel(g)})`);
    if (totalIsActive(s)) bits.push("over/under paused");
    return `<tr><td>${esc(displayTeam(g.away_team))} at ${esc(displayTeam(g.home_team))}</td><td>${esc(bits.join("; "))}</td><td>${esc(whenCT(g.pick_time.captured_at))}</td></tr>`;
  }).join("");
  showTotalsPause(card);
}

async function renderTeams() {
  const data = await load("teams.json");
  $("through").textContent = `2026 regular season through week ${data.through_week}.`;
  $("teams").innerHTML = data.teams.map((t, i) => `
    <article class="team" id="${esc(t.team)}">
      <div>
        <strong>${i + 1}. ${esc(t.name)}</strong>
        <div class="meta">${esc(displayTeam(t.team))}, rating ${fmt(t.rating, 3)}</div>
        ${spark(t.weekly)}
      </div>
      <div class="bars">
        <div class="bar-row"><span>Off</span>${epaBar(t.off_epa, "")}<b>${fmt(t.off_epa, 3)}</b></div>
        <div class="bar-row"><span>Def</span>${epaBar(-(t.def_epa || 0), "def")}<b>${fmt(t.def_epa, 3)}</b></div>
        <div class="meta">Offense success rate ${t.off_success == null ? "n/a" : (100 * t.off_success).toFixed(1)}%</div>
      </div>
    </article>`).join("");
}

async function renderFreshness() {
  const data = await load("freshness.json");
  const stale = data.stale_after && new Date(data.stale_after).getTime() < Date.now();
  if (stale) {
    $("stale").hidden = false;
    $("stale").textContent = "This data is out of date. The last refresh was more than 36 hours ago.";
  }
  const stamp = savedCT(data.generated_at);
  $("when").textContent = stamp ? `Updated ${stamp}` : "Updated";
}


function fmtPct(rate) {
  return `${(100 * rate).toFixed(1)}%`;
}

function pointsLabel(value) {
  const shown = Number(value.toFixed(1));
  if (shown === 0) return "0.0";
  return `${shown > 0 ? "+" : ""}${shown.toFixed(1)}`;
}

function powerChart(ratings) {
  // HTML rows instead of a scaled SVG, so team labels stay a readable size on phones.
  // points_rating is the weeks 5 to 8 scoring-margin scale (positive = points above average).
  const ranked = ratings.slice().sort((a, b) => b.points_rating - a.points_rating || a.team.localeCompare(b.team));
  const peak = Math.max(...ranked.map((r) => Math.abs(r.points_rating)));
  const step = peak <= 6 ? 3 : 4;
  const maxAbs = Math.max(6, Math.ceil(peak / step) * step);
  const pos = (pts) => 50 + (pts / maxAbs) * 50;
  const ticks = [];
  for (let t = -maxAbs; t <= maxAbs + 0.01; t += step) ticks.push(t);
  const tickMarks = ticks.map((t) => `<i class="tick${t === 0 ? " zero" : ""}" style="left:${pos(t).toFixed(2)}%"></i>`).join("");
  const rows = ranked.map((r) => {
    const pts = r.points_rating;
    const left = Math.min(50, pos(pts));
    const width = Math.max(0.4, Math.abs(pos(pts) - 50));
    const value = pointsLabel(pts);
    return `<li class="pw-row">
      <span class="pw-team" aria-hidden="true">${esc(displayTeam(r.team))}</span>
      <span class="pw-track" aria-hidden="true">${tickMarks}<i class="pw-bar ${pts >= 0 ? "up" : "down"}" style="left:${left.toFixed(2)}%;width:${width.toFixed(2)}%"></i></span>
      <span class="pw-val"><span class="sr">${esc(displayTeam(r.name || r.team))} </span>${value}</span>
    </li>`;
  }).join("");
  const scale = ticks.map((t) => `<span style="left:${pos(t).toFixed(2)}%">${t > 0 ? "+" : ""}${t}</span>`).join("");
  return `<ol class="power" aria-label="Team ratings in points, best to worst. Positive means better than an average team.">${rows}</ol>
    <div class="pw-axis" aria-hidden="true"><span></span><div class="pw-axis-scale">${scale}<span class="dir worse">worse</span><span class="dir better">better</span></div><span></span></div>`;
}

function gameScale(market, model) {
  const maxAbs = Math.max(12, Math.abs(market), Math.abs(model)) + 1;
  const pos = (v) => (((v + maxAbs) / (2 * maxAbs)) * 100).toFixed(2);
  // the line is an outline ring, the model a solid ink dot; drawn market under, model on top
  return `<div class="gs" aria-hidden="true">
    <div class="gs-rail"><i class="gs-zero" style="left:${pos(0)}%"></i><i class="gs-dot market" style="left:${pos(market)}%"></i><i class="gs-dot model" style="left:${pos(model)}%"></i></div>
    <div class="gs-ends"><span>away</span><span>home</span></div>
  </div>`;
}

function gamesChart(games) {
  return games.map((g) => {
    const away = displayTeam(g.away);
    const home = displayTeam(g.home);
    const pickBits = [];
    if (g.spread_pick) pickBits.push(displaySpread(g.spread_pick));
    if (g.total_pick) pickBits.push(g.total_pick.replace("OVER", "Over").replace("UNDER", "Under"));
    const edgeBits = [];
    if (g.spread_pick) edgeBits.push(`${Math.abs(g.spread_edge).toFixed(1)} pts off the Vegas spread`);
    if (g.total_pick) edgeBits.push(`${Math.abs(g.total_edge).toFixed(1)} pts off the Vegas total`);
    let tag = "No pick";
    if (g.is_pick) tag = pickBits.join(", ") || "Pick";
    else if (g.total_voided) tag = "Voided total";
    // market_margin_home is the home spread (negative = home favored); flip it to a home margin for plotting
    const mktHome = -g.market_margin_home;
    const byLine = (m) => Math.abs(m) < 0.05 ? "even" : `${displayTeam(m > 0 ? g.home : g.away)} by ${Math.abs(m).toFixed(1).replace(/\.0$/, "")}`;
    const sub = g.is_pick && edgeBits.length ? edgeBits.join(", ") : `Vegas says ${byLine(mktHome)}, our model says ${byLine(g.model_margin_home)}`;
    return `<div class="game-row${g.is_pick ? " is-pick" : ""}">
      <div class="match">${esc(away)} at ${esc(home)}<small>${esc(tag)}</small></div>
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
    { label: "Spreads", rate: holdout.spread_win_rate, detail: `${holdout.spread_wins}-${holdout.spread_losses}-${holdout.spread_pushes}` },
    { label: "Totals", rate: holdout.total_win_rate, detail: `${holdout.total_wins}-${holdout.total_losses}-${holdout.total_pushes}` },
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
      <rect class="${below ? "bar-miss" : "bar-fill"}" x="${x}" y="${top}" width="${barW}" height="${h}"/>
      <text class="val${h < 26 ? " out" : ""}" x="${x + barW / 2}" y="${h < 26 ? top - 8 : top + 20}" text-anchor="middle">${fmtPct(r.rate)}</text>
      <text class="label" x="${x + barW / 2}" y="${H - 18}" text-anchor="middle">${esc(r.label)}</text>
      <text class="axis" x="${x + barW / 2}" y="${H - 4}" text-anchor="middle">${esc(r.detail)}</text>`;
  }).join("");

  const label = rows.map((r) => `${r.label} ${fmtPct(r.rate)} (${r.detail})`).join(", ") + `. Break-even ${fmtPct(holdout.breakeven)}.`;
  return `<svg class="rate-bar" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}">
    <line class="break" x1="${padL}" y1="${breakY}" x2="${W - padR}" y2="${breakY}"/>
    <text class="axis" x="${W - padR}" y="${breakY - 6}" text-anchor="end">Break-even ${fmtPct(holdout.breakeven)}</text>
    <line class="base" x1="${padL}" y1="${padT + chartH}" x2="${W - padR}" y2="${padT + chartH}"/>
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
    { label: "Our model", val: holdout.model_mae_margin },
    { label: "Vegas", val: holdout.market_mae_margin },
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
      <rect class="${cls}" x="${x}" y="${top}" width="${barW}" height="${h}"/>
      <text class="val${h < 26 ? " out" : ""}" x="${x + barW / 2}" y="${h < 26 ? top - 8 : top + 20}" text-anchor="middle">${r.val.toFixed(2)}</text>
      <text class="label" x="${x + barW / 2}" y="${H - 14}" text-anchor="middle">${esc(r.label)}</text>`;
  }).join("");

  const label = `Average miss on final margin (pts): ${rows.map((r) => `${r.label} ${r.val.toFixed(2)}`).join(", ")}.`;
  return `<svg class="mae-bar" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}">
    <text class="axis" x="${padL}" y="14">Average miss on final margin (pts)</text>
    <line class="base" x1="${padL}" y1="${padT + chartH}" x2="${W - padR}" y2="${padT + chartH}"/>
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
      spreadPick = `${displayTeam(s.spread_pick)} ${text}`;
    }
    let totalPick = null;
    if (totalIsActive(s)) {
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
      total_voided: Boolean(s.total_voided),
      is_pick: Boolean(s.spread_qualifies || totalIsActive(s)),
    };
  });
}

async function renderModel() {
  const [data, card] = await Promise.all([load("model.json"), load("picks.json")]);
  $("ratings-caption").textContent =
    "Each rating is how many points better or worse than an average team we think a team is. We built it from scores through week 4, scaled for weeks 5 to 8.";
  $("ratings-chart").innerHTML = powerChart(data.ratings);
  $("games-chart").innerHTML = gamesChart(officialGames(card));
  const caption = $("week5-caption");
  if (caption && card.lock_label) {
    caption.textContent = `${card.lock_label}. We make a pick only when our model and Vegas differ by 2+ points on the margin or 3+ on the total.`;
  }
  const voidNote = $("totals-void-note");
  if (voidNote) {
    if (card.totals_void_note) {
      voidNote.hidden = false;
      voidNote.textContent = totalsVoidNotice(card);
    } else {
      voidNote.hidden = true;
    }
  }
  const closeNote = $("close-fallback-note");
  if (closeNote) {
    if (card.close_fallback_note) {
      closeNote.hidden = false;
      closeNote.textContent = card.close_fallback_note;
    } else {
      closeNote.hidden = true;
    }
  }
  $("winrate-chart").innerHTML = winRateChart(data.holdout);
  $("mae-chart").innerHTML = maeChart(data.holdout);
  const label = $("live-label");
  if (label) label.textContent = card.lock_label || "2026 live record";
  const meta = $("live-meta");
  if (meta && card.holdout_note) meta.textContent = card.holdout_note;
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
      <rect class="${cls}" x="${x}" y="${top}" width="${barW}" height="${h}"/>
      <text class="val${h < 26 ? " out" : ""}" x="${x + barW / 2}" y="${h < 26 ? top - 8 : top + 20}" text-anchor="middle">${fmtPct(row.r.win_rate)}</text>
      <text class="label" x="${x + barW / 2}" y="${H - 18}" text-anchor="middle">${esc(row.label)}</text>
      <text class="axis" x="${x + barW / 2}" y="${H - 4}" text-anchor="middle">${esc(rcRec(row.r))}</text>`;
  }).join("");
  const label = rows.map((row) => `${row.label} ${fmtPct(row.r.win_rate)} (${rcRec(row.r)})`).join(", ") + `. Break-even ${fmtPct(rc.breakeven)}.`;
  return `<svg class="rate-bar" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}">
    <line class="break" x1="${padL}" y1="${breakY}" x2="${W - padR}" y2="${breakY}"/>
    <text class="axis" x="${W - padR}" y="${breakY - 6}" text-anchor="end">Break-even ${fmtPct(rc.breakeven)}</text>
    <line class="base" x1="${padL}" y1="${padT + chartH}" x2="${W - padR}" y2="${padT + chartH}"/>
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
    const tip = `${displayTeam(g.away_team)} at ${displayTeam(g.home_team)}: ${displayTeam(call)} ${word}`;
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
  const N = (t) => `the ${rc.names[t] || displayTeam(t)}`;
  const cap = (x) => x.charAt(0).toUpperCase() + x.slice(1);
  const by = (m) => `${m > 0 ? N(l.home) : N(l.away)} by ${rcNum(Math.abs(m))}`;
  let saw = "", happened = "", number = "";
  if (l.kind === "spread") {
    const pickLine = l.pick === l.home ? -l.line_home_margin : l.line_home_margin;
    const pickMargin = l.pick === l.home ? l.actual_home_margin : -l.actual_home_margin;
    saw = `Vegas had ${by(l.line_home_margin)}. The model had ${by(l.model_home_margin)}, ${rcNum(Math.abs(l.edge))} points away from Vegas, so it would have taken ${N(l.pick)} at ${pickLine > 0 ? "+" : ""}${rcNum(pickLine)}.`;
    happened = `${l.final}. ${cap(N(l.pick))} ${l.outcome === "win" ? "covered" : "did not cover"}.`;
    if (l.outcome === "win") {
      const dog = rc.spread_underdog_calls;
      number = `${dog.bets} of the model's ${rc.spread.bets} spread calls were on the underdog, and those went ${rcRec(dog)}. The model pulls every team hard toward average, so it rarely trusts a big favorite. That paid off here. ${cap(N(l.pick))} were getting ${rcNum(Math.abs(pickLine))} points and ${pickMargin > 0 ? "won by" : "lost by only"} ${Math.abs(pickMargin)}.`;
    } else {
      number = `This is the same pull toward average, and here it cost the model. A ${rcNum(Math.abs(l.line_home_margin))}-point favorite looked like a ${rcNum(Math.abs(l.model_home_margin))}-point favorite to the model. Vegas missed the final margin by ${rcNum(l.line_miss_pts)} points. The model missed by ${rcNum(l.model_miss_pts)}.`;
    }
  } else {
    const side = l.pick === "over" ? "over" : "under";
    const sideRec = rc.total_by_side[side];
    const [pa, pb] = rc.proj_total_range;
    const [la, lb] = rc.line_total_range;
    const mu = l.model_used;
    const offPts = rc.points_per_combined_off * (mu[l.home].off_epa + mu[l.away].off_epa);
    // Reproduce the frozen report's original sign, including its known bug.
    const defPts = -rc.points_per_combined_off * (mu[l.home].def_epa + mu[l.away].def_epa);
    const leader = defPts >= 0
      ? (mu[l.home].def_epa <= mu[l.away].def_epa ? l.home : l.away)
      : (mu[l.home].def_epa >= mu[l.away].def_epa ? l.home : l.away);
    const moved = (pts) => pts < 0 ? `took ${rcNum(Math.abs(pts))} off` : `added ${rcNum(Math.abs(pts))}`;
    saw = `The Vegas total was ${rcNum(l.line_total)} points. The model expected ${rcNum(l.model_total)}, ${rcNum(Math.abs(l.edge))} points ${l.edge > 0 ? "higher" : "lower"}, so it would have taken the ${side}.`;
    happened = `${l.final}, ${l.actual_total} points in all. That is ${rcNum(l.line_miss_pts)} ${l.actual_total < l.line_total ? "under" : "over"} the Vegas total.`;
    number = `Every model total in weeks 1 to 4 landed between ${rcNum(pa)} and ${rcNum(pb)}, while the Vegas totals ran from ${rcNum(la)} to ${rcNum(lb)}. So low lines drew ${side}s, and ${side}s went ${rcRec(sideRec)}. This preserves the original sign bug: defense is EPA allowed, so a stingier defense should lower projected totals, but this model subtracted it. Here the two offenses ${moved(offPts)}, and the defenses, led by ${N(leader)}, ${moved(defPts)}.`;
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
    `${rc.games_graded} games graded. A pick counts when our model and Vegas differ by ${rc.rule.spread_edge_min}+ points on the margin or ${rc.rule.total_edge_min}+ on the total. A standard bet needs ${be} wins to break even.`;
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
    <p class="meta">If it had picked every game, not just the big gaps, it would have gone ${rcRec(all.spread)} (${rcPct(all.spread)}), totals ${rcRec(all.total)} (${rcPct(all.total)}). Vegas still guessed final margins better.</p>`;
  $("rc-weeks").innerHTML = rcWeeks(rc);
  $("rc-lessons").innerHTML = rc.lessons.map((l) => rcLesson(l, rc)).join("");

  const lc = rc.leak_check;
  const h = model.holdout;
  const pending = rc.pending.length
    ? `<p>${rc.pending.map((p) => esc(p.matchup)).join(", ")} had not finished when this ran, so it is not graded.</p>` : "";
  $("rc-honest").innerHTML = `
    <p>Each week, the model only saw games already played. Week 3 used weeks 1 and 2. Week 4 used weeks 1 through 3. The settings were tuned on ${rc.model.fit_on_seasons[0]} to ${rc.model.fit_on_seasons[rc.model.fit_on_seasons.length - 1]} and frozen before any of this.</p>
    <p>To check for leaks, we took each week and swapped every play from that week onward for random numbers (${lc.map((x) => x.plays_poisoned.toLocaleString("en-US")).join(", ")} plays for weeks ${lc.map((x) => x.week).join(", ")}) and ran it again. That week's numbers did not move at all. Scrambling earlier weeks did move weeks 3 and 4, so the test can catch a leak.</p>
    <p>Weeks 1 and 2 ran on ${rc.model.prior_seasons[0]} to ${rc.model.prior_seasons[2]} alone. With one game per team, the model's strength-of-schedule step cancels out, so 2026 games start counting in week 3.</p>
    <p>Grading uses the final Vegas lines from nflverse. ${esc(rc.model.note)} The 2022 to 2025 test remains ${fmtPct(h.spread_win_rate)} on spreads and ${fmtPct(h.total_win_rate)} on totals. Four weeks is a small sample in either direction.</p>
    ${pending}`;
  const t = new Date(rc.generated_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/Chicago" });
  $("rc-foot").textContent = `Backtest generated ${t} CT. Final Vegas lines and scores from nflverse. This is a research record, not betting advice.`;
}

function officialLine(game, names) {
  const selection = game.selection || {};
  const parts = [];
  if (selection.spread_qualifies) {
    const side = selection.spread_pick;
    const shown = displayTeam(side);
    const price = pickLineDisplay(game, side);
    const number = price.slice(shown.length).trim();
    parts.push(`${displayTeam((names && names[side]) || shown)} ${number} (${leanLabel(game)})`);
  }
  if (totalIsActive(selection)) {
    const word = selection.total_pick === "over" ? "Over" : "Under";
    parts.push(`${word} ${Number(game.pick_time.total).toFixed(1)}`);
  }
  return parts.length ? parts.join(", ") : "no pick";
}

async function renderOfficialPicks() {
  const nodes = [...document.querySelectorAll(".official-pick")];
  if (!nodes.length) return;
  const picksUrl = new URL("../api/picks.json", document.baseURI);
  const teamsUrl = new URL("../api/teams.json", document.baseURI);
  const [picksRes, teamsRes] = await Promise.all([fetch(picksUrl), fetch(teamsUrl)]);
  if (!picksRes.ok) throw new Error(`picks.json (${picksRes.status})`);
  const picks = await picksRes.json();
  const teams = teamsRes.ok ? await teamsRes.json() : { teams: [] };
  const names = Object.fromEntries((teams.teams || []).map((t) => [t.team, t.name]));
  const pageWeek = Number(document.body.dataset.week || 0);
  const pageSeason = Number(document.body.dataset.season || 0);
  if (pageWeek && (Number(picks.week) !== pageWeek || (pageSeason && Number(picks.season) !== pageSeason))) {
    // Prefer the historical recap, with the saved card as a fallback when none exists.
    const nn = String(pageWeek).padStart(2, "0");
    const cardUrl = `https://github.com/BowmanStephen/nfl-lab/blob/main/output/live/${pageSeason || picks.season}-week-${nn}.json`;
    const hasRecap = await recapExists(pageWeek, "../");
    nodes.forEach((node) => {
      const link = node.querySelector("a");
      if (link) {
        link.href = hasRecap ? `../recaps/week${pageWeek}.html` : cardUrl;
        link.textContent = hasRecap ? `Week ${pageWeek} recap` : "Saved card";
      }
      const slot = node.querySelector(".official-line");
      if (slot) slot.textContent = `official picks for week ${pageWeek}`;
    });
    return;
  }
  const byId = Object.fromEntries((picks.games || []).map((g) => [g.game_id, g]));
  nodes.forEach((node) => {
    const id = node.dataset.game;
    const game = byId[id];
    const link = node.querySelector("a");
    if (link && id) {
      const week = /^(\d{4})_(\d{2})_/.exec(id);
      link.href = game || !week
        ? `../index.html#b-${id}`
        : `../recaps/week${Number(week[2])}.html`;
    }
    const slot = node.querySelector(".official-line");
    if (slot) slot.textContent = game ? officialLine(game, names) : "no pick";
  });
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { buildTrackRecord, totalsArePaused, displayTeam, displaySpread, takeText, leanLabel, gameRow, officialLine, STRONG_LEAN_EDGE };
}

if (typeof document !== "undefined" && document.body) {
  const page = document.body.dataset.page;
  const run = {
    home: renderHome,
    ledger: renderLedger,
    teams: renderTeams,
    freshness: renderFreshness,
    model: renderModel,
    "report-card": renderReportCard,
  }[page];
  if (document.querySelector(".official-pick")) {
    renderOfficialPicks().catch(() => {
      document.querySelectorAll(".official-line").forEach((slot) => {
        if (!slot.textContent) slot.textContent = "unavailable";
      });
    });
  }
  if (run) {
    run().catch((err) => {
      const slot = $("health") || $("live-record") || $("when") || $("ratings-caption") || $("rec-caption") || document.querySelector("main");
      if (slot) {
        if (slot.hidden) slot.hidden = false;
        slot.textContent = "We couldn't load the latest numbers. Try refreshing.";
      }
    });
  }
}
