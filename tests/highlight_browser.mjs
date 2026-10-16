// Open the published site in Chrome and read what a visitor would see after
// following an official-pick anchor. No extra packages: Node's WebSocket plus
// the DevTools protocol.
import { spawn } from "node:child_process";
import { once } from "node:events";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { waitForDevTools } from "./chrome_startup.mjs";

const publicDir = process.argv[2];
if (!publicDir) {
  console.error("usage: node tests/highlight_browser.mjs <publicDir>");
  process.exit(2);
}

function chromeBin() {
  const candidates = [
    process.env.CHROME_PATH,
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
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
    awaitPromise: true,
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
  await cdp.send("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-reduced-motion", value: reduced ? "reduce" : "no-preference" }],
  });
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
  const pick = picksOnCard[picksOnCard.length - 1] || (picks.games || []).at(-1);
  if (!pick) throw new Error("current card has no games");
  const preview = fs.readFileSync(path.join(publicDir, "previews", "week5.html"), "utf8");
  const past = [...preview.matchAll(/data-game="([^"]+)"/g)]
    .map((match) => match[1])
    .find((id) => !onCard.has(id));
  if (!past) throw new Error("week 5 preview has no game missing from the current card");
  const week = Number(/^(\d{4})_(\d{2})_/.exec(past)[2]);
  return { pickId: `b-${pick.game_id}`, pastId: `b-${past}`, week };
}

async function main() {
  if (process.argv.includes("--targets-only")) {
    process.stdout.write(JSON.stringify(targets()));
    return;
  }
  if (typeof WebSocket !== "function") {
    throw new Error("node WebSocket is required (Node 22)");
  }
  const chrome = chromeBin();
  if (!chrome) throw new Error("Chrome is not installed");
  const { pickId, pastId, week } = targets();
  const site = await startSite(publicDir);
  const origin = `http://127.0.0.1:${site.address().port}`;
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "nfl-chrome-"));
  const proc = spawn(chrome, [
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--no-first-run",
    "--remote-debugging-port=0",
    `--user-data-dir=${profile}`,
    "about:blank",
  ], { stdio: ["ignore", "ignore", "pipe"] });

  const pages = [];
  let browser;
  try {
    const endpoint = await waitForDevTools(proc);
    const browserSocket = new WebSocket(endpoint);
    await new Promise((resolve, reject) => {
      browserSocket.addEventListener("open", resolve, { once: true });
      browserSocket.addEventListener("error", reject, { once: true });
    });
    browser = new Cdp(browserSocket);
    browser.listUrl = `http://${new URL(endpoint).host}/json/list`;

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

    const contrastPage = await blankPage(browser);
    pages.push(contrastPage);
    await show(contrastPage, `${origin}/index.html`, { height: 700 });
    // Rows appear after the optional recap request on a fully scored card.
    await waitFor(contrastPage, `Boolean(document.getElementById(${JSON.stringify(pickId)}))`);
    await evaluate(contrastPage, 'document.querySelectorAll(".row-toggle").forEach((button) => button.click())');
    const contrast = {};
    for (const media of ["screen", "print"]) {
      contrast[media] = {};
      for (const scheme of ["light", "dark"]) {
        await contrastPage.send("Emulation.setEmulatedMedia", {
          media,
          features: [{ name: "prefers-color-scheme", value: scheme }],
        });
        // Theme changes animate link colors; measure the settled palette.
        await evaluate(contrastPage, `Promise.all(document.getAnimations()
          .filter((animation) => animation instanceof CSSTransition)
          .map((animation) => animation.finished.catch(() => {})))`);
        contrast[media][scheme] = await evaluate(contrastPage, `(${measureContrast.toString()})()`);
      }
    }

    process.stdout.write(JSON.stringify({
      pickId,
      pastId,
      week,
      row,
      reduced: reducedSettled || reduced,
      missed,
      official,
      contrast,
    }));
  } finally {
    for (const page of pages) {
      try { page.close(); } catch { /* already gone */ }
    }
    if (proc.exitCode === null && proc.signalCode === null) {
      const exited = once(proc, "exit");
      // Let Chrome stop its children and flush the profile before removing it.
      if (browser) browser.send("Browser.close").catch(() => {});
      else proc.kill("SIGTERM");
      const deadline = setTimeout(() => proc.kill("SIGKILL"), 5000);
      try { await exited; } finally { clearTimeout(deadline); }
    }
    if (browser) browser.close();
    site.close();
    fs.rmSync(profile, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 });
  }
}

// Runs in Chrome so media queries, inherited colors and transparency are real.
function measureContrast() {
  const rgba = (color) => {
    if (!/^rgba?\(/.test(color)) throw new Error(`Unsupported contrast color: ${color}`);
    const channels = color.match(/[\d.]+/g).map(Number);
    return [...channels.slice(0, 3), channels[3] ?? 1];
  };
  const over = (fg, bg) => fg.slice(0, 3).map((value, i) => value * fg[3] + bg[i] * (1 - fg[3]));
  const luminance = (color) => color.map((value) => {
    const channel = value / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  }).reduce((total, value, i) => total + value * [0.2126, 0.7152, 0.0722][i], 0);
  const text = [...document.querySelectorAll("body *")].filter((el) =>
    [...el.childNodes].some((node) => node.nodeType === Node.TEXT_NODE && node.textContent.trim())
    && el.getClientRects().length && getComputedStyle(el).visibility === "visible"
    && getComputedStyle(el).clipPath === "none");
  return {
    print: matchMedia("print").matches,
    screen: matchMedia("screen").matches,
    dark: matchMedia("(prefers-color-scheme: dark)").matches,
    paper: getComputedStyle(document.body).backgroundColor,
    samples: text.map((el) => {
      const ancestors = [];
      for (let node = el; node; node = node.parentElement) ancestors.unshift(node);
      let background = [255, 255, 255];
      for (const node of ancestors) {
        const style = getComputedStyle(node);
        if (style.opacity !== "1") throw new Error("Contrast probe needs opacity compositing");
        background = over(rgba(style.backgroundColor), background);
      }
      const foreground = over(rgba(getComputedStyle(el).color), background);
      const a = luminance(foreground), b = luminance(background);
      return {
        tag: el.tagName.toLowerCase(),
        id: el.id,
        text: el.textContent.trim().slice(0, 80),
        ratio: (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05),
      };
    }),
  };
}

main().catch((err) => {
  console.error(err.stack || err.message);
  process.exit(1);
});
