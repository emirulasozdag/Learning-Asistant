import { expect, test } from "@playwright/test";

import { ask, course, firstClaim, loginAsStudent, openTutor, questionBox, waitForAnswer } from "./helpers";

// Hata durumları. Uygulamaya sahte veri eklenmez: `route.abort` yalnızca bağlantının
// kopmasını taklit eder; engel kaldırılınca aynı istek gerçek API'ye gider.

test.beforeEach(async ({ page }) => {
  await loginAsStudent(page);
});

test("servise ulaşılamazsa öğrenciye söylenir; Tekrar sor yeniden dener", async ({ page }) => {
  await openTutor(page, course("A"));
  await page.route("**/api/tutor/turn/stream", (route) => route.abort("failed"));

  await ask(page, "İkili arama nasıl çalışır?");
  await expect(page.getByText("Ders servisine ulaşılamıyor")).toBeVisible();
  await expect(page.getByText(/Failed to fetch|İstek başarısız/)).toHaveCount(0);
  await expect(page.getByText("yeterli bilgi bulunamadı")).toHaveCount(0);

  await page.unroute("**/api/tutor/turn/stream");
  await page.getByRole("button", { name: "Tekrar sor" }).click();
  await waitForAnswer(page);
  await expect(firstClaim(page)).toBeVisible();
  await expect(page.getByText("Ders servisine ulaşılamıyor")).toHaveCount(0);
});

test("akıştaki hata olayı geçici sorun olarak gösterilir, 'konu derste yok' olarak değil", async ({ page }) => {
  await openTutor(page, course("A"));
  await page.route("**/api/tutor/turn/stream", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      // backend/app/api/tutor.py `_sse("error", {"detail": ...})` çıktısıyla birebir aynı biçim:
      // "event: <ad>\ndata: <json.dumps(..., ensure_ascii=False)>\n\n".
      body: 'event: error\ndata: {"detail": "Cevap üretilirken beklenmeyen bir hata oluştu."}\n\n',
    }),
  );

  await ask(page, "İkili arama nasıl çalışır?");
  await expect(page.getByText("Geçici bir sorun oluştu")).toBeVisible();
  await expect(page.getByRole("button", { name: "Tekrar sor" })).toBeVisible();
  await expect(page.getByText("yeterli bilgi bulunamadı")).toHaveCount(0);
  await expect(page.getByText("beklenmeyen bir hata")).toHaveCount(0);
});

test("materyaller yüklenemezse 'materyal yok' denmez; Tekrar dene yükler", async ({ page }) => {
  const algorithms = course("A");
  const materials = `**/api/courses/${algorithms.id}/materials`;
  await page.route(materials, (route) => route.abort("failed"));

  await page.goto(`/student/courses/${algorithms.id}/tutor`);
  await expect(page.getByRole("heading", { name: "Materyaller yüklenemedi" })).toBeVisible();
  await expect(page.getByText("Bu derse henüz materyal yüklenmedi")).toHaveCount(0);
  await expect(questionBox(page)).not.toHaveAttribute("placeholder", "Bu derse henüz materyal yüklenmedi");

  await page.unroute(materials);
  await page.getByRole("button", { name: "Tekrar dene" }).click();
  await expect(page.getByRole("heading", { name: `${algorithms.name} dersine sor` })).toBeVisible();
  await expect(page.getByText(algorithms.documentTitle)).toBeVisible();
});

test("ders listesi yüklenemezse 'Ders bulunamadı' denmez; Tekrar dene yükler", async ({ page }) => {
  const algorithms = course("A");
  await page.route("**/api/courses", (route) => route.abort("failed"));

  await page.goto(`/student/courses/${algorithms.id}/tutor`);
  await expect(page.getByRole("heading", { name: "Dersler yüklenemedi" })).toBeVisible();
  await expect(page.getByText("Ders bulunamadı")).toHaveCount(0);

  await page.unroute("**/api/courses");
  await page.getByRole("button", { name: "Tekrar dene" }).click();
  await expect(page.getByRole("heading", { name: `${algorithms.name} dersine sor` })).toBeVisible();
});

test("kaynak açılamazsa sade mesaj ve Tekrar dene; kaynak değişince eski hata kalmaz", async ({ page }) => {
  const algorithms = course("A");
  await openTutor(page, algorithms);
  const sources = "**/api/sources/**";
  await page.route(sources, (route) => route.abort("failed"));

  await ask(page, "İkili arama nasıl çalışır?");
  await waitForAnswer(page);
  const panel = page.getByRole("complementary", { name: "Kaynak" });
  await expect(panel.getByRole("heading", { name: "Kaynak açılamadı" })).toBeVisible();
  await expect(panel.getByText(/Failed to fetch|İstek başarısız/)).toHaveCount(0);

  await page.unroute(sources);
  await panel.getByRole("button", { name: "Tekrar dene" }).click();
  await expect(panel.getByText(algorithms.documentTitle, { exact: true }).first()).toBeVisible();
  await expect(panel.getByRole("heading", { name: "Kaynak açılamadı" })).toHaveCount(0);

  // Başka bir bölüm hata verir; sonra ilk kaynağa dönülünce eski hata görünmez. "Nasıl bulundu"
  // geniş ekranda açık gelir.
  const hits = page.locator("details ol button");
  expect(await hits.count()).toBeGreaterThan(1);
  await page.route(sources, (route) => route.abort("failed"));
  await hits.nth(1).click();
  await expect(panel.getByRole("heading", { name: "Kaynak açılamadı" })).toBeVisible();

  await page.unroute(sources);
  await firstClaim(page).click();
  await expect(panel.getByText(algorithms.documentTitle, { exact: true }).first()).toBeVisible();
  await expect(panel.getByRole("heading", { name: "Kaynak açılamadı" })).toHaveCount(0);
});
