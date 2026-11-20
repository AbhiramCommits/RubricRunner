import { execSync } from "node:child_process";
import path from "node:path";

import { expect, test } from "@playwright/test";

const repoRoot = path.resolve(__dirname, "../../..");

test("grade the class, edit two criteria, publish, and audit the versions", async ({ page }) => {
  // Fresh demo database: one course, one assignment (#1), 24 submissions, no versions.
  execSync("make seed", { cwd: repoRoot, stdio: "pipe" });

  await page.goto("/assignments/1");
  await expect(page.getByRole("heading", { name: /Argumentative Essay/ })).toBeVisible();

  await page.getByRole("button", { name: "Grade whole class" }).click();
  await page.waitForURL(/run=\d+/, { timeout: 30_000 });
  await expect(page.getByText("Run finished", { exact: false })).toBeVisible({
    timeout: 90_000,
  });
  await expect(page.getByText("24/24 processed")).toBeVisible();

  const reviewRow = page.locator("tr", { hasText: "Needs review" }).first();
  await expect(reviewRow).toBeVisible();
  const studentCell = reviewRow.locator("td").first();
  const studentName = (await studentCell.locator("div").first().innerText()).trim();
  await reviewRow.getByRole("link", { name: "Review" }).click();

  await expect(page.getByText("Needs review — publishing is blocked")).toBeVisible();
  const publishButton = page.getByRole("button", { name: "Publish this version" });
  await expect(publishButton).toBeDisabled();

  const points = page.locator('input[name="points"]');
  await points.nth(0).fill("5");
  await points.nth(1).fill("9");
  await page
    .locator('textarea[name="summaryComment"]')
    .fill("Strong thesis and evidence. Tighten the conclusion before the final draft.");

  await page.getByRole("button", { name: "Save as new version" }).click();
  await page.waitForURL(/version=\d+&saved=1/, { timeout: 30_000 });
  await expect(page.getByText("Saved as a new teacher version")).toBeVisible();
  await expect(page.getByRole("button", { name: "Publish this version" })).toBeEnabled();

  await page.getByRole("button", { name: "Publish this version" }).click();
  await page.waitForURL(/published=\d+/, { timeout: 30_000 });

  const publishedRow = page.locator("tr", { hasText: studentName }).first();
  await expect(publishedRow).toContainText("Published");
  await publishedRow.getByRole("link", { name: "Review" }).click();

  await page.getByRole("link", { name: "Version history →" }).click();
  await page.waitForURL(/history/, { timeout: 30_000 });
  await expect(page.getByTestId("version-timeline").locator(":scope > li")).toHaveCount(2);
  await expect(
    page.getByTestId("version-timeline").getByText("Raw model output", { exact: true }),
  ).toHaveCount(1);
  await expect(page.getByText("Audit trail of published grade")).toBeVisible();
  await expect(page.getByText("raw model output preserved")).toBeVisible();
});
