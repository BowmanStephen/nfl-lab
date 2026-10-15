// Exercise renderHome with successful, missing, failed, and pending preview checks.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const [pub, response] = process.argv.slice(2);

function element() {
  return {
    innerHTML: "", textContent: "", hidden: true, children: [], attributes: {}, listeners: {},
    appendChild(child) { this.children.push(child); },
    setAttribute(name, value) { this.attributes[name] = value; },
    getAttribute(name) { return this.attributes[name]; },
    addEventListener(name, fn) { this.listeners[name] = fn; },
    querySelectorAll() { return []; },
  };
}
const els = {};
const get = (id) => els[id] ||= element();
const button = get("test-toggle");
button.setAttribute("aria-controls", "test-panel");
button.setAttribute("aria-expanded", "false");
get("test-panel").setAttribute("aria-labelledby", "test-toggle");
get("test-game").closest = () => get("test-panel");
get("test-game").scrollIntoView = () => { get("test-game").scrolled = true; };
get("main").querySelectorAll = () => [button];
let resolvePreview;
const context = vm.createContext({
  URLSearchParams,
  document: {
    body: { dataset: {} }, getElementById: get, createElement: element,
    querySelector: () => null, querySelectorAll: () => [], addEventListener() {},
  },
  window: { addEventListener() {} },
  location: { hash: "#test-game", search: "" },
  fetch: async (url, options) => {
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
  assert.ok(get("games").innerHTML.includes("row-toggle"));
  assert.equal(typeof button.listeners.click, "function", "game controls must be bound");
  assert.equal(get("test-game").scrolled, true, "deep link must be restored");
  assert.equal(get("test-panel").hidden, false);
  button.listeners.click();
  assert.equal(get("test-panel").hidden, true, "bound control must toggle its panel");
  if (response === "pending") {
    assert.equal(get("previews-link").textContent, "");
    assert.equal(get("previews-link").children.length, 0);
    resolvePreview({ ok: false, status: 404 });
    await new Promise(setImmediate);
  }
  const week = JSON.parse(fs.readFileSync(path.join(pub, "api/picks.json"), "utf8")).week;
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
