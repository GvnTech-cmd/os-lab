#!/usr/bin/env node
// Interactive mac2 REPL for the macOS Lab: keeps one Appium mac2 session open against a
// chosen application and drives it over the WebDriver protocol with fetch — no extra npm
// packages beyond what `appium.sh install` already needs. A local operator tool: the web
// console keeps its preview → confirm model and never runs interactive sessions.
//
//   macos-repl.mjs <appium-url> <bundle-id> <artifacts-dir>
import readline from "node:readline";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const [,, BASE_URL, BUNDLE_ID, ARTIFACTS] = process.argv;
if (!BASE_URL || !BUNDLE_ID || !ARTIFACTS) {
  console.error("usage: macos-repl.mjs <appium-url> <bundle-id> <artifacts-dir>");
  process.exit(1);
}
const base = BASE_URL.replace(/\/$/, "");
const ELEMENT_KEY = "element-6066-11e4-a52e-4f735466cecf";

let session = null;
let found = []; // numbered elements from the last find

async function api(method, path, body) {
  const res = await fetch(base + path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  const value = data.value ?? {};
  if (!res.ok || value.error) throw new Error(value.message ?? value.error ?? res.statusText);
  return value;
}
const post = (path, body) => api("POST", path, body);
const get = (path) => api("GET", path);
const elementPath = (index) => `/session/${session}/element/${found[index][ELEMENT_KEY]}`;

async function startSession() {
  const value = await post("/session", { capabilities: { alwaysMatch: {
    platformName: "mac",
    "appium:automationName": "mac2",
    "appium:bundleId": BUNDLE_ID,
  } } });
  session = value.sessionId;
  console.log(`mac2 session ${session} on ${BUNDLE_ID}`);
  console.log('Type "help" for commands. Web pages and dialogs you automate are real.');
}

const HELP = `commands:
  state            print the app's accessibility tree (XML source)
  shot [name]      save a screenshot into ${ARTIFACTS}/
  find <text>      find elements whose label contains <text>; they get numbers
  click <n>        click element <n>
  type <n> <text>  send <text> to element <n>
  clear            forget the numbered elements
  quit             close the session and exit
  help             show this list`;

const commands = {
  async state() {
    const source = await get(`/session/${session}/source`);
    console.log(typeof source === "string" ? source : JSON.stringify(source, null, 2));
  },
  async shot(name) {
    const png = await get(`/session/${session}/screenshot`);
    mkdirSync(ARTIFACTS, { recursive: true });
    const file = join(ARTIFACTS, `macos-repl-${name || Date.now()}.png`);
    writeFileSync(file, Buffer.from(png, "base64"));
    console.log(file);
  },
  async find(query) {
    if (!query) throw new Error('usage: find <text>');
    const value = await post(`/session/${session}/elements`, {
      using: "xpath",
      value: `//*[contains(@label, ${JSON.stringify(query)})]`,
    });
    found = value.slice(0, 20);
    for (const [index, element] of found.entries()) {
      const id = `/session/${session}/element/${element[ELEMENT_KEY]}`;
      const type = await get(`${id}/name`).catch(() => "?");
      const text = await get(`${id}/text`).catch(() => "");
      console.log(`${index}: <${type}> ${String(text).slice(0, 80)}`);
    }
    console.log(found.length ? `${found.length} element(s); use click <n> or type <n> <text>` : "no elements matched");
  },
  async click([index]) {
    if (found[index] === undefined) throw new Error("no such numbered element; run find first");
    await post(`${elementPath(Number(index))}/click`);
    console.log(`clicked ${index}`);
  },
  async type([index, ...text]) {
    if (found[index] === undefined) throw new Error("no such numbered element; run find first");
    if (!text.length) throw new Error("usage: type <n> <text>");
    await post(`${elementPath(Number(index))}/value`, { text: text.join(" ") });
    console.log(`sent text to ${index}`);
  },
  clear() {
    found = [];
    console.log("element numbers cleared");
  },
  help() {
    console.log(HELP);
  },
};

async function closeSession() {
  if (session) await api("DELETE", `/session/${session}`).catch(() => {});
  process.exit(0);
}

const rl = readline.createInterface({ input: process.stdin, output: process.stdout, prompt: "mac2> " });
rl.on("close", closeSession);
await startSession().catch((error) => {
  console.error(`error: could not start the mac2 session on ${BUNDLE_ID}: ${error.message}`);
  console.error("Is Appium running with the mac2 driver installed, and did macOS ask for Accessibility permission?");
  process.exit(1);
});
rl.prompt();
for await (const line of rl) {
  const [command, ...args] = line.trim().split(/\s+/);
  try {
    if (!command) {
      // empty line: keep the prompt
    } else if (command === "quit" || command === "exit") {
      await closeSession();
    } else if (command === "help" || !commands[command]) {
      console.log(HELP);
    } else {
      await commands[command](args);
    }
  } catch (error) {
    console.error(`error: ${error.message}`);
  }
  rl.prompt();
}
