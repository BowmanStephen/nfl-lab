// Render the published pages with the real site.js so tests can read the
// numbers a browser would show. No extra packages: a tiny DOM plus Node's vm.
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";

const [publicDir, nowIso, ...pageNames] = process.argv.slice(2);
if (!publicDir || !nowIso || pageNames.length === 0) {
  console.error("usage: node tests/render_site.mjs <publicDir> <nowIso> <page>...");
  process.exit(2);
}

const PAGES = {
  home: { file: "index.html", href: "http://nfl-lab.test/index.html" },
  ledger: { file: "ledger.html", href: "http://nfl-lab.test/ledger.html" },
  model: { file: "model.html", href: "http://nfl-lab.test/model.html" },
};

// This is a focused DOM, not a browser: parse actual nodes and search only the
// connected tree so missing or removed markup cannot produce phantom fields.
const VOID_TAGS = new Set("area base br col embed hr img input link meta param source track wbr".split(" "));

class El {
  constructor(tag, attrs = {}, opening = "") {
    this.tag = tag;
    this.attrs = attrs;
    this.id = attrs.id || "";
    this.hidden = Object.hasOwn(attrs, "hidden");
    this.dataset = Object.fromEntries(Object.entries(attrs)
      .filter(([key]) => key.startsWith("data-"))
      .map(([key, value]) => [key.slice(5), value]));
    this.opening = opening;
    this.closing = "";
    this.children = [];
  }

  set textContent(value) {
    // Text assignments remove existing descendants, just as in a browser.
    const text = value == null ? "" : String(value);
    this.children = [text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")];
  }

  get textContent() {
    return this.innerHTML.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  }

  set innerHTML(value) {
    this.children = parseMarkup(value == null ? "" : String(value)).children;
  }

  get innerHTML() {
    return this.children.map((child) => typeof child === "string" ? child
      : child.opening + child.innerHTML + child.closing).join("");
  }

  setAttribute(name, value) { this.attrs[name] = String(value); }
  getAttribute(name) { return this.attrs[name] ?? null; }
  addEventListener() {}
  appendChild(child) { this.children.push(child); return child; }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  querySelectorAll(selector) {
    return descendants(this).filter((el) => selector.startsWith("#") ? el.id === selector.slice(1)
      : selector.startsWith(".") ? (el.attrs.class || "").split(/\s+/).includes(selector.slice(1))
      : el.tag === selector);
  }
  closest() { return null; }
  scrollIntoView() {}
}

function descendants(root) {
  return root.children.flatMap((child) => typeof child === "string" ? [] : [child, ...descendants(child)]);
}

function parseMarkup(markup) {
  const root = new El("document");
  const stack = [root];
  // Match comments and quoted attributes as units: apparent IDs inside either
  // must never become nodes. Script/style contents are raw text, not markup.
  const tokens = /<!--[\s\S]*?(?:-->|$)|<![^>]*>|<\/?[a-zA-Z][^>"']*(?:(?:"[^"]*"|'[^']*')[^>"']*)*>/g;
  let offset = 0;
  let token;
  while ((token = tokens.exec(markup))) {
    const parent = stack[stack.length - 1];
    parent.children.push(markup.slice(offset, token.index));
    const raw = token[0];
    offset = tokens.lastIndex;
    if (raw.startsWith("<!")) { parent.children.push(raw); continue; }
    const tag = raw.match(/^<\/?([\w:-]+)/)[1].toLowerCase();
    if (raw.startsWith("</")) {
      const index = stack.findLastIndex((el) => el.tag === tag);
      if (index > 0) { stack[index].closing = raw; stack.length = index; }
      continue;
    }
    const attrs = {};
    const attrSource = raw.slice(raw.match(/^<[\w:-]+/)[0].length, -1);
    const attrPattern = /([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g;
    for (const attr of attrSource.matchAll(attrPattern)) {
      attrs[attr[1].toLowerCase()] = attr[2] ?? attr[3] ?? attr[4] ?? "";
    }
    const el = new El(tag, attrs, raw);
    parent.children.push(el);
    if (VOID_TAGS.has(tag) || raw.endsWith("/>")) continue;
    if (["script", "style", "textarea", "title"].includes(tag)) {
      const end = new RegExp(`</${tag}\\s*>`, "ig");
      end.lastIndex = offset;
      const close = end.exec(markup);
      el.children = [markup.slice(offset, close ? close.index : markup.length)];
      el.closing = close ? close[0] : "";
      offset = close ? end.lastIndex : markup.length;
      tokens.lastIndex = offset;
    } else {
      stack.push(el);
    }
  }
  stack[stack.length - 1].children.push(markup.slice(offset));
  return root;
}

function fileFor(pageHref, url) {
  const abs = new URL(url, pageHref);
  const rel = decodeURIComponent(abs.pathname).replace(/^\/+/, "");
  const full = path.resolve(publicDir, rel);
  const root = path.resolve(publicDir);
  if (full !== root && !full.startsWith(root + path.sep)) {
    throw new Error(`refusing to read ${url}`);
  }
  return full;
}

async function renderPage(name) {
  const spec = PAGES[name];
  if (!spec) throw new Error(`unknown page ${name}`);
  const html = fs.readFileSync(path.join(publicDir, spec.file), "utf8");
  const tree = parseMarkup(html);
  const body = tree.querySelector("body") || new El("body");
  const jobs = [];

  function getElementById(id) {
    return descendants(tree).find((el) => el.id && el.id === id) || null;
  }

  const location = {
    href: spec.href,
    search: `?now=${encodeURIComponent(nowIso)}`,
    hash: "",
    reload() {},
  };

  function trackedFetch(url, opts = {}) {
    const job = (async () => {
      const file = fileFor(spec.href, url);
      const exists = fs.existsSync(file);
      return {
        ok: exists,
        status: exists ? 200 : 404,
        async json() {
          return JSON.parse(fs.readFileSync(file, "utf8"));
        },
        async text() {
          return fs.readFileSync(file, "utf8");
        },
      };
    })();
    jobs.push(job);
    return job;
  }

  const document = {
    body,
    title: "",
    getElementById,
    createElement(tag) { return new El(tag); },
    querySelector(sel) { return tree.querySelector(sel); },
    querySelectorAll(sel) { return tree.querySelectorAll(sel); },
  };

  const sandbox = {
    console,
    document,
    location,
    fetch: trackedFetch,
    URL,
    URLSearchParams,
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(publicDir, "assets", "site.js"), "utf8"), sandbox, {
    filename: "site.js",
  });

  for (let i = 0; i < 30; i += 1) {
    if (jobs.length === 0) break;
    const batch = jobs.splice(0, jobs.length);
    await Promise.all(batch);
    await new Promise((resolve) => setImmediate(resolve));
  }
  if (jobs.length) throw new Error(`${name} render did not settle`);

  const fields = {};
  for (const el of descendants(tree)) {
    if (!el.id || Object.hasOwn(fields, el.id)) continue;
    fields[el.id] = { text: el.textContent, html: el.innerHTML, hidden: Boolean(el.hidden) };
  }
  return fields;
}

const rendered = {};
for (const name of pageNames) {
  rendered[name] = await renderPage(name);
}
process.stdout.write(JSON.stringify(rendered));
