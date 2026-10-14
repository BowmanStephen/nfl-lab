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

class El {
  constructor(id) {
    this.id = id;
    this.hidden = false;
    this.dataset = {};
    this._mode = "html";
    this._text = "";
    this._html = "";
  }

  set textContent(value) {
    this._mode = "text";
    this._text = value == null ? "" : String(value);
  }

  get textContent() {
    if (this._mode === "text") return this._text;
    return this._html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  }

  set innerHTML(value) {
    this._mode = "html";
    this._html = value == null ? "" : String(value);
  }

  get innerHTML() {
    return this._html;
  }

  setAttribute() {}

  getAttribute() {
    return "";
  }

  addEventListener() {}

  querySelector() {
    return null;
  }

  querySelectorAll() {
    return [];
  }

  closest() {
    return null;
  }

  scrollIntoView() {}
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
  const pageMatch = html.match(/data-page="([^"]+)"/);
  const elements = new Map();
  const jobs = [];

  function getElementById(id) {
    if (!elements.has(id)) elements.set(id, new El(id));
    return elements.get(id);
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
    body: { dataset: { page: pageMatch ? pageMatch[1] : "" } },
    title: "",
    getElementById,
    querySelector(sel) {
      if (sel === "main") return getElementById("main");
      if (sel === ".official-pick" && html.includes("official-pick")) return new El("official-pick");
      return null;
    },
    querySelectorAll(sel) {
      if (sel === ".official-line") return [];
      if (sel === ".row-toggle") return [];
      return [];
    },
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
  for (const [id, el] of elements) {
    fields[id] = { text: el.textContent, html: el.innerHTML, hidden: Boolean(el.hidden) };
  }
  return fields;
}

const rendered = {};
for (const name of pageNames) {
  rendered[name] = await renderPage(name);
}
process.stdout.write(JSON.stringify(rendered));
