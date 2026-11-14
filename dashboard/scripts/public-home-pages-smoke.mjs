#!/usr/bin/env node
// Exercise the post-filtered public home with failed/successful release and clipboard requests.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { resolve, sep, extname } from "node:path";
import { chromium } from "@playwright/test";

const folder = resolve(process.argv[2] ?? "build-pages");
const base = "/os-lab";
const mime = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".json": "application/json", ".png": "image/png" };
const server = createServer(async (req, res) => {
  try {
    const path = new URL(req.url, "http://localhost").pathname;
    if (!path.startsWith(base + "/")) throw new Error("outside site");
    let file = resolve(folder, "." + decodeURIComponent(path.slice(base.length)));
    if (file !== folder && !file.startsWith(folder + sep)) throw new Error("outside artifact");
    if ((await stat(file)).isDirectory()) file += "/index.html";
    res.writeHead(200, { "Content-Type": mime[extname(file)] ?? "application/octet-stream" });
    res.end(await readFile(file));
  } catch { res.writeHead(404); res.end(); }
});
await new Promise(done => server.listen(0, "127.0.0.1", done));
let browser;
try {
  browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  const engineCalls = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => { if (new URL(request.url()).pathname.startsWith("/api/")) engineCalls.push(request.url()); });
  await page.addInitScript(() => Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: async () => { throw new Error("denied"); } } }));
  let releaseOk = false;
  await page.route("https://api.github.com/repos/keyvanarasteh/os-lab/releases/latest", route => releaseOk
    ? route.fulfill({ json: { tag_name: "v-test", html_url: "https://github.com/keyvanarasteh/os-lab/releases/tag/v-test", assets: [{ name: "os-lab_macos_universal.dmg", browser_download_url: "https://example.test/dmg" }] } })
    : route.abort());
  const origin = `http://127.0.0.1:${server.address().port}`;
  await page.goto(`${origin}${base}/`);
  await page.getByText("Release details unavailable. Open the latest release page.").waitFor();
  assert.ok((await page.locator('a[href$="/releases/latest"]').count()) > 0, "release fallback missing");
  await page.getByRole("button", { name: "Copy", exact: true }).first().click();
  await page.getByText("Clipboard unavailable. Select the text manually.").waitFor();
  releaseOk = true;
  await page.reload();
  await page.getByText("v-test").waitFor();
  assert.equal(await page.locator('a[href="https://example.test/dmg"]').count(), 1, "asset link missing");
  await page.evaluate(() => Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: async () => {} } }));
  await page.getByRole("button", { name: "Copy", exact: true }).first().click();
  await page.getByText("Copied", { exact: true }).waitFor();
  assert.deepEqual(errors, [], "public-home hydration errors");
  assert.deepEqual(engineCalls, [], "public-home engine requests");
  console.log("PASS public home: release fallback/asset and clipboard failure/success, no engine calls");
} finally {
  if (browser) await browser.close();
  await new Promise(done => server.close(done));
}
