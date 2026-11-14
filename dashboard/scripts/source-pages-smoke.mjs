#!/usr/bin/env node
// Verify every public Source route without a local engine or private fixtures.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, stat, readdir } from "node:fs/promises";
import { resolve, sep, extname } from "node:path";
import { chromium } from "@playwright/test";
const folder = resolve(process.argv[2] ?? ".check-source-pages");
const base = "/os-lab";
const mime = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".json": "application/json", ".png": "image/png", ".woff2": "font/woff2" };
const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, "http://localhost");
    if (!url.pathname.startsWith(base + "/")) throw new Error();
    let file = resolve(folder, "." + decodeURIComponent(url.pathname.slice(base.length)));
    if (!file.startsWith(folder + sep)) throw new Error();
    if ((await stat(file)).isDirectory()) file += "/index.html";
    const bytes = await readFile(file);
    res.writeHead(200, { "Content-Type": mime[extname(file)] ?? "application/octet-stream" });
    res.end(bytes);
  } catch { res.writeHead(404); res.end(); }
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
let browser;
try {
  browser = await chromium.launch();
  const page = await browser.newPage();
  const requests = [], errors = [];
  page.on("request", request => { if (new URL(request.url()).pathname.includes("/api/")) requests.push(request.url()); });
  page.on("pageerror", error => errors.push(error.message));
  const locales = ["en", ...(await readdir(new URL("../src/i18n/generated/", import.meta.url))).filter(name => name.endsWith(".json")).map(name => name.slice(0, -5))];
  const routes = ["", "analyzer", "evidence", "deep-analysis", "pipeline", "brain", "sources", "settings/runtime", "docs", "docs/guide", "docs/collectors", "docs/brain", "docs/import", "docs/runbook"];
  let checked = 0;
  for (const locale of locales) for (const route of routes) {
    const prefix = `${base}${locale === "en" ? "" : "/" + locale}`;
    const response = await page.goto(`${origin}${prefix}/source/${route ? route + "/" : ""}?repo=owned/sample&file=owned.js`);
    assert.equal(response.status(), 200, `${locale}/${route}`);
    await page.locator("main nav").waitFor();
    assert.equal(await page.locator("html").getAttribute("lang"), locale);
    assert.equal(await page.locator("main button").count(), 0, "Public operation button");
    const links = await page.locator('a[href^="/"]').evaluateAll(nodes => nodes.map(node => node.getAttribute("href")));
    assert.deepEqual(links.filter(href => !href.startsWith(base + "/")), [], "Base path escaped");
    assert.ok(links.some(href => href.startsWith(prefix + "/source/")), "Locale route missing");
    checked++;
  }
  await page.getByRole("combobox").first().selectOption("en");
  await page.waitForURL(`${origin}${base}/source/docs/runbook/?repo=owned/sample&file=owned.js`);
  await page.getByRole("combobox").first().selectOption("tr");
  await page.waitForURL(`${origin}${base}/tr/source/docs/runbook/?repo=owned/sample&file=owned.js`);
  assert.deepEqual(requests, [], "Public engine requests");
  assert.deepEqual(errors, [], "Public hydration errors");
  console.log(`PASS ${checked} Source Pages routes across ${locales.length} locales; base/query switches and no engine requests/actions`);
} finally { if (browser) await browser.close(); await new Promise(resolve => server.close(resolve)); }
