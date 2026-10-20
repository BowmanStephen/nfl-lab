#!/usr/bin/env node
// Capture a real Chrome screenshot + text snapshot of one site path.
// Usage: node browser_shot.mjs <baseUrl> <path> <outDir>
// Example: node browser_shot.mjs http://127.0.0.1:8765 /index.html ./artifacts/home
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { waitForDevTools } from "../../../../tests/chrome_startup.mjs";

const [baseUrl, pagePath, outDir] = process.argv.slice(2);
if (!baseUrl || !pagePath || !outDir) {
  console.error("usage: node browser_shot.mjs <baseUrl> <path> <outDir>");
  process.exit(2);
}

function chromeBin() {
  const candidates = [
    process.env.CHROME_PATH,
    "/usr/local/bin/google-chrome",
    "/usr/local/bin/chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ].filter(Boolean);
  return candidates.find((c) => {
    try {
      fs.accessSync(c, fs.constants.X_OK);
      return true;
    } catch {
      return false;
    }
  }) || "";
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
    const id = this.next++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  close() {
    this.ws.close();
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function evaluate(cdp, expression) {
  const result = await cdp.send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (result.exceptionDetails) {
    throw new Error(
      result.exceptionDetails.exception?.description ||
        result.exceptionDetails.text ||
        "evaluate failed",
    );
  }
  return result.result.value;
}

async function main() {
  const bin = chromeBin();
  if (!bin) throw new Error("Chrome/Chromium not found");

  fs.mkdirSync(outDir, { recursive: true });
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "nfl-lab-verify-chrome-"));
  const proc = spawn(
    bin,
    [
      `--user-data-dir=${profile}`,
      "--remote-debugging-port=0",
      "--headless=new",
      "--disable-gpu",
      "--no-first-run",
      "--no-default-browser-check",
      "about:blank",
    ],
    { stdio: ["ignore", "ignore", "pipe"] },
  );

  let cdp;
  try {
    const wsUrl = await waitForDevTools(proc);
    // DevTools announces a ws:// browser URL; HTTP JSON endpoints need http(s).
    const httpBase = wsUrl
      .replace(/^ws:/, "http:")
      .replace(/^wss:/, "https:")
      .replace(/\/devtools\/browser\/.*$/, "");
    const listUrl = `${httpBase}/json/list`;
    const versionUrl = `${httpBase}/json/version`;
    const version = await fetch(versionUrl).then((r) => r.json());
    const browserWs = new WebSocket(version.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      browserWs.addEventListener("open", resolve, { once: true });
      browserWs.addEventListener("error", reject, { once: true });
    });
    const browser = new Cdp(browserWs);
    browser.listUrl = listUrl;

    const created = await browser.send("Target.createTarget", { url: "about:blank" });
    let page = null;
    const started = Date.now();
    while (!page && Date.now() - started < 4000) {
      const list = await fetch(listUrl).then((r) => r.json());
      page = list.find((t) => t.id === created.targetId && t.webSocketDebuggerUrl);
      if (!page) await sleep(40);
    }
    if (!page) throw new Error("page target missing");
    const pageWs = new WebSocket(page.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      pageWs.addEventListener("open", resolve, { once: true });
      pageWs.addEventListener("error", reject, { once: true });
    });
    cdp = new Cdp(pageWs);
    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width: 1280,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    });

    const url = new URL(pagePath, baseUrl.endsWith("/") ? baseUrl : baseUrl + "/").href;
    await cdp.send("Page.navigate", { url });
    // Navigation and static headings do not prove that site.js loaded the API data.
    const deadline = Date.now() + 10000;
    let snap = null;
    while (Date.now() < deadline) {
      snap = await evaluate(
        cdp,
        `(() => {
          const page = document.body?.dataset.page || "";
          const text = (id) => document.getElementById(id)?.textContent?.trim() || "";
          const populated = (value) => !!value && !/^(?:…|\\.\\.\\.)$|Loading/i.test(value);
          const title = document.getElementById("home-title")?.textContent?.trim() || "";
          const mark = document.querySelector("a.mark")?.textContent?.trim() || "";
          const h1 = document.querySelector("h1")?.textContent?.trim() || "";
          const games = document.querySelectorAll("#games .game-row:not(.placeholder)").length;
          const spread = document.getElementById("spread-rec")?.textContent?.trim() || "";
          const live = document.getElementById("live-health")?.textContent?.trim() || "";
          const total = text("total-rec");
          const scope = text("tr-scope");
          const tiles = document.querySelectorAll("#tr-tiles .tr-tile").length;
          const charts = {
            ratings: document.querySelectorAll("#ratings-chart .pw-row").length,
            games: document.querySelectorAll("#games-chart .game-row").length,
            winrate: !!document.querySelector("#winrate-chart svg"),
            mae: !!document.querySelector("#mae-chart svg"),
          };
          const loading = /Loading/i.test(title);
          let ready = !loading && !!(title || h1);
          if (page === "home") ready = populated(title);
          if (page === "ledger") {
            ready = [spread, total, live, scope].every(populated) && tiles > 0;
          }
          if (page === "model") {
            ready = charts.ratings > 0 && charts.games > 0 && charts.winrate && charts.mae;
          }
          return { page, title, mark, h1, games, spread, total, live, scope, tiles, charts, loading, ready };
        })()`,
      );
      if (snap?.ready) break;
      await sleep(80);
    }
    if (!snap?.ready) throw new Error(`page never hydrated: ${JSON.stringify(snap)}`);

    const shot = await cdp.send("Page.captureScreenshot", { format: "png" });
    const pngPath = path.join(outDir, "page.png");
    fs.writeFileSync(pngPath, Buffer.from(shot.data, "base64"));
    const textPath = path.join(outDir, "snapshot.json");
    fs.writeFileSync(textPath, JSON.stringify({ url, ...snap }, null, 2) + "\n");
    fs.writeFileSync(
      path.join(outDir, "meta.txt"),
      [
        `url=${url}`,
        `png=${pngPath}`,
        `snapshot=${textPath}`,
        `timestamp_utc=${new Date().toISOString()}`,
      ].join("\n") + "\n",
    );
    console.log(`evidence=${outDir}`);
    console.log(JSON.stringify(snap));
  } finally {
    try {
      cdp?.close();
    } catch {
      /* ignore */
    }
    proc.kill("SIGTERM");
    try {
      fs.rmSync(profile, { recursive: true, force: true });
    } catch {
      /* ignore */
    }
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
