import { expect, test } from "@playwright/test";

test("dashboard renders primary controls", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Create New Project" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Load from URL" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Create New Project" })).toBeVisible();
});
