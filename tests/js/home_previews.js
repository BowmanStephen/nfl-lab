// Exercise renderHome with successful, missing, failed, and pending preview checks.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const [pub, response] = process.argv.slice(2);

function element() {
  return {
    html: "", text: "", hidden: false, children: [], attributes: {}, listeners: {},
    get innerHTML() { return this.html; },
    set innerHTML(value) {
      this.html = value;
      this.children = [];
      const stack = [this];
      for (const match of value.matchAll(/<(\/?)([a-z][a-z0-9]*)\b([^>]*)>/gi)) {
        const [, closing, tag, attrs] = match;
        if (closing) {
          if (stack.length > 1) stack.pop();
          continue;
        }
        const child = element();
        for (const attr of attrs.matchAll(/([\w-]+)="([^"]*)"/g)) child.setAttribute(attr[1], attr[2]);
        child.hidden = /\shidden\b/.test(attrs);
        if (child.attributes.id) els[child.attributes.id] = child;
        stack.at(-1).appendChild(child);
        if (!["br", "hr", "img", "input", "link", "meta"].includes(tag)) stack.push(child);
      }
    },
    get textContent() { return this.text + this.children.map((child) => child.textContent).join(""); },
    set textContent(value) { this.text = value; this.children = []; },
    appendChild(child) { child.parent = this; this.children.push(child); },
    setAttribute(name, value) { this.attributes[name] = value; },
    getAttribute(name) { return this.attributes[name]; },
    addEventListener(name, fn) { this.listeners[name] = fn; },
    querySelectorAll(selector) {
      assert.equal(selector, ".row-toggle");
      return this.children.flatMap((child) => [
        ...((child.getAttribute("class") || "").split(/\s+/).includes("row-toggle") ? [child] : []),
        ...child.querySelectorAll(selector),
      ]);
    },
    closest(selector) {
      assert.equal(selector, "[hidden]");
      return this.hidden ? this : this.parent?.closest(selector) || null;
    },
    scrollIntoView() { this.scrolled = true; },
    matches(selector) { assert.equal(selector, ":target"); return true; },
    focus() { this.focused = true; },
  };
}
const els = {};
const get = (id) => els[id] || null;
element().innerHTML = fs.readFileSync(path.join(pub, "index.html"), "utf8");
// Pick selections on this committed card are immutable; grading may be filled later.
// Keep the fixture before kickoff regardless of the current public weekly card.
const card = JSON.parse(fs.readFileSync(path.join(pub, "../output/live/2026-week-06.json"), "utf8"));
for (const game of card.games) game.grading = null;
const game = card.games.find((g) => g.selection.spread_qualifies);
const gameId = game ? String(game.game_id).replace(/[^\w-]/g, "") : null;
let resolvePreview;
const context = vm.createContext({
  URLSearchParams,
  document: {
    body: { dataset: {} }, getElementById: get, createElement: element,
    querySelector: () => null, querySelectorAll: () => [], addEventListener() {},
  },
  window: { addEventListener() {}, matchMedia: () => ({ matches: true }) },
  location: { hash: gameId ? `#d-${gameId}` : "", search: "" },
  fetch: async (url, options) => {
    if (url === "api/picks.json") return { ok: true, json: async () => card };
    if (String(url).startsWith("previews/")) {
      assert.equal(options.method, "HEAD");
      if (response === "network") throw new Error("offline");
      if (response === "pending") return new Promise((resolve) => { resolvePreview = resolve; });
      return { ok: response === "200", status: Number(response) };
    }
    return { ok: true, json: async () => JSON.parse(fs.readFileSync(path.join(pub, url), "utf8")) };
  },
});
vm.runInContext(fs.readFileSync(path.join(pub, "assets/site.js"), "utf8"), context);
vm.runInContext('Date.now = () => Date.parse("2026-10-15T16:00:00Z")', context);

(async () => {
  const render = vm.runInContext("renderHome()", context);
  let timer;
  try {
    await Promise.race([
      render,
      new Promise((_, reject) => { timer = setTimeout(() => reject(new Error("preview check blocked home initialization")), 1000); }),
    ]);
  } finally { clearTimeout(timer); }
  await new Promise(setImmediate);
  const buttons = get("games").querySelectorAll(".row-toggle");
  assert.equal(buttons.length, card.games.filter((g) => g.selection.spread_qualifies).length,
    "only qualifying picks should have controls in the picks section");
  for (const button of get("main").querySelectorAll(".row-toggle")) {
    assert.equal(typeof button.listeners.click, "function", "rendered controls must be bound");
  }
  if (gameId) {
    const button = buttons.find((btn) => btn.getAttribute("aria-controls") === `d-${gameId}`);
    assert.ok(button, "deep link must reference a rendered game control");
    const panel = get(button.getAttribute("aria-controls"));
    assert.equal(panel.scrolled, true, "deep link must be restored");
    assert.equal(panel.hidden, false);
    button.listeners.click();
    assert.equal(panel.hidden, true, "generated control must toggle its rendered panel");
  }
  if (response === "pending") {
    assert.equal(get("previews-link").textContent, "");
    assert.equal(get("previews-link").children.length, 0);
    resolvePreview({ ok: false, status: 404 });
    await new Promise(setImmediate);
  }
  const week = card.week;
  const slot = get("previews-link");
  if (response === "200") {
    assert.equal(slot.children.length, 1);
    assert.equal(slot.children[0].href, `previews/week${week}.html`);
    assert.equal(slot.children[0].textContent, `Read the week ${week} game previews`);
  } else {
    assert.equal(slot.children.length, 0, "missing or unverified page must not be linked");
    assert.equal(slot.textContent, response === "404" || response === "pending"
      ? `Week ${week} previews are coming soon`
      : `Week ${week} previews are temporarily unavailable. Try refreshing.`);
  }
})().catch((err) => { console.error(err); process.exitCode = 1; });
