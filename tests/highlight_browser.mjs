// Open the published site in Chrome and read what a visitor would see after
// following an official-pick anchor. No extra packages: Node's WebSocket plus
// the DevTools protocol.
import { spawn } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";

const publicDir = process.argv[2];
if (!publicDir) {
  console.error("usage: node tests/highlight_browser.mjs <publicDir>");
  process.exit(2);
}

function chromeBin() {
  const candidates = [
    process.env.CHROME_PATH,
    "/usr/local/bin/google-chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ].filter(Boolean);
  return candidates.find((candidate) => {
    try {
      fs.accessSync(candidate, fs.constants.X_OK);
      return true;
    } catch {
      return false;
    }
  }) || "";
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

function startSite(root) {
  const types = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
  };
  const rootResolved = path.resolve(root);
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, "http://127.0.0.1");
    let rel = decodeURIComponent(url.pathname);
    if (rel.endsWith("/")) rel += "index.html";
    const full = path.resolve(rootResolved, `.${rel}`);
    if (full !== rootResolved && !full.startsWith(rootResolved + path.sep)) {
      res.writeHead(403);
      res.end();
      return;
    }
    fs.readFile(full, (err, data) => {
      if (err) {
        res.writeHead(404);
        res.end("not found");
        return;
      }
      res.writeHead(200, { "content-type": types[path.extname(full)] || "application/octet-stream" });
      res.end(data);
    });
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForJson(url) {
  const started = Date.now();
  let last = "";
  while (Date.now() - started < 8000) {
    try {
      const res = await fetch(url);
      if (res.ok) return res.json();
      last = `${res.status}`;
    } catch (err) {
      last = err.message;
    }
    await sleep(40);
  }
  throw new Error(`devtools did not come up (${last})`);
}

class Cdp {
  constructor(ws) {
    this.ws = ws;
    this.next = 1;
    this.pending = new Map();
    ws.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (!message.id || !this.pending.has(message.id)) return;
      const { resolve, reject } = this.pending.get(message.id);
      this.pending.delete(message.id);
      if (message.error) reject(new Error(JSON.stringify(message.error)));
      else resolve(message.result);
    });
  }

  send(method, params = {}) {
    const id = this.next;
    this.next += 1;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  close() {
    this.ws.close();
  }
}

async function evaluate(cdp, expression) {
  const result = await cdp.send("Runtime.evaluate", {
    expression,
    returnByValue: true,
  });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.text || "evaluate failed");
  }
  return result.result.value;
}

async function blankPage(browserWs) {
  const created = await browserWs.send("Target.createTarget", { url: "about:blank" });
  let page = null;
  const started = Date.now();
  while (!page && Date.now() - started < 4000) {
    const list = await fetch(browserWs.listUrl).then((res) => res.json());
    page = list.find((target) => target.id === created.targetId && target.webSocketDebuggerUrl);
    if (!page) await sleep(40);
  }
  if (!page) throw new Error("devtools page target missing");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", reject, { once: true });
  });
  const cdp = new Cdp(ws);
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  return cdp;
}

async function show(cdp, url, { reduced = false, width = 390, height = 280 } = {}) {
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: true,
  });
  if (reduced) {
    await cdp.send("Emulation.setEmulatedMedia", {
      features: [{ name: "prefers-reduced-motion", value: "reduce" }],
    });
  }
  await cdp.send("Page.navigate", { url });
}

async function waitFor(cdp, expression, timeout = 8000) {
  const started = Date.now();
  let last = null;
  while (Date.now() - started < timeout) {
    last = await evaluate(cdp, expression);
    if (last) return last;
    await sleep(40);
  }
  throw new Error(`timed out: ${JSON.stringify(last)}`);
}

function rowExpression(id) {
  return `(() => {
    const el = document.getElementById(${JSON.stringify(id)});
    if (!el || !el.matches(":target")) return null;
    const active = document.activeElement;
    if (!active || active.id !== el.id) return null;
    for (const anim of el.getAnimations()) {
      anim.pause();
      anim.currentTime = 0;
    }
    const rect = el.getBoundingClientRect();
    const mid = (rect.top + rect.bottom) / 2;
    const inView = mid >= 0 && mid < window.innerHeight;
    if (!inView) return null;
    const cs = getComputedStyle(el);
    return {
      id: el.id,
      background: cs.backgroundColor,
      boxShadow: cs.boxShadow,
      animationName: cs.animationName,
      tabIndex: el.tabIndex,
      activeId: active.id,
      scrollY: window.scrollY,
      inView,
    };
  })()`;
}

