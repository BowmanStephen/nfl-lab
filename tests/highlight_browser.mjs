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
import { measureSvgContrast } from "./svg_contrast.mjs";

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
    throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text || "evaluate failed");
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

async function show(cdp, url, { reduced = false, width = 390, height = 280, mobile = true } = {}) {
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile,
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

    const contrast = {};
    const viewports = {
      mobile: { width: 390, height: 844, mobile: true },
      desktop: { width: 1280, height: 900, mobile: false },
    };
    for (const [viewport, metrics] of Object.entries(viewports)) {
      const contrastPage = await blankPage(browser);
      pages.push(contrastPage);
      await show(contrastPage, `${origin}/index.html`, metrics);
      // Rows appear after the optional recap request on a fully scored card.
      await waitFor(contrastPage, `Boolean(document.getElementById(${JSON.stringify(pickId)}))`);
      await evaluate(contrastPage, 'document.querySelectorAll(".row-toggle").forEach((button) => button.click())');
      contrast[viewport] = {};
      for (const media of ["screen", "print"]) {
        contrast[viewport][media] = {};
        for (const scheme of ["light", "dark"]) {
          await contrastPage.send("Emulation.setEmulatedMedia", {
            media,
            features: [{ name: "prefers-color-scheme", value: scheme }],
          });
          // Theme changes animate link colors; measure the settled palette.
          await settleTransitions(contrastPage);
          contrast[viewport][media][scheme] = await evaluate(contrastPage, `(${measureContrast.toString()})()`);
          if (media === "screen") {
            contrast[viewport][media][scheme].interactions = await interactionContrast(contrastPage);
          }
        }
      }
    }

    // Follow the actual homepage navigation so a new recap week stays covered.
    const linkedContrast = {};
    // The missing-recap fixture deliberately removes the Last week destination.
    const linkedPages = process.argv.includes("--skip-linked-contrast") ? []
      : [["last_week", "Last week"], ["teams", "Teams"], ["model", "How it works"], ["glossary", "Glossary"],
        ["ledger", "Track record"], ["freshness", "Data updates"],
        ["replay", "2026 replay"], ["preview6", "Week 6 previews"]];
    const ready = {
      last_week: 'Boolean(document.querySelector("#what-mattered p:not(.kicker)"))',
      teams: 'document.querySelectorAll("#teams .team").length === 32',
      model: 'document.querySelectorAll("#ratings-chart .pw-row").length === 32'
        + ' && document.querySelectorAll("#games-chart .game-row").length > 0'
        + ' && document.querySelectorAll("#winrate-chart svg, #mae-chart svg").length === 2',
      glossary: 'document.querySelectorAll("main article.game h2").length >= 12'
        + ' && Boolean(document.querySelector("main table tbody tr:last-child td:last-child"))',
      ledger: 'document.querySelectorAll("#tr-tiles .tr-tile").length === 2'
        + ' && document.querySelectorAll("#tr-games .tr-game").length > 0'
        + ' && document.querySelectorAll("#seasons tr").length === 4'
        + ' && document.querySelectorAll("#live tr").length > 0'
        + ' && document.getElementById("live-health").textContent !== "…"',
      freshness: 'document.getElementById("when").textContent.startsWith("Updated ")'
        + ' && !document.getElementById("when").textContent.includes("…")',
      replay: 'document.querySelectorAll("#rc-hero .rc-big").length === 2'
        + ' && document.querySelectorAll("#rc-weeks .rc-week:not(.rc-week-head)").length === 4'
        + ' && document.querySelectorAll("#rc-lessons .rc-lesson").length === 3'
        + ' && document.getElementById("rc-foot").textContent.startsWith("Backtest generated ")',
      preview6: 'document.querySelectorAll("main article.game").length === 14'
        + ' && document.querySelectorAll(".official-line").length === 14'
        + ' && Array.from(document.querySelectorAll(".official-line"))'
        + '.every((el) => el.textContent.trim() && el.textContent.trim() !== "unavailable")',
    };
    for (const [name, label] of linkedPages) {
      const href = await evaluate(rowPage, `Array.from(document.querySelectorAll(".nav a, .foot-nav a"))
        .find((link) => link.textContent.trim() === ${JSON.stringify(label)})?.href`);
      if (!href) throw new Error(`Homepage navigation is missing ${label}`);
      linkedContrast[name] = {};
      for (const [viewport, metrics] of Object.entries(viewports)) {
        const page = await blankPage(browser);
        pages.push(page);
        await show(page, href, metrics);
        await waitFor(page, `document.readyState === "complete" && (${ready[name]})`);
        linkedContrast[name][viewport] = {};
        for (const scheme of ["light", "dark"]) {
          await page.send("Emulation.setEmulatedMedia", {
            media: "screen",
            features: [{ name: "prefers-color-scheme", value: scheme }],
          });
          await settleTransitions(page);
          linkedContrast[name][viewport][scheme] = {
            ...await evaluate(page, `(${measureContrast.toString()})()`),
            interactions: await interactionContrast(page),
          };
          if (name === "model" || name === "replay") {
            linkedContrast[name][viewport][scheme].svgContrast =
              await evaluate(page, `(${measureSvgContrast.toString()})()`);
          }
          if (name === "ledger") {
            const closed = await evaluate(page, '!document.querySelector(".tr-bettors").open');
            await toggleBettors(page);
            linkedContrast[name][viewport][scheme].expanded = {
              ...await evaluate(page, `(${measureContrast.toString()})()`),
              interactions: await interactionContrast(page),
              wasClosed: closed,
              isOpen: await evaluate(page, 'document.querySelector(".tr-bettors").open'),
            };
            await toggleBettors(page);
          }
          if (name === "model") {
            const selector = "#games-chart .game-row";
            const targets = await evaluate(page, `Array.from(document.querySelectorAll(${JSON.stringify(selector)}))
              .map((el, index) => ({ index, text: el.textContent.trim() }))`);
            linkedContrast[name][viewport][scheme].rowInteractions = {
              targets, hover: await hoverContrast(page, selector, targets),
            };
          }
        }
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
      linkedContrast,
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

async function settleTransitions(page) {
  await evaluate(page, `Promise.all(document.getAnimations()
    .filter((animation) => animation instanceof CSSTransition)
    .map((animation) => animation.finished.catch(() => {})))`);
}

async function toggleBettors(page) {
  const wasOpen = await evaluate(page, 'document.querySelector(".tr-bettors").open');
  await evaluate(page, 'document.querySelector(".tr-bettors > summary").focus()');
  await page.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Enter", code: "Enter",
    windowsVirtualKeyCode: 13, text: "\r", unmodifiedText: "\r" });
  await page.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
  await waitFor(page, `document.querySelector(".tr-bettors").open === ${!wasOpen}`);
  await settleTransitions(page);
}

async function hoverContrast(page, selector, targets) {
  const hover = [];
  await evaluate(page, "document.activeElement.blur()");
  for (const target of targets) {
    const point = await evaluate(page, `(() => {
      const el = document.querySelectorAll(${JSON.stringify(selector)})[${target.index}];
      el.scrollIntoView({ block: "center", inline: "center", behavior: "instant" });
      // A wrapped inline link's bounding-box center can fall between its fragments.
      const r = Array.from(el.getClientRects()).find((rect) => rect.width > 0 && rect.height > 0);
      return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
    })()`);
    await page.send("Input.dispatchMouseEvent", { type: "mouseMoved", ...point });
    await settleTransitions(page);
    hover.push({ index: target.index, result: await evaluate(page,
      `(${measureContrast.toString()})(${target.index}, ${JSON.stringify(selector)})`) });
  }
  await page.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: 0, y: 0 });
  return hover;
}

