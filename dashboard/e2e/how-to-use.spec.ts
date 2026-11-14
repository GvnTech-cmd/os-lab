import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";

test("embedded command inventory matches the shipped CLI and configuration sources", () => {
  const result = execFileSync(process.platform === "win32" ? "python" : "python3",
    ["../scripts/build-how-to-use-reference.py", "--check"], { encoding: "utf8" });
  expect(result).toContain("matches all allowlisted sources");
});

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    const json = path === "/api/host" ? { host: { os: "linux", arch: "x86_64" }, labs: [] }
      : path === "/api/health" ? { status: "ok" }
      : path === "/api/jobs" ? { jobs: [] } : { logs: [] };
    return route.fulfill({ json });
  });
});

test("Workspace prompt includes task, shipped support and workflow limits without sending it", async ({ page }) => {
  const sent: string[] = [];
  page.on("request", request => { if (request.postData()) sent.push(request.postData()!); });
  await page.addInitScript(() => Object.defineProperty(navigator, "clipboard", {
    configurable: true, value: { writeText: async (value: string) => { (window as any).copiedPrompt = value; } }
  }));
  await page.goto("/how-to-use/");
  await expect(page.getByRole("button", { name: "How to use", exact: true })).toHaveAttribute("aria-current", "page");
  const submit = page.getByRole("button", { name: "Generate and copy prompt" });
  await expect(submit).toBeDisabled();
  await page.getByLabel("What do you want to do?").fill("   ");
  await expect(submit).toBeDisabled();
  const task = "Analyze my owned browser extension <script>alert('task')</script>";
  await page.getByLabel("What do you want to do?").fill(task);
  await submit.click();
  await expect(page.getByRole("status")).toContainText("Prompt copied.");
  const prompt = await page.getByLabel("Generated prompt", { exact: true }).inputValue();
  expect(await page.evaluate(() => (window as any).copiedPrompt)).toBe(prompt);
  for (const text of [task, "local dashboard", "Windows Lab", "Linux Lab", "iOS Lab", "macOS Lab", "Android Lab", "Source Lab", "Firewall Lab", "full", "partial", "none", "PRIVACY.md", "RUNBOOK.md", "preview", "not runtime observations", "roll back"]) expect(prompt).toContain(text);
  // Guard the detailed operational context that was previously absent from
  // the high-level catalog, including less prominent native/helper workflows.
  for (const text of ["## 1. Host requirements", "## 11. Troubleshooting", "# Generated technical command inventory",
    "--report-only", "make -C win-lab wait-install", "make -C linux-lab wait-ready",
    "dump-sandbox --pkg PACKAGE", "vbox-deploy-android", "IQ_SESSION_HMAC_KEY_FILE",
    "--expected-plan", "--map-min-role-confidence", "mac-appium-stop", "render-rules.py",
    "SSH_WAIT_TIMEOUT", "OSLAB_CONTENT_OFFLINE", "ssh-config-doctor.sh",
    "frida==", "## npm scripts: `app/package.json`", "## Reference sources"]) expect(prompt).toContain(text);
  expect(prompt).not.toContain("WINDOWS_PASSWORD=admin");
  expect(prompt).not.toContain("MOBSF_API_KEY=compact-lab-key");
  expect(sent.some(body => body.includes(task))).toBe(false);
  expect(await page.evaluate(() => location.search + location.hash + JSON.stringify(localStorage))).not.toContain(task);
  await page.getByLabel("What do you want to do?").fill("A different task");
  await expect(page.getByLabel("Generated prompt", { exact: true })).toHaveCount(0);
});

test("clipboard rejection preserves selectable prompt and supports retry", async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(navigator, "clipboard", {
    configurable: true, value: { writeText: async () => { throw new Error("Denied"); } }
  }));
  await page.goto("/how-to-use/");
  await page.getByLabel("What do you want to do?").fill("Help with my firewall design");
  await page.getByRole("button", { name: "Generate and copy prompt" }).click();
  await expect(page.getByRole("status")).toContainText("Clipboard unavailable.");
  await page.getByRole("button", { name: "Select prompt", exact: true }).click();
  expect(await page.getByLabel("Generated prompt", { exact: true }).evaluate((node: HTMLTextAreaElement) => node.selectionEnd - node.selectionStart)).toBeGreaterThan(5000);
  await page.evaluate(() => Object.defineProperty(navigator, "clipboard", { value: { writeText: async () => {} } }));
  await page.getByRole("button", { name: "Copy prompt again" }).click();
  await expect(page.getByRole("status")).toContainText("Prompt copied.");
});

test("mobile Workspace drawer reaches the prompt page", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/feedback/");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("dialog", { name: "Navigation" }).getByRole("button", { name: "How to use", exact: true }).click();
  await expect(page).toHaveURL(/\/how-to-use\/$/);
  await expect(page.getByLabel("What do you want to do?")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBe(true);
});
