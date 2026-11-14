import { expect, test, type Page } from "@playwright/test";
async function sourceShell(page: Page) {
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = {};
    if (path === "/api/health") json = { status: "ok" };
    if (path === "/api/host") json = { host: { os: "linux", arch: "x86_64" }, labs: [{ id: "source", label: "Source Lab", state: "ready", actions: [] }] };
    if (path === "/api/jobs") json = { jobs: [] };
    if (path === "/api/logs") json = { logs: [] };
    if (path === "/api/source/settings/runtime") json = { key: { configured: false, source: "none", problem: null }, canary: { testUrl: "https://example.test" }, playwright: false };
    if (path === "/api/source/detection") json = { targets: [{ key: "targets/sample", name: "sample", slug: "owned__sample" }], runner: { ready: true }, run: null };
    if (path === "/api/source/evidence") json = new URL(route.request().url()).searchParams.has("slug") ? { slug: "owned__sample", findings: [], coverage: { limitations: ["Static only"] }, scorecard: {}, sessions: [], reports: [] } : { targets: [{ slug: "owned__sample", platform: "browser-extension" }], truncated: false };
    if (path === "/api/source/analyzer") json = { run: null, report: null, summaryCount: 0, summaryRows: [], sourceFiles: [{ name: "owned.txt", format: "TXT" }], sourceFilesTruncated: false };
    if (path === "/api/source/analyzer/merged") json = matrixFixture;
    if (path === "/api/source/sources") json = { stats: {}, files: [], mergedExtensions: [], curated: [], monitored: [] };
    if (path === "/api/source/spotlight") json = { data: [{ title: "owned__sample", href: "/source/evidence/?slug=owned__sample" }] };
    await route.fulfill({ json });
  });
}