async function interactionContrast(page) {
  const selector = 'a[href],button,summary,[tabindex="0"]';
  // Hidden details content can retain layout boxes; scrolling it would open the section.
  const targets = await evaluate(page, `Array.from(document.querySelectorAll(${JSON.stringify(selector)}))
    .map((el, index) => ({ el, index }))
    .filter(({ el }) => el.getClientRects().length && getComputedStyle(el).visibility === "visible"
      && !el.disabled && el.tabIndex >= 0
      && (!el.closest("details:not([open])")
        || el.closest("summary")?.parentElement === el.closest("details:not([open])")))
    .map(({ el, index }) => ({ index, text: el.textContent.trim(),
      label: el.getAttribute("aria-label"), officialPick: Boolean(el.closest(".official-pick")),
      hoverable: !el.matches(".skip") }))`);
  const hover = await hoverContrast(page, selector, targets.filter((target) => target.hoverable));
  const focus = [];
  const seen = new Set();
  for (let step = 0; step < targets.length * 2 + 4 && seen.size < targets.length; step++) {
    await page.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
    await page.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
    const index = await evaluate(page, `Array.from(document.querySelectorAll(${JSON.stringify(selector)})).indexOf(document.activeElement)`);
    if (!targets.some((target) => target.index === index) || seen.has(index)) continue;
    await settleTransitions(page);
    focus.push({ index, result: await evaluate(page, `(${measureContrast.toString()})(${index}, ${JSON.stringify(selector)})`) });
    seen.add(index);
  }
  await evaluate(page, "document.activeElement.blur()");
  return { targets, hover, focus };
}

