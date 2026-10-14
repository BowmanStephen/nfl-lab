"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..");
const SITE = path.join(ROOT, "public", "assets", "site.js");
const API = path.join(ROOT, "public", "api");
const PUBLIC = path.join(ROOT, "public");

class El {
  constructor(id) {
    this.id = id || "";
    this.hidden = false;
    this.dataset = {};
    this.className = "";
    this.attrs = {};
    this._html = "";
  }
  set innerHTML(value) {
    this._html = value == null ? "" : String(value);
  }
  get innerHTML() {
    return this._html;
  }
  set textContent(value) {
    this._html = value == null ? "" : String(value);
  }
  get textContent() {
    return this._html.replace(/<[^>]+>/g, " ");
  }
  setAttribute(key, value) {
    this.attrs[key] = String(value);
    if (key === "id") this.id = String(value);
  }
  getAttribute(key) {
    return Object.prototype.hasOwnProperty.call(this.attrs, key) ? this.attrs[key] : null;
  }
  addEventListener() {}
  removeEventListener() {}
  querySelector(sel) {
    return this.querySelectorAll(sel)[0] || null;
  }
  querySelectorAll() {
    return [];
  }
  closest() {
    return null;
  }
  scrollIntoView() {}
  focus() {}
}

function readJson(name) {
  return fs.readFileSync(path.join(API, name), "utf8");
}

function makeFetch(picksOverride) {
  const inflight = new Set();
  function track(promise) {
    const wrapped = Promise.resolve(promise).finally(() => inflight.delete(wrapped));
    inflight.add(wrapped);
    return wrapped;
  }
  function fetchImpl(url) {
    const name = String(url).split("?")[0].split("/").pop();
    return track(Promise.resolve().then(() => {
      if (!name.endsWith(".json")) {
        return { ok: false, status: 404, json: async () => ({}) };
      }
      const body = name === "picks.json" && picksOverride != null ? picksOverride : readJson(name);
      return {
        ok: true,
        status: 200,
        json: () => track(Promise.resolve(JSON.parse(body))),
        text: () => track(Promise.resolve(body)),
      };
    }));
  }
  async function whenSettled() {
    // DOM writes run in the promise continuations of these fetches, after the
    // fetch promises themselves settle. setImmediate runs once that queue drains.
    for (let turn = 0; turn < 50; turn += 1) {
      while (inflight.size) await Promise.race([...inflight]);
      await new Promise((resolve) => setImmediate(resolve));
      if (inflight.size === 0) return;
    }
    throw new Error(`page fetches did not settle (${inflight.size} still running)`);
  }
  return { fetchImpl, whenSettled };
}

function officialPick(gameId) {
  const line = new El("official-line");
  line.className = "official-line";
  const anchor = new El("a");
  const node = new El("official-pick");
  node.className = "official-pick";
  node.dataset.game = gameId;
  node.line = line;
  node.anchor = anchor;
  node.querySelector = (sel) => {
    if (sel === "a") return anchor;
    if (sel === ".official-line") return line;
    return null;
  };
  return node;
}

function previewGameIds() {
  const html = fs.readFileSync(path.join(PUBLIC, "previews", "week5.html"), "utf8");
  return [...html.matchAll(/data-game="([^"]+)"/g)].map((m) => m[1]);
}

function renderPage(pageName, picksOverride) {
  const ids = {};
  const get = (id) => {
    if (!ids[id]) ids[id] = new El(id);
    return ids[id];
  };
  const { fetchImpl, whenSettled } = makeFetch(picksOverride);
  const picks = pageName === "preview" ? previewGameIds().map(officialPick) : [];
  const body = new El("body");
  if (pageName !== "preview") body.dataset.page = pageName;
  const document = {
    body,
    baseURI: pageName === "preview"
      ? "http://nfl-lab.test/previews/week5.html"
      : "http://nfl-lab.test/index.html",
    title: "",
    getElementById: get,
    querySelector(sel) {
      if (sel === "main") return get("main");
      if (sel === ".official-pick") return picks[0] || null;
      return null;
    },
    querySelectorAll(sel) {
      if (sel === ".official-pick") return picks;
      if (sel === ".official-line") return picks.map((node) => node.line);
      return [];
    },
  };
  const context = {
    document,
    location: { search: "?now=2026-10-14T16:00:00Z", hash: "", reload() {} },
    fetch: fetchImpl,
    URL,
    URLSearchParams,
    Date,
    Promise,
    Object,
    Number,
    String,
    Math,
    JSON,
    console,
    setTimeout,
    clearTimeout,
    Intl,
    Array,
    Map,
    Set,
    RegExp,
    Error,
    parseInt,
    parseFloat,
    isNaN,
    NaN,
    Infinity,
    Boolean,
    encodeURIComponent,
    decodeURIComponent,
    module: { exports: {} },
  };
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(SITE, "utf8"), context, { filename: "site.js" });
  return { ids, picks, context, whenSettled };
}

function dump(rendered) {
  const html = [];
  for (const el of Object.values(rendered.ids)) {
    if (el.innerHTML) html.push(el.innerHTML);
  }
  for (const node of rendered.picks) {
    if (node.line.innerHTML) html.push(node.line.innerHTML);
    if (node.anchor.attrs.href) html.push(node.anchor.attrs.href);
  }
  return html.join("\n");
}

async function main() {
  const fixturePath = process.argv[2];
  if (!fixturePath) {
    console.error("usage: node tests/render_display_team.js <rams-card.json>");
    process.exit(1);
  }
  const fixtureCard = fs.readFileSync(fixturePath, "utf8");
  const exported = require(SITE);
  const helper = {
    LA: exported.displayTeam("LA"),
    LAR: exported.displayTeam("LAR"),
    LAC: exported.displayTeam("LAC"),
    ramsName: exported.displayTeam("LA Rams"),
    chargersName: exported.displayTeam("LA Chargers"),
    ari: exported.displayTeam("ARI"),
  };
  const pages = {};
  for (const name of ["home", "ledger", "teams", "model", "report-card", "freshness", "preview"]) {
    const rendered = renderPage(name);
    await rendered.whenSettled();
    pages[name] = dump(rendered);
  }
  const fixture = renderPage("home", fixtureCard);
  await fixture.whenSettled();
  pages.fixture = dump(fixture);
  process.stdout.write(JSON.stringify({ helper, pages }));
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
