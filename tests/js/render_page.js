// Minimal DOM stub to run site.js page renderers in node without dependencies.
// Usage: node render_page.js <public dir> <page html> <picks.json override> <now ISO>
// Prints JSON {id: {html, text, hidden}} for every id in the page.
const fs = require("fs");
const path = require("path");
const [pub, pageFile, picksPath, nowIso] = process.argv.slice(2);
const html = fs.readFileSync(path.join(pub, pageFile), "utf8");
const page = (html.match(/<body[^>]*data-page="([^"]+)"/) || [])[1];
const els = {};
for (const m of html.matchAll(/<([a-z0-9]+)([^>]*)\sid="([^"]+)"([^>]*)>/g)) {
  const attrs = m[2] + m[4];
  els[m[3]] = {
    id: m[3], innerHTML: "", textContent: "", hidden: /\shidden\b/.test(attrs), href: "",
    dataset: {}, classList: { add() {}, remove() {}, toggle() {} }, style: {},
    querySelectorAll: () => [], querySelector: () => null, addEventListener() {},
    setAttribute() {}, getAttribute: () => null,
  };
}
global.document = {
  body: { dataset: { page } },
  getElementById: (id) => els[id] || null,
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener() {},
};
global.window = { location: { hash: "", search: "" }, addEventListener() {} };
global.location = global.window.location;
const realNow = Date.parse(nowIso);
Date.now = () => realNow;
global.fetch = async (url) => {
  const rel = String(url).replace(/^\.?\//, "");
  const file = rel === "api/picks.json" ? picksPath : path.join(pub, rel);
  if (!fs.existsSync(file)) return { ok: false, status: 404, json: async () => ({}) };
  const body = fs.readFileSync(file, "utf8");
  return { ok: true, status: 200, json: async () => JSON.parse(body), text: async () => body };
};
require(path.resolve(pub, "assets/site.js"));
setTimeout(() => {
  const out = {};
  for (const [id, e] of Object.entries(els)) out[id] = { html: e.innerHTML, text: e.textContent, hidden: e.hidden };
  console.log(JSON.stringify(out));
}, 300);
