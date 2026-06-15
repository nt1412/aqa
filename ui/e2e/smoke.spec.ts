import { type ConsoleMessage, type Page, expect, test } from "@playwright/test";

// Collect browser errors so any view that throws on render fails the test.
function trackErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e}`));
  page.on("console", (m: ConsoleMessage) => {
    // favicon 404 is dev noise, not an app error
    if (m.type() === "error" && !m.text().includes("favicon")) errors.push(`console: ${m.text()}`);
  });
  return errors;
}

const VIEWS: [string, string][] = [
  ["/suites", "test suites"],
  ["/builds", "build timeline"],
  ["/branches", "merge-readiness"],
  ["/health", "project health"],
];

test("login, then the operator console views render without errors", async ({ page }) => {
  const errors = trackErrors(page);

  // login (form is prefilled admin/admin; a seeded admin must exist)
  await page.goto("/login");
  await page.getByRole("button", { name: "authenticate" }).click();

  // logged-in shell rendered (nav present) and a project is available/selected
  await expect(page.getByRole("link", { name: /Builds/ })).toBeVisible();
  await expect(page.getByRole("combobox")).toBeVisible();

  for (const [path, heading] of VIEWS) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
  }

  expect(errors, `browser errors:\n${errors.join("\n")}`).toEqual([]);
});