test("Source destinations hydrate and preserve query links", async ({ page }) => {
  await sourceShell(page);
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  for (const route of ["", "analyzer", "evidence", "deep-analysis", "pipeline", "brain", "sources", "settings/runtime"]) {
    await page.goto(`/source/${route ? route + "/" : ""}?repo=owned/sample&file=main.js`);
    await expect(page.getByRole("navigation", { name: "Source Lab pages" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Source Lab pages" }).getByRole("link", { name: "Readiness & setup" })).toHaveAttribute("href", "/labs/source/");
    expect(new URL(page.url()).searchParams.get("repo")).toBe("owned/sample");
  }
  expect(errors).toEqual([]);
});

test("Source Spotlight record opens its target and Escape restores focus", async ({ page }) => {
  await sourceShell(page);
  await page.goto("/source/");
  await expect(page.getByRole("navigation", { name: "Source Lab pages" })).toBeVisible();
  await page.keyboard.press("Control+k");
  const search = page.getByRole("combobox", { name: "Spotlight search" });
  await expect(search).toBeFocused();
  await search.fill("owned");
  await page.getByRole("option", { name: /owned__sample/ }).click();
  await expect(page).toHaveURL(/source\/evidence\/\?slug=owned__sample/);
  await expect(page.getByRole("navigation", { name: "Source Lab pages" })).toBeVisible();
  await page.keyboard.press("Control+k");
  await expect(search).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(search).not.toBeVisible();
});

test("Source mobile drawer and theme work", async ({ page }) => {
  await sourceShell(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/source/deep-analysis/?repo=owned/sample&file=main.js");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.getByRole("dialog", { name: "Navigation" })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Toggle theme" }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBe(true);
});

const matrixFixture = {
  stats: { totalAnalyzed: 1, mv2Count: 1, uniqueDepsCount: 1 }, truncated: false,
  propsMatrix: [{ name: "browser_action", count: 1, slugs: ["owned__sample"], category: "UI Surface", mv2: 1, mv3: 0, mvStatus: "MV2 Only", specNote: "Pinned fixture note", migrationNote: "Use action instead" }],
  depsMatrix: [{ name: "react", count: 1, slugs: ["owned__sample"], category: "UI / Framework", sections: ["dependencies"] }],
  permsMatrix: [{ name: "nativeMessaging", count: 1, slugs: ["owned__sample"], risk: "high" }],
  swGroups: { serviceWorker: [], persistentScript: ["owned__sample"], backgroundPage: [], none: [] },
  extensions: [{ slug: "owned__sample", repo: "owned/sample", name: "Owned fixture", manifestVersion: "2", version: "1", description: "Owned fixture only", riskLevel: "HIGH", heuristicScore: 3, backgroundType: "persistentScript", dependenciesCount: 1, permissions: ["nativeMessaging"] }]
};
test("Source Overview matrices filter, inspect notes, link targets and export", async ({ page }) => {
  await sourceShell(page);
  await page.route("**/api/source/analyzer/merged*", route => route.fulfill({ json: matrixFixture }));
  await page.goto("/source/");
  await expect(page.getByRole("tabpanel").getByText("browser_action")).toBeVisible();
  await page.getByRole("tabpanel").getByRole("button", { name: "Inspect" }).click();
  const inspector = page.getByRole("dialog", { name: "Source inspector" });
  await expect(inspector.getByText("Use action instead")).toBeVisible();
  await expect(inspector.getByRole("link", { name: "owned__sample" })).toHaveAttribute("href", "/source/deep-analysis/?repo=owned%2Fsample");
  await page.keyboard.press("Escape");
  await page.getByRole("tab", { name: "Dependencies" }).click();
  await expect(page.getByRole("tabpanel").getByText("react")).toBeVisible();
  await page.getByRole("tab", { name: "Dependencies" }).press("ArrowRight");
  await expect(page.getByRole("tab", { name: "Permissions" })).toBeFocused();
  await expect(page.getByRole("tabpanel").getByText("nativeMessaging")).toBeVisible();
  await page.getByLabel("Filter results").fill("absent");
  await expect(page.getByText("No matching results. Add authorized targets or adjust filters.")).toBeVisible();
  await expect(page).toHaveURL(/tab=perms&q=absent/);
  await expect(page.getByRole("link", { name: "Download CSV" })).toHaveAttribute("href", "/api/source/analyzer/merged?export=csv");
});
test("Source Overview and catalogs report loading, empty and failed requests", async ({ page }) => {
  await sourceShell(page);
  await page.route("**/api/source/analyzer/merged*", async route => {
    await new Promise(resolve => setTimeout(resolve, 250));
    await route.fulfill({ status: 400, json: { error: "Invalid private artifact" } });
  });
  await page.goto("/source/");
  await expect(page.locator('[aria-busy="true"]')).toBeVisible();
  await expect(page.getByRole("alert")).toHaveText("Invalid private artifact");
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  await page.route("**/api/source/sources*", route => route.fulfill({ json: { stats: {}, files: [], mergedExtensions: [], curated: [], monitored: [] } }));
  await page.goto("/source/sources/");
  await expect(page.getByText("No matching sources.")).toBeVisible();
});

test("Source crawler validates inputs and previews, runs, polls and cancels", async ({ page }) => {
  await sourceShell(page);
  let started = false; let cancelled = false;
  const job = { id: "source-fixture-job", lab: "source", action: "crawl", label: "Owned crawl", state: "running", command: "python3 source-lab/run.py crawl owned/sample", lines: 1, logs: ["Analyzing owned/sample"], truncated: false };
  await page.route("**/api/source/analyzer", async route => {
    if (route.request().method() === "GET") return route.fallback();
    const body = route.request().postDataJSON();
    expect(body.options).toEqual({ repos: ["owned/sample"], workers: 2, depth: 1, noAst: true, noMetadata: true, resume: false, keepWorkspace: true });
    if (body.preview) return route.fulfill({ json: { plan: { display: job.command, effects: ["Contacts GitHub for selected sources"], timeoutSec: 3600 }, token: "fixture-confirmation" } });
    expect(body.token).toBe("fixture-confirmation"); started = true;
    return route.fulfill({ status: 202, json: { job } });
  });
  await page.route("**/api/jobs/source-fixture-job", route => route.fulfill({ json: job }));
  await page.route("**/api/jobs/source-fixture-job/cancel", route => { cancelled = true; return route.fulfill({ json: { ...job, state: "cancelled", logs: ["Cancelled by operator"] } }); });
  await page.goto("/source/analyzer/");
  await expect(page.getByRole("button", { name: "Preview crawl" })).toBeDisabled();
  await page.getByLabel("GitHub repositories").fill("https://user:credential@example.test/private");
  await expect(page.getByRole("button", { name: "Preview crawl" })).toBeDisabled();
  await page.getByLabel("GitHub repositories").fill("owned/sample");
  await page.getByLabel("Workers", { exact: true }).fill("2");
  await page.getByRole("button", { name: "Preview crawl" }).click();
  await expect(page.getByRole("region", { name: "Crawl preview" })).toContainText("Contacts GitHub");
  expect(started).toBe(false);
  await page.getByRole("button", { name: "Confirm and run" }).click();
  await expect(page.getByLabel("Crawler logs")).toContainText("Analyzing owned/sample");
  await expect(page.getByRole("button", { name: "Preview crawl" })).toBeDisabled();
  await page.getByRole("button", { name: "Cancel crawl" }).click();
  await expect(page.getByLabel("Crawler logs")).toContainText("Cancelled by operator");
  expect(started && cancelled).toBe(true);
});

test("Source crawler list selection invalidates preview and shows request errors", async ({ page }) => {
  await sourceShell(page);
  let requests = 0;
  await page.route("**/api/source/analyzer", async route => {
    if (route.request().method() === "GET") return route.fallback();
    const body = route.request().postDataJSON(); expect(body.options.sourceFile).toBe("owned.txt");
    if (++requests === 1) return route.fulfill({ json: { plan: { display: "python3 crawl --input owned.txt", effects: [], timeoutSec: 3600 }, token: "fixture" } });
    return route.fulfill({ status: 409, json: { error: "Private workspace is busy" } });
  });
  await page.goto("/source/analyzer/");
  await page.getByLabel("Input mode").selectOption("source");
  await page.getByRole("combobox", { name: /^Source list/ }).selectOption("owned.txt");
  await page.getByRole("button", { name: "Preview crawl" }).click();
  await expect(page.getByRole("button", { name: "Confirm and run" })).toBeVisible();
  await page.getByLabel("Clone depth").fill("2");
  await expect(page.getByRole("button", { name: "Confirm and run" })).not.toBeVisible();
  await page.getByRole("button", { name: "Preview crawl" }).click();
  await expect(page.getByRole("alert")).toHaveText("Private workspace is busy");
});

test("Source crawler honors live missing requirements", async ({ page }) => {
  await sourceShell(page);
  await page.route("**/api/host", route => route.fulfill({ json: { host: { os: "linux", arch: "x86_64" }, labs: [{ id: "source", state: "ready", actions: [], requirements: [{ id: "git", found: false, required: false }] }] } }));
  await page.goto("/source/analyzer/");
  await page.getByLabel("GitHub repositories").fill("owned/sample");
  await expect(page.getByRole("button", { name: "Preview crawl" })).toBeDisabled();
  await expect(page.getByText("Crawler needs live Source Lab readiness and Git. Check Readiness & setup for missing requirements.")).toBeVisible();
});

for (const platform of ["browser-extension", "windows-app", "macos-app", "android-app", "ios-app"]) {
  test(`Evidence preserves ${platform} states, coverage and verification`, async ({ page }) => {
    await sourceShell(page);
    await page.route("**/api/source/evidence?slug=*", route => route.fulfill({ json: {
      slug: "owned__sample", platform, coverage: { parser_mode: "fixture", limitations: ["Partial fixture coverage"] },
      scorecard: { dimensions: { H1: { score: 1 } }, note: "Static triage only" }, sessions: [], reports: ["findings.json"],
      findings: [{ finding_id: "owned.rule", platform, state: "static_lead", severity: "high", confidence: 0.5,
        hypothesis: "Owned fixture hypothesis", evidence: [{ file: "owned.js", line: 1, artifact: "source" }],
        verification: "Owned decisive test", alternative_explanations: ["Benign fixture"], limitations: [], remediation: "Review fixture" }]
    } }));
    await page.goto("/source/evidence/?slug=owned__sample");
    await expect(page.getByText("Owned fixture hypothesis")).toBeVisible();
    await page.getByText("Coverage", { exact: true }).click();
    await expect(page.getByText(/Partial fixture coverage/)).toBeVisible();
    await page.getByText("Verification", { exact: true }).click();
    await expect(page.getByText(/Owned decisive test/)).toBeVisible();
    await expect(page.getByRole("link", { name: "findings.json" })).toHaveAttribute("href", /evidence\/report\?slug=owned__sample&file=findings.json/);
    await page.getByRole("combobox", { name: /^State/ }).selectOption("correlated_behavior");
    await expect(page.getByText("Owned fixture hypothesis")).not.toBeVisible();
  });
}

test("Runtime rotation requires acknowledgement and environment keys stay read-only", async ({ page }) => {
  await sourceShell(page);
  const runtime = { key: { configured: true, source: "managed-file", problem: null }, canary: { testUrl: "https://example.test" }, playwright: false };
  await page.route("**/api/source/settings/runtime", route => route.fulfill({ json: runtime }));
  await page.goto("/source/settings/runtime/");
  await expect(page.getByRole("button", { name: "Preview action" })).toBeDisabled();
  await page.getByRole("checkbox").check();
  await expect(page.getByRole("button", { name: "Preview action" })).toBeEnabled();
  runtime.key.source = "env";
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByText("The environment owns this key. Change it outside the dashboard.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Preview action" })).toBeDisabled();
  await page.getByRole("combobox", { name: /^Action/ }).selectOption("set-canary");
  await expect(page.getByLabel("Configured canary URL")).toHaveValue("https://example.test");
  await page.getByLabel("Configured canary URL").fill("https://user:secret@example.test/?secret=fixture");
  await expect(page.getByRole("button", { name: "Preview action" })).toBeDisabled();
});

test("Deep analysis preserves source links, legacy AST and structural map coverage", async ({ page }) => {
  await sourceShell(page);
  const bundle = { repo: "owned/sample", slug: "owned__sample", manifestAnalysis: {}, metadata: {}, dependencies: {}, fileTree: [{ path: "main.js", type: "blob" }], astIndex: [], repoMap: {
    schema_version: 1, stats: { files: 1 }, targets: [], coverage: { limitations: ["Partial owned map"] }, entrypoints: [],
    files: { "main.js": { lang: "javascript", parser: "regex", role: { kind: "entry", confidence: 0.8 }, symbols: [{ name: "owned" }], imports: [] } }
  } };
  await page.route("**/api/source/deep-analysis*", route => {
    const url = new URL(route.request().url());
    const json = url.searchParams.has("file") ? url.searchParams.get("view") === "ast" ? { ast: { parser: "legacy", nodes: ["owned"] } } : { content: "console.log('owned source');" } : url.searchParams.has("repo") ? bundle : { analyzedRepos: [bundle], availableRepos: [], truncated: false };
    return route.fulfill({ json });
  });
  await page.goto("/source/deep-analysis/?repo=owned/sample&file=main.js");
  await expect(page.getByText("console.log('owned source');", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "AST", exact: true }).click();
  await page.getByText("AST", { exact: true }).last().click();
  await expect(page.getByText(/legacy/)).toBeVisible();
  await page.getByRole("button", { name: "Structural map", exact: true }).click();
  const map = page.getByRole("dialog", { name: "Structural map" });
  await map.getByText("Coverage", { exact: true }).click();
  await expect(map.getByText(/Partial owned map/)).toBeVisible();
  await map.getByRole("button", { name: "main.js", exact: true }).click();
  await expect(page).toHaveURL(/repo=owned%2Fsample&file=main.js/);
});

test("Pipeline labels its pinned fallback and exposes stage inputs and network details", async ({ page }) => {
  await sourceShell(page);
  await page.route("**/api/source/pipeline", route => route.fulfill({ status: 404, json: { error: "No operator snapshot" } }));
  await page.goto("/source/pipeline/");
  await expect(page.getByText("Pinned architecture reference; no live run or automatic regeneration is implied.")).toBeVisible();
  await page.getByRole("button", { name: /Shallow clone repository/ }).click();
  await page.getByText("Network", { exact: true }).first().click();
  await expect(page.getByRole("main").getByText(/github.com/, { exact: false }).first()).toBeVisible();
  await expect(page.getByText(/2026-11-09/)).toBeVisible();
});

test("Brain loads an owned tab", async ({ page }) => {
  await sourceShell(page);
  await page.route("**/api/source/brain", route => route.fulfill({ json: { data: { manifest: { tabs: [{ id: "owned", label: "Owned graph", file: "owned.json" }] } } } }));
  await page.route("**/api/source/brain/files/owned.json", route => route.fulfill({ json: { nodes: [{ id: "owned", label: "Owned", type: "service" }], edges: [] } }));
  await page.goto("/source/brain/");
  await expect(page.getByRole("button", { name: "Owned graph" })).toBeVisible();
  await expect(page.getByText(/1 nodes/)).toBeVisible();
});

test("Brain graph, providers, rankings and export preserve snapshot boundaries", async ({ page }) => {
  await sourceShell(page);
  const graph = { meta: { analyzedAt: "2026-11-09", project: "Owned fixture" }, nodes: [
    { id: "a", label: "Owned service", type: "service", data: { file: "owned.js", metrics: { cyclomaticComplexity: 3 }, flowSteps: [{ type: "call", label: "Owned call" }] } },
    { id: "b", label: "Owned job", type: "job", data: {} }
  ], edges: [{ id: "ab", source: "a", target: "b", label: "dispatch", type: "call" }] };
  await page.route("**/api/source/brain", route => route.fulfill({ json: { data: { manifest: { tabs: [{ id: "owned", label: "Owned graph", file: "owned.json" }], providers: { source: "source.json", history: "history.json", aiRules: "rules.json" } } } } }));
  await page.route("**/api/source/brain/files/*", route => {
    const file = new URL(route.request().url()).pathname.split("/").pop();
    const json = file === "owned.json" ? graph : file === "source.json" ? { "owned.js": { content: "return owned;" } } : file === "history.json" ? { "owned.js": [{ revision: "old", content: "old owned;" }, { revision: "new", content: "new owned;" }] } : { a: "Owned static rule" };
    return route.fulfill({ json });
  });
  await page.goto("/source/brain/");
  await page.getByRole("button", { name: "Owned service", exact: true }).first().click();
  await expect(page).toHaveURL(/node=a/);
  await page.getByRole("button", { name: "Source", exact: true }).click();
  await expect(page.getByText("return owned;", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Diff", exact: true }).click();
  await expect(page.getByText("old owned;", { exact: true })).toBeVisible();
  await expect(page.getByText("new owned;", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Flowchart", exact: true }).click();
  await expect(page.getByText("call → Owned call", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "AI rules", exact: true }).click();
  await page.getByRole("button", { name: "AI rules", exact: true }).last().click();
  await expect(page.getByRole("dialog", { name: "AI rules" })).toContainText("Owned static rule");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Usages", exact: true }).click();
  await expect(page.getByRole("button", { name: "a → b · dispatch", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Sequence", exact: true }).click();
  await expect(page.getByText("Snapshot relationships are not a runtime trace.")).toBeVisible();
  await page.getByRole("button", { name: "History", exact: true }).click();
  await expect(page.getByText("old owned;", { exact: true })).toBeVisible();
  for (const mode of ["Complexity", "Risk"]) {
    await page.getByRole("button", { name: mode, exact: true }).click();
    await expect(page.getByText("Recorded metrics rank review priorities; they are not security findings.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Owned service · 3", exact: true })).toBeVisible();
  }
  await page.getByRole("button", { name: "Stress", exact: true }).click();
  await expect(page.getByText("Live stress testing is unavailable without an application provider.")).toBeVisible();
  await page.getByRole("button", { name: "Export", exact: true }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download JSON", exact: true }).click();
  expect((await download).suggestedFilename()).toBe("source-brain-owned.json");
});

test("Brain virtual window filters locally and exports the complete owned graph", async ({ page }) => {
  await sourceShell(page);
  const graph = { nodes: Array.from({ length: 250 }, (_, i) => ({ id: String(i), type: i % 2 ? "job" : "service", label: `Owned ${i}`, data: {} })), edges: [] };
  await page.route("**/api/source/brain", route => route.fulfill({ json: { data: { manifest: { tabs: [{ id: "owned", label: "Owned graph", file: "owned.json" }] } } } }));
  await page.route("**/api/source/brain/files/*", route => route.fulfill({ json: graph }));
  await page.goto("/source/brain/");
  const canvas = page.getByRole("group", { name: "Snapshot graph" });
  await expect(canvas.getByRole("button")).toHaveCount(100);
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(canvas.getByRole("button", { name: "Owned 100", exact: true })).toBeVisible();
  await page.getByLabel("Filter results").fill("Owned 249");
  await expect(canvas.getByRole("button")).toHaveCount(1);
  await canvas.getByRole("button").focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/node=249/);
  await page.getByRole("button", { name: "Source", exact: true }).click();
  await expect(page.getByText("This provider is unavailable. Configure an authorized local snapshot.")).toBeVisible();
  await page.getByRole("button", { name: "Export", exact: true }).click();
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download JSON", exact: true }).click();
  const download = await pending;
  const { readFileSync } = await import("node:fs");
  expect(JSON.parse(readFileSync((await download.path())!, "utf8")).nodes.length).toBe(250);
});

test("Source workflow docs render and keep internal guide links local", async ({ page }) => {
  await sourceShell(page);
  await page.goto("/source/docs/runbook/");
  await expect(page.getByRole("article").getByRole("heading", { name: "Source Lab operator and release runbook", exact: true })).toBeVisible();
  await expect(page.getByRole("article").getByRole("link", { name: "Legacy import", exact: true })).toHaveAttribute("href", "/source/docs/import/");
  await page.goto("/tr/source/docs/import/");
  await expect(page.locator("html")).toHaveAttribute("lang", "tr");
  await expect(page.getByRole("article")).toHaveAttribute("lang", "en");
  await expect(page.locator('main nav a[href="/tr/source/docs/runbook/"]')).toBeVisible();
});
