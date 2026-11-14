import { expect, test } from "@playwright/test";

/**
 * CLNP-18: bookmark affordances on scan cards and history items, the
 * bookmarks section with its flags, and quick clean opening the plan
 * confirmation — all through mocked typed endpoints (no engine calls).
 */
const scan = {
  cancelled: false,
  entries: [{ id: "system.caches", name: "Caches", category: "system", risk: "low", sizeBytes: 42, files: 1, folders: 1, unreadable: [], paths: [{ path: "/tmp/caches", reason: "", source: "catalog", sizeBytes: 42, error: null }] }],
  totals: { sizeBytes: 42, files: 1, folders: 1, unreadable: 0 }
};
const plan = {
  planId: "plan-bookmark", mode: "trash", expiresAt: Date.now() / 1000 + 600,
  items: [{ entryId: "system.caches", entryName: "Caches", path: "/tmp/caches", status: "ready", code: "", reason: "", source: "catalog", sizeBytes: 42, files: 1, folders: 1 }],
  totals: { ready: 1, skipped: 0, bytes: 42 }
};
const bookmarksPayload = (bookmarked: boolean) => ({
  bookmarks: bookmarked ? [{
    entryId: "system.caches", createdAt: 1000, priority: 1, quickClean: true,
    autoCleanHook: { enabled: false, lastRunAt: null },
    sizeAlert: { enabled: true, thresholdBytes: 1024 * 1024 * 1024, armed: true, lastAlertAt: null },
    entry: { name: "Caches", risk: "low", category: "system", needsPrivilege: false, paths: [{ template: "~/Caches", path: "/tmp/caches", reason: "" }] }
  }] : [],
  error: null
});

type BookmarksPayloadFn = () => ReturnType<typeof bookmarksPayload>;
async function mockApis(page: import("@playwright/test").Page, loadBookmarks: BookmarksPayloadFn) {
  const calls: { path: string; body: Record<string, unknown> }[] = [];
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const body = route.request().postDataJSON?.() ?? {};
    if (route.request().method() === "POST") calls.push({ path, body });
    let data: unknown = {};
    if (path === "/api/cleanup/status") data = { state: "ready", reasons: [], requirements: [], capabilities: [] };
    else if (path === "/api/cleanup/catalog") data = { platform: "macos", entries: [{ id: "system.caches", name: "Caches", category: "system", risk: "low", hint: "Safe cache", impact: "", defaultSelected: true, needsPrivilege: false, paths: [{ template: "~/Caches", path: "/tmp/caches", reason: "" }] }] };
    else if (path === "/api/cleanup/jobs") data = { jobs: [] };
    else if (path === "/api/cleanup/permissions") data = { platform: "macos", permissions: [] };
    else if (path === "/api/cleanup/monitor") data = { enabled: false, running: false, intervalSeconds: 300, cooldownSeconds: 3600, volumes: [{ mountPoint: "", minFreeBytes: 0, minFreePercent: 10, enabled: true, volume: null }], state: { volumes: {}, events: [], lastEvaluationAt: null, lastError: null }, activeWarnings: [], configError: null, checkedAt: 1 };
    else if (path === "/api/cleanup/volumes") data = { platform: "macos", threshold: 0.9, volumes: [], homeVolume: null, warnings: [], error: null };
    else if (path === "/api/cleanup/bookmarks") data = loadBookmarks();
    else if (path === "/api/cleanup/bookmarks/quick-clean") data = { job: { id: "job-plan", kind: "plan", state: "running", request: body, progress: {}, result: null, error: null }, refusals: [] };
    else if (path === "/api/cleanup/jobs/job-plan") data = { id: "job-plan", kind: "plan", state: "done", request: { entryIds: ["system.caches"], mode: "trash" }, progress: {}, result: plan, error: null };
    else if (path === "/api/host") data = { host: { os: "macos", osPretty: "macOS", arch: "arm64", hostname: "test", cpus: 8, memory: 0, disk: null, kvm: { present: false, usable: false }, wsl: { guest: false, distributions: [] }, runtime: null, xcode: null, python: "3.12", root: "/tmp", tools: [], providers: [] }, labs: [] };
    else if (path === "/api/health") data = { status: "ok", version: "test", console: true };
    else if (path === "/api/jobs") data = { jobs: [] };
    else if (path === "/api/logs") data = { logs: [] };
    await route.fulfill({ json: data });
  });
  return calls;
}

test("scan card bookmark toggles and quick clean opens the confirm dialog", async ({ page }) => {
  page.on("pageerror", (error) => console.log("PAGEERROR:", String(error)));
  page.on("console", (msg) => { if (msg.type() === "error") console.log("CONSOLE:", msg.text()); });
  let marked = false;
  const calls = await mockApis(page, () => bookmarksPayload(marked));
  await page.goto("/cleanup/scan/");
  await expect(page.getByRole("heading", { name: "Scan", exact: false })).toBeVisible();

  await page.getByRole("button", { name: "Bookmark this item" }).click();
  marked = true;
  await page.goto("/cleanup/");
  await expect(page.getByText("Caches", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Quick clean bookmarks" }).click();
  await expect(page.getByRole("dialog")).toContainText("Move to Trash");
  expect(calls.find((call) => call.path === "/api/cleanup/bookmarks/quick-clean")).toBeTruthy();
});