// Runs in Chrome so media queries, inherited colors and transparency are real.
function measureContrast(targetIndex = null, selector = "a[href],button,summary") {
  const rgba = (color) => {
    // Chrome preserves color-mix(in srgb, ...) in this computed-color syntax.
    if (color.startsWith("color(srgb ")) {
      const [channels, alpha = "1"] = color.slice(11, -1).split("/");
      return [...channels.trim().split(/\s+/).map((value) => Number(value) * 255), Number(alpha)];
    }
    if (!/^rgba?\(/.test(color)) throw new Error(`Unsupported contrast color: ${color}`);
    const channels = color.match(/[\d.]+/g).map(Number);
    return [...channels.slice(0, 3), channels[3] ?? 1];
  };
  const over = (fg, bg) => fg.slice(0, 3).map((value, i) => value * fg[3] + bg[i] * (1 - fg[3]));
  const luminance = (color) => color.map((value) => {
    const channel = value / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  }).reduce((total, value, i) => total + value * [0.2126, 0.7152, 0.0722][i], 0);
  const ratio = (a, b) => (Math.max(luminance(a), luminance(b)) + 0.05) / (Math.min(luminance(a), luminance(b)) + 0.05);
  const backgroundOf = (el) => {
    const ancestors = [];
    for (let node = el; node; node = node.parentElement) ancestors.unshift(node);
    let background = [255, 255, 255];
    for (const node of ancestors) {
      const style = getComputedStyle(node);
      if (style.opacity !== "1") throw new Error("Contrast probe needs opacity compositing");
      background = over(rgba(style.backgroundColor), background);
    }
    return background;
  };
  const root = targetIndex === null ? document.body : document.querySelectorAll(selector)[targetIndex];
  if (!root) throw new Error("Contrast target disappeared");
  const style = getComputedStyle(root);
  const outside = backgroundOf(root.parentElement);
  // SVG text uses fill and may sit over other shapes, requiring a separate probe.
  const text = [root, ...root.querySelectorAll("*")].filter((el) =>
    el.namespaceURI === "http://www.w3.org/1999/xhtml"
    && [...el.childNodes].some((node) => node.nodeType === Node.TEXT_NODE && node.textContent.trim())
    && el.getClientRects().length && getComputedStyle(el).visibility === "visible"
    && (!el.closest("details:not([open])")
      || el.closest("summary")?.parentElement === el.closest("details:not([open])"))
    && getComputedStyle(el).clipPath === "none");
  return {
    hovered: root.matches(":hover"),
    focused: root === document.activeElement,
    focusVisible: root.matches(":focus-visible"),
    outline: {
      style: style.outlineStyle,
      width: parseFloat(style.outlineWidth),
      ratio: style.outlineStyle === "none" ? null : ratio(over(rgba(style.outlineColor), outside), outside),
    },
    viewport: {
      width: innerWidth,
      height: innerHeight,
      mobileLayout: matchMedia("(max-width: 600px)").matches,
    },
    print: matchMedia("print").matches,
    screen: matchMedia("screen").matches,
    dark: matchMedia("(prefers-color-scheme: dark)").matches,
    paper: getComputedStyle(document.body).backgroundColor,
    samples: text.map((el) => {
      const background = backgroundOf(el);
      const foreground = over(rgba(getComputedStyle(el).color), background);
      return {
        tag: el.tagName.toLowerCase(),
        id: el.id,
        text: el.textContent.trim().slice(0, 80),
        ratio: ratio(foreground, background),
      };
    }),
  };
}

main().catch((err) => {
  console.error(err.stack || err.message);
  process.exit(1);
});
