import { expect, test } from "@playwright/test";

/**
 * CLNP-23: the Space Explorer tab — a read-only size tree over registered
 * roots only. A walk names a root id; a drill-down sends a relative path
 * that stays inside the root; the unavailable root is never offered. All
 * through mocked typed endpoints (no engine calls, nothing deleted).
 */
const rootTree = {
  name: "home dev projects", path: "/tmp/projects", sizeBytes: 300, files: 12, folders: 3, truncated: false, unreadable: 0,
  children: [
    { name: "big-app", path: "/tmp/projects/big-app", sizeBytes: 220, files: 8, folders: 2, truncated: false, unreadable: 0, children: [
      { name: "target", path: "/tmp/projects/big-app/target", sizeBytes: 180, files: 6, folders: 1, truncated: false, unreadable: 0, children: [] },
      { name: "src", path: "/tmp/projects/big-app/src", sizeBytes: 40, files: 2, folders: 0, truncated: false, unreadable: 0, children: [] },
    ] },
    { name: "small-app", path: "/tmp/projects/small-app", sizeBytes: 80, files: 4, folders: 1, truncated: true, unreadable: 2, children: [] },
  ],
};
const subtreeTrees: Record<string, unknown> = {
  "big-app": { name: "big-app", path: "/tmp/projects/big-app", sizeBytes: 220, files: 8, folders: 2, truncated: false, unreadable: 0, children: [
    { name: "target", path: "/tmp/projects/big-app/target", sizeBytes: 180, files: 6, folders: 1, truncated: false, unreadable: 0, children: [] },
    { name: "src", path: "/tmp/projects/big-app/src", sizeBytes: 40, files: 2, folders: 0, truncated: false, unreadable: 0, children: [] },
  ] },
  "big-app/target": { name: "target", path: "/tmp/projects/big-app/target", sizeBytes: 180, files: 6, folders: 1, truncated: false, unreadable: 0, children: [
    { name: "debug", path: "/tmp/projects/big-app/target/debug", sizeBytes: 175, files: 6, folders: 0, truncated: false, unreadable: 0, children: [] },
  ] },
};

async function mockApis(page: import("@playwright/test").Page, { refuse = false } = {}) {
  const calls: { path: string; body: Record<string, unknown> }[] = [];
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const body = route.request().postDataJSON?.() ?? {};
    if (route.request().method() === "POST") calls.push({ path, body });
    let data: unknown = {};
    if (path === "/api/cleanup/status") data = { state: "ready", reasons: [], requirements: [], capabilities: [] };
    else if (path === "/api/cleanup/monitor") data = { enabled: false, running: false, intervalSeconds: 300, cooldownSeconds: 3600, volumes: [], state: { volumes: {}, events: [], lastEvaluationAt: null, lastError: null }, activeWarnings: [], configError: null, checkedAt: 1 };
    else if (path === "/api/cleanup/volumes") data = { platform: "macos", threshold: 0.9, volumes: [], homeVolume: null, warnings: [], error: null };
    else if (path === "/api/cleanup/bookmarks") data = { bookmarks: [], error: null };
    else if (path === "/api/cleanup/permissions") data = { platform: "macos", permissions: [] };
    else if (path === "/api/cleanup/catalog") data = { platform: "macos", entries: [] };
    else if (path === "/api/cleanup/jobs") data = { jobs: [] };
    else if (path === "/api/cleanup/explorer/roots") data = { roots: [
      { id: "home-dev-projects", name: "Home dev projects", source: "deep-roots", path: "/tmp/projects", available: true, reason: "" },
      { id: "shared-logs", name: "Shared logs", source: "custom", path: "/tmp/shared-logs", available: true, reason: "" },
      { id: "gone-root", name: "Gone root", source: "deep-roots", path: null, available: false, reason: "path does not exist" },
    ] };
    else if (path === "/api/cleanup/explorer/scan") {
      if (refuse) return route.fulfill({ status: 400, json: { error: "Unknown root id(s): missing-root" } });
      data = { id: "job-walk", kind: "explorer", state: "running", request: body, progress: { currentPath: "/tmp/projects" }, result: null, error: null };
    }
    else if (path === "/api/cleanup/explorer/subtree") {
      if (!(String(body.relative ?? "") in subtreeTrees)) return route.fulfill({ status: 400, json: { error: "Refused: the path leaves the root" } });
      data = { id: "job-walk", kind: "explorer", state: "running", request: body, progress: null, result: null, error: null };
    }
    else if (path === "/api/cleanup/jobs/job-walk") {
      const request = [...calls].reverse().find((call) => call.path.startsWith("/api/cleanup/explorer/"))?.body ?? {};
      const relative = String(request.relative ?? "");
      const tree = relative ? subtreeTrees[relative] : rootTree;
      data = { id: "job-walk", kind: "explorer", state: "done", request, progress: null,
        result: { rootId: "home-dev-projects", path: "/tmp/projects", relative: relative || null, tree, nodes: 15, truncated: false, cancelled: false, checkedAt: 1 }, error: null };
    }
    else if (path === "/api/host") data = { host: { os: "macos", osPretty: "macOS", arch: "arm64", hostname: "test", cpus: 8, memory: 0, disk: null, kvm: { present: false, usable: false }, wsl: { guest: false, distributions: [] }, runtime: null, xcode: null, python: "3.12", root: "/tmp", tools: [], providers: [] }, labs: [] };
    else if (path === "/api/health") data = { status: "ok", version: "test", console: true };
    else if (path === "/api/jobs") data = { jobs: [] };
    else if (path === "/api/logs") data = { logs: [] };
    await route.fulfill({ json: data });
  });
  return calls;
}