function targets() {
  const picks = JSON.parse(fs.readFileSync(path.join(publicDir, "api", "picks.json"), "utf8"));
  const onCard = new Set((picks.games || []).map((game) => game.game_id));
  const picksOnCard = (picks.games || []).filter((game) => game.selection && game.selection.spread_qualifies);
  const pick = picksOnCard[picksOnCard.length - 1];
  if (!pick) throw new Error("current card has no spread pick");
  const preview = fs.readFileSync(path.join(publicDir, "previews", "week5.html"), "utf8");
  const past = [...preview.matchAll(/data-game="([^"]+)"/g)]
    .map((match) => match[1])
    .find((id) => !onCard.has(id));
  if (!past) throw new Error("week 5 preview has no game missing from the current card");
  const week = Number(/^(\d{4})_(\d{2})_/.exec(past)[2]);
  return { pickId: `b-${pick.game_id}`, pastId: `b-${past}`, week };
}

async function main() {
  if (typeof WebSocket !== "function") {
    throw new Error("node WebSocket is required (Node 22)");
  }
  const chrome = chromeBin();
  if (!chrome) throw new Error("Chrome is not installed");
  const { pickId, pastId, week } = targets();
  const site = await startSite(publicDir);
  const origin = `http://127.0.0.1:${site.address().port}`;
  const debugPort = await freePort();
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "nfl-chrome-"));
  const proc = spawn(chrome, [
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--no-first-run",
    `--remote-debugging-port=${debugPort}`,
    `--user-data-dir=${profile}`,
    "about:blank",
  ], { stdio: "ignore" });

  const pages = [];
  try {
    const version = await waitForJson(`http://127.0.0.1:${debugPort}/json/version`);
    const browserSocket = new WebSocket(version.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      browserSocket.addEventListener("open", resolve, { once: true });
      browserSocket.addEventListener("error", reject, { once: true });
    });
    const browser = new Cdp(browserSocket);
    browser.listUrl = `http://127.0.0.1:${debugPort}/json/list`;

    const rowPage = await blankPage(browser);
    pages.push(rowPage);
    await show(rowPage, `${origin}/index.html#${pickId}`);
    const row = await waitFor(rowPage, rowExpression(pickId));

    const reducedPage = await blankPage(browser);
    pages.push(reducedPage);
    await show(reducedPage, `${origin}/index.html#${pickId}`, { reduced: true });
    const reduced = await waitFor(reducedPage, rowExpression(pickId));
    await sleep(400);
    const reducedSettled = await evaluate(reducedPage, rowExpression(pickId));
    if (!reducedSettled) throw new Error(`reduced-motion row disappeared after ${JSON.stringify(reduced)}`);

    const missedPage = await blankPage(browser);
    pages.push(missedPage);
    await show(missedPage, `${origin}/index.html#${pastId}`, { height: 700 });
    const missed = await waitFor(missedPage, `(() => {
      const note = document.querySelector(".missed-pick");
      if (!note) return null;
      const link = note.querySelector("a");
      return {
        text: note.textContent,
        href: link ? link.getAttribute("href") : "",
        role: note.getAttribute("role") || "",
      };
    })()`);

    const previewPage = await blankPage(browser);
    pages.push(previewPage);
    await show(previewPage, `${origin}/previews/week5.html`, { height: 700 });
    const official = await waitFor(previewPage, `(() => {
      const links = [...document.querySelectorAll(".official-pick a")];
      if (!links.length) return null;
      const hrefs = links.map((link) => link.getAttribute("href") || "");
      if (hrefs.some((href) => href.includes("index.html#b-"))) return null;
      return hrefs;
    })()`);

    process.stdout.write(JSON.stringify({
      pickId,
      pastId,
      week,
      row,
      reduced: reducedSettled || reduced,
      missed,
      official,
    }));
  } finally {
    for (const page of pages) {
      try { page.close(); } catch { /* already gone */ }
    }
    proc.kill("SIGKILL");
    site.close();
    fs.rmSync(profile, { recursive: true, force: true });
  }
}

main().catch((err) => {
  console.error(err.stack || err.message);
  process.exit(1);
});
