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

test("izlence yüklenemezse tekrar denenir; her sayfada tek h1 var", async ({ page }) => {
  const algorithms = course("A");
  let fail = true;
  await page.route(`**/api/courses/${algorithms.id}/outline`, async (route) => {
    if (fail) {
      fail = false;
      await route.fulfill({ status: 500, body: "" });
      return;
    }
    await route.continue();
  });

  await page.goto(`/student/courses/${algorithms.id}/syllabus`);
  await expect(page.getByText("İzlence yüklenemedi")).toBeVisible();
  await page.getByRole("button", { name: "Tekrar dene" }).click();
  await expect(page.getByText("İzlence yüklenemedi")).toHaveCount(0);

  for (const section of ["", "/syllabus", "/calendar", "/lecture-notes", "/videos", "/learning", "/materials"]) {
    await page.goto(`/student/courses/${algorithms.id}${section}`);
    await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
  }
});