test("space explorer measures a root, drills down and walks breadcrumbs", async ({ page }) => {
  page.on("pageerror", (error) => console.log("PAGEERROR:", String(error)));
  const calls = await mockApis(page);
  await page.goto("/cleanup/space/");
  await expect(page.getByRole("heading", { name: "Space Explorer" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Space Explorer" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByText("Pick a root and measure it to see its folders by size.")).toBeVisible();

  // The first available root is preselected; the unavailable one is never offered.
  const rootSelect = page.getByLabel("Root");
  await expect(rootSelect).toHaveValue("home-dev-projects");
  await expect(rootSelect).toContainText("Home dev projects");
  await expect(rootSelect).toContainText("Shared logs (your folder)");
  await expect(rootSelect).not.toContainText("Gone root");

  await page.getByRole("button", { name: "Measure", exact: true }).click();
  expect(calls.find((call) => call.path === "/api/cleanup/explorer/scan")?.body).toEqual({ rootId: "home-dev-projects" });
  // dua-style rows, largest first, with sizes, counts and honesty markers
  const big = page.getByRole("button", { name: "big-app" });
  const small = page.getByRole("button", { name: "small-app" });
  await expect(big).toBeVisible();
  await expect(small).toBeVisible();
  expect((await big.boundingBox())!.y).toBeLessThan((await small.boundingBox())!.y);
  await expect(page.getByText("8 files · 2 folders")).toBeVisible();
  await expect(page.getByText("partial", { exact: true })).toBeVisible();
  await expect(page.getByText("2 unreadable")).toBeVisible();
  await expect(page.getByText("300 B · 15 entries", { exact: false })).toBeVisible();
  await expect(page.getByRole("link", { name: "Advanced scan" }).last()).toHaveAttribute("href", /\/cleanup\/scan\/$/);

  // Drill-down: a relative path inside the root, one level at a time.
  await big.click();
  expect(calls.filter((call) => call.path === "/api/cleanup/explorer/subtree").at(-1)?.body)
    .toEqual({ rootId: "home-dev-projects", relative: "big-app" });
  await expect(page.getByRole("button", { name: "home dev projects" })).toBeVisible();
  await page.getByRole("button", { name: "target" }).click();
  expect(calls.filter((call) => call.path === "/api/cleanup/explorer/subtree").at(-1)?.body)
    .toEqual({ rootId: "home-dev-projects", relative: "big-app/target" });
  await expect(page.getByRole("button", { name: "debug" })).toBeVisible();

  // The middle breadcrumb segment navigates back up; the root name re-measures.
  await page.getByRole("button", { name: "big-app" }).click();
  expect(calls.filter((call) => call.path === "/api/cleanup/explorer/subtree").at(-1)?.body)
    .toEqual({ rootId: "home-dev-projects", relative: "big-app" });
  await expect(page.getByRole("button", { name: "target" })).toBeVisible();
  await page.getByRole("button", { name: "home dev projects" }).click();
  expect(calls.filter((call) => call.path === "/api/cleanup/explorer/scan")).toHaveLength(2);
  await expect(page.getByRole("button", { name: "small-app" })).toBeVisible();
});

test("an unknown root id is refused with the typed error and nothing walks", async ({ page }) => {
  const calls = await mockApis(page, { refuse: true });
  await page.goto("/cleanup/space/");
  await expect(page.getByRole("heading", { name: "Space Explorer" })).toBeVisible();
  await page.getByRole("button", { name: "Measure", exact: true }).click();
  expect(calls.find((call) => call.path === "/api/cleanup/explorer/scan")?.body).toEqual({ rootId: "home-dev-projects" });
  await expect(page.getByText("Unknown root id(s): missing-root")).toBeVisible();
  // No tree, no rows: the refusal left nothing to browse.
  await expect(page.getByRole("button", { name: "big-app" })).toHaveCount(0);
});
