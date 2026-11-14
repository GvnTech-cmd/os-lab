import { expect, test } from "@playwright/test";

/**
 * CLNP-08: tab navigation swaps in place — no document reload, real URLs,
 * back/forward re-derives the page, deep links still land on the right tab.
 * A `window` marker set before the click proves the document never reloaded.
 */
test("cleanup tabs navigate in place without a reload", async ({ page }) => {
  const permissionsPayloads: number[] = [];
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = {};
    if (path === "/api/cleanup/status") data = { state: "ready", reasons: [], requirements: [], capabilities: [] };
    else if (path === "/api/cleanup/catalog") data = { platform: "macos", entries: [] };
    else if (path === "/api/cleanup/jobs") data = { jobs: [] };
    else if (path === "/api/cleanup/permissions") {
      permissionsPayloads.push(Date.now());
      data = { platform: "macos", permissions: [] };
    } else if (path === "/api/cleanup/history") data = { entries: [], total: 0, verified: true };
    else if (path === "/api/host") data = { host: { os: "macos", osPretty: "macOS", arch: "arm64", hostname: "test", cpus: 8, memory: 0, disk: null, kvm: { present: false, usable: false }, wsl: { guest: false, distributions: [] }, runtime: null, xcode: null, python: "3.12", root: "/tmp", tools: [], providers: [] }, labs: [] };
    else if (path === "/api/health") data = { status: "ok", version: "test", console: true };
    else if (path === "/api/jobs") data = { jobs: [] };
    else if (path === "/api/logs") data = { logs: [] };
    await route.fulfill({ json: data });
  });

  await page.goto("/cleanup/");
  await expect(page.getByRole("heading", { name: "Cleanup Lab" }).first()).toBeVisible();
  await page.evaluate(() => { (window as unknown as { __e2eMarker?: number }).__e2eMarker = 42; });

  // Tab change: URL updates, no reload (marker survives), aria-current moves.
  await page.getByRole("link", { name: "Results" }).click();
  await expect(page).toHaveURL(/\/cleanup\/results\/$/);
  await expect(page.getByRole("link", { name: "Results" })).toHaveAttribute("aria-current", "page");
  expect(await page.evaluate(() => (window as unknown as { __e2eMarker?: number }).__e2eMarker)).toBe(42);

  // In-page links ("View results" and friends) navigate in place too.
  await page.getByRole("link", { name: "History" }).click();
  await expect(page).toHaveURL(/\/cleanup\/history\/$/);
  await expect(page.getByText("No cleanup runs recorded yet.")).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as { __e2eMarker?: number }).__e2eMarker)).toBe(42);

  // Back/forward re-derives the page from the URL without a reload.
  await page.goBack();
  await expect(page).toHaveURL(/\/cleanup\/results\/$/);
  await expect(page.getByRole("link", { name: "Results" })).toHaveAttribute("aria-current", "page");
  await page.goForward();
  await expect(page).toHaveURL(/\/cleanup\/history\/$/);
  expect(await page.evaluate(() => (window as unknown as { __e2eMarker?: number }).__e2eMarker)).toBe(42);
});

test("a direct deep link still lands on the right tab", async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = {};
    if (path === "/api/cleanup/status") data = { state: "ready", reasons: [], requirements: [], capabilities: [] };
    else if (path === "/api/cleanup/catalog") data = { platform: "macos", entries: [] };
    else if (path === "/api/cleanup/jobs") data = { jobs: [] };
    else if (path === "/api/cleanup/permissions") data = { platform: "macos", permissions: [] };
    else if (path === "/api/cleanup/history") data = { entries: [], total: 0, verified: true };
    else if (path === "/api/host") data = { host: { os: "macos", osPretty: "macOS", arch: "arm64", hostname: "test", cpus: 8, memory: 0, disk: null, kvm: { present: false, usable: false }, wsl: { guest: false, distributions: [] }, runtime: null, xcode: null, python: "3.12", root: "/tmp", tools: [], providers: [] }, labs: [] };
    else if (path === "/api/health") data = { status: "ok", version: "test", console: true };
    else if (path === "/api/jobs") data = { jobs: [] };
    else if (path === "/api/logs") data = { logs: [] };
    await route.fulfill({ json: data });
  });
  await page.goto("/cleanup/history/");
  await expect(page).toHaveURL(/\/cleanup\/history\/$/);
  await expect(page.getByRole("link", { name: "History" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByText("No cleanup runs recorded yet.")).toBeVisible();
});
