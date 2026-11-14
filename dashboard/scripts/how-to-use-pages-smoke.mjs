#!/usr/bin/env node
// Check the filtered deployment artifact, or the live deployment via HOW_TO_USE_ORIGIN.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { resolve, sep, extname } from "node:path";
import { chromium } from "@playwright/test";
const folder = resolve(process.argv[2] ?? "build-pages");
const base = "/os-lab";
const mime = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".json": "application/json", ".png": "image/png", ".woff2": "font/woff2" };
const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, "http://localhost");
    assert.ok(url.pathname.startsWith(base + "/"));
    let file = resolve(folder, "." + decodeURIComponent(url.pathname.slice(base.length)));
    assert.ok(file.startsWith(folder + sep));
    if ((await stat(file)).isDirectory()) file += "/index.html";
    res.writeHead(200, { "Content-Type": mime[extname(file)] ?? "application/octet-stream" });
    res.end(await readFile(file));
  } catch { res.writeHead(404); res.end(); }
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const origin = process.env.HOW_TO_USE_ORIGIN ?? `http://127.0.0.1:${server.address().port}`;
let browser;
try {
  browser = await chromium.launch();
  const page = await browser.newPage();
  const requests = [], errors = [];
  page.on("request", request => { if (new URL(request.url()).pathname.includes("/api/") || request.method() !== "GET") requests.push(request.url()); });
  page.on("pageerror", error => errors.push(error.message));
  await page.addInitScript(() => Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: async value => { window.copiedPrompt = value; } } }));
  for (const locale of ["en", "tr", "de", "fr", "es", "it", "fa", "ar"]) {
    const prefix = `${base}${locale === "en" ? "" : "/" + locale}`;
    const response = await page.goto(`${origin}${prefix}/how-to-use/`);
    assert.equal(response.status(), 200);
    await page.locator("#task-request").waitFor();
    assert.equal(await page.locator("html").getAttribute("lang"), locale);
    await page.locator("#task-request").fill("Review my owned extension safely");
    await page.locator('button[type="submit"]').click();
    await page.waitForFunction(() => window.copiedPrompt?.includes("Review my owned extension safely"));
    const prompt = await page.locator("#generated-prompt").inputValue();
    assert.ok(prompt.includes("public GitHub Pages site"));
    assert.ok(prompt.includes("Source Lab") && prompt.includes("Firewall Lab"));
    assert.ok(prompt.includes("# os-lab operational technical cheatsheet") && prompt.includes("# Generated technical command inventory"));
    assert.ok(prompt.includes("vbox-deploy-android") && prompt.includes("--map-min-role-confidence") && prompt.includes("## Reference sources"));
    assert.equal(await page.evaluate(() => window.copiedPrompt), prompt);
    const links = await page.locator('a[href^="/"]').evaluateAll(nodes => nodes.map(node => node.getAttribute("href")));
    assert.deepEqual(links.filter(href => !href.startsWith(base + "/")), []);
    if (locale !== "en") {
      await page.waitForFunction(() => document.querySelector('button[aria-current="page"]')?.textContent?.trim() !== "How to use");
    }
  }
  await page.getByRole("combobox").first().selectOption("en");
  await page.waitForURL(`${origin}${base}/how-to-use/`);
  await page.getByRole("combobox").first().selectOption("tr");
  await page.waitForURL(`${origin}${base}/tr/how-to-use/`);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await page.locator("#task-request").waitFor();
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2));
  assert.deepEqual(requests, [], "Unexpected public engine or mutation requests");
  assert.deepEqual(errors, [], "Hydration errors");
  console.log("PASS How to use: eight public locales, prompt clipboard, language switching, mobile layout, no engine calls or hydration errors");
} finally { if (browser) await browser.close(); await new Promise(resolve => server.close(resolve)); }
