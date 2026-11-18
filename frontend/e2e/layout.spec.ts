import { expect, test } from "@playwright/test";

import { course, loginAsStudent } from "./helpers";

// Tek uygulama düzeni ve küçük tutarlılık düzeltmeleri (#103, #106).

test.beforeEach(async ({ page }) => {
  await loginAsStudent(page);
});

test("ders sayfasında tablo kesilmez; konum şeridi bölüm adını söyler", async ({ page }) => {
  const algorithms = course("A");
  await page.goto(`/student/courses/${algorithms.id}/lecture-notes`);

  await expect(page.getByRole("navigation", { name: "Konum" })).toContainText("Ders notları");
  const table = page.getByRole("table").first();
  await expect(table).toBeVisible();
  const box = await table.boundingBox();
  const viewport = page.viewportSize();
  expect(box && viewport && box.x + box.width <= viewport.width).toBeTruthy();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
});

test("dar ekran menüsü: ürün adı görünür, Escape kapatır @dar-ekran", async ({ page }) => {
  await page.goto("/student");
  await page.getByRole("button", { name: "Menüyü aç" }).click();

  const menu = page.getByRole("dialog", { name: "Menü" });
  await expect(menu).toBeVisible();
  const name = menu.getByText("Learning", { exact: true });
  await expect(name).toBeVisible();
  // Beyaz zemin üstüne beyaz yazı olmasın (#106).
  const color = await name.evaluate((element) => getComputedStyle(element).color);
  expect(color).not.toBe("rgb(255, 255, 255)");
  await expect(menu.getByRole("link", { name: "Hesabım" })).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(menu).toHaveCount(0);
});
