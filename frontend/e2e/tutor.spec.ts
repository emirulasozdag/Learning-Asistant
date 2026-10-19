import { expect, test } from "@playwright/test";

import {
  ask,
  course,
  firstCitation,
  liveRegion,
  loginAsStudent,
  openTutor,
  questionBox,
  waitForAnswer,
} from "./helpers";

// Test sistemi LLM'siz çalışır: cevap, materyaldeki en ilgili bölümün alıntısıdır (deterministik).
// Görünür metinler `exact: true` ile aranır: ekran okuyucu duyuru bölgesi aynı cümleyi sonunda
// noktayla tekrarlar. "Görünmemeli" kontrolleri ise iki yeri de kapsar.

test.beforeEach(async ({ page }) => {
  await loginAsStudent(page);
});

test("soru sorulur; kaynaklı cevap, incelenen bölümler ve duyuru gelir", async ({ page }) => {
  const algorithms = course("A");
  await openTutor(page, algorithms);
  await ask(page, "İkili arama nasıl çalışır?");
  await waitForAnswer(page);

  await expect(
    page.getByText("Yapay zekâ şu an kullanılamıyor; ders materyalindeki ilgili bölüm olduğu gibi gösteriliyor.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByText("sağ yarı atılır")).toBeVisible();
  await expect(firstCitation(page)).toBeVisible();
  await expect(liveRegion(page)).toHaveText(/ilgili bölüm gösterildi/);

  // Geniş ekranda ilk kaynak yanda kendiliğinden açılır.
  const panel = page.getByRole("complementary", { name: "Kaynak" });
  await expect(panel.getByText(algorithms.documentTitle)).toBeVisible();

  await page.getByText("İncelenen bölümler").click();
  await expect(page.getByText(/bölüm incelendi, 1 tanesi cevapta kullanıldı/)).toBeVisible();
  // Teknik tanılama bilgisi öğrenciye gösterilmez.
  await expect(page.getByText(/e5|eşik|benzerlik/i)).toHaveCount(0);
});

test("kaynak açılır ve kapanınca odak açan düğmeye döner", async ({ page }) => {
  const algorithms = course("A");
  await openTutor(page, algorithms);
  await ask(page, "İkili arama nasıl çalışır?");
  await waitForAnswer(page);

  const panel = page.getByRole("complementary", { name: "Kaynak" });
  await panel.getByRole("button", { name: "Kaynağı kapat" }).click();
  await expect(panel).toHaveCount(0);

  const card = page.getByRole("button", { name: new RegExp(algorithms.documentTitle) }).first();
  await card.click();
  await expect(panel.getByRole("img", { name: new RegExp(algorithms.documentTitle) })).toBeVisible();
  await expect(panel.getByText(/Cevapla karşılaştır/)).toBeVisible();

  await panel.getByRole("button", { name: "Kaynağı kapat" }).click();
  await expect(panel).toHaveCount(0);
  await expect(card).toBeFocused();
});

test("@dar-ekran kaynak diyalog olarak açılır; odak içeride kalır, Escape kapatır", async ({ page }) => {
  await openTutor(page, course("A"));
  await ask(page, "İkili arama nasıl çalışır?");
  await waitForAnswer(page);

  // Dar ekranda kaynak kendiliğinden açılıp cevabın üstünü örtmez.
  const dialog = page.getByRole("dialog", { name: "Kaynak" });
  await expect(dialog).toHaveCount(0);

  const citation = firstCitation(page);
  await citation.click();
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute("aria-modal", "true");
  await expect(dialog).toBeFocused();

  for (let i = 0; i < 6; i++) {
    await page.keyboard.press("Tab");
    expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  }
  for (let i = 0; i < 3; i++) {
    await page.keyboard.press("Shift+Tab");
    expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  }

  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(citation).toBeFocused();
});

test("Durdur süren cevabı iptal eder; Tekrar sor yeniden sorar", async ({ page }) => {
  await openTutor(page, course("A"));

  // Gerçek API cevabı değişmeden geçer; yalnızca ilk istek geciktirilir ki durdurulabilsin.
  let slow = true;
  await page.route("**/api/ask/stream", async (route) => {
    if (slow) await new Promise((resolve) => setTimeout(resolve, 4_000));
    await route.continue().catch(() => {});
  });

  await ask(page, "İkili arama nasıl çalışır?");
  const stop = page.getByRole("button", { name: "Durdur" });
  await expect(stop).toBeVisible();
  await expect(page.getByText("Ders materyalinde aranıyor", { exact: true })).toBeVisible();

  await stop.click();
  await expect(page.getByText("Durduruldu", { exact: true })).toBeVisible();
  await expect(page.getByText("Ders materyalinde aranıyor")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Gönder" })).toBeVisible();
  await expect(liveRegion(page)).toHaveText("Durduruldu.");

  slow = false;
  await page.getByRole("button", { name: "Tekrar sor" }).click();
  await waitForAnswer(page);
  await expect(firstCitation(page)).toBeVisible();
  await expect(page.getByText("Durduruldu")).toHaveCount(0);
});

test("ders değiştirince sohbet ve kaynak sıfırlanır; yeni derste ilk soru hatasız gider", async ({ page }) => {
  const algorithms = course("A");
  const dataStructures = course("B");
  await openTutor(page, algorithms);
  await ask(page, "İkili arama nasıl çalışır?");
  await waitForAnswer(page);
  await expect(page.getByRole("complementary", { name: "Kaynak" })).toBeVisible();

  await page.getByRole("link", { name: dataStructures.name }).click();
  await expect(page).toHaveURL(new RegExp(`/student/courses/${dataStructures.id}/tutor$`));
  await expect(page.getByRole("heading", { name: `${dataStructures.name} dersine sor` })).toBeVisible();
  await expect(page.getByText("İkili arama nasıl çalışır?")).toHaveCount(0);
  await expect(page.getByRole("complementary", { name: "Kaynak" })).toHaveCount(0);

  // Eski dersin sohbet kimliği gitseydi backend "Sohbet bulunamadı" derdi.
  await ask(page, "Yığın nasıl çalışır?");
  await waitForAnswer(page);
  await expect(page.getByText("son giren ilk çıkar")).toBeVisible();
  await expect(page.getByText(/Soru gönderilemedi|Sohbet bulunamadı/)).toHaveCount(0);

  // Soru sürerken ders değiştirilirse istek iptal edilir; ekran takılı kalmaz.
  await page.route("**/api/ask/stream", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 4_000));
    await route.continue().catch(() => {});
  });
  await ask(page, "Kuyruk nasıl çalışır?");
  await expect(page.getByRole("button", { name: "Durdur" })).toBeVisible();
  await page.getByRole("link", { name: algorithms.name }).click();
  await expect(page.getByRole("heading", { name: `${algorithms.name} dersine sor` })).toBeVisible();
  await expect(page.getByText("Ders materyalinde aranıyor")).toHaveCount(0);
  await expect(questionBox(page)).toBeEnabled();
  await expect(page.getByRole("button", { name: "Durdur" })).toHaveCount(0);
});

test("ders kapsamı dışındaki soru kapsam dışı olarak gösterilir", async ({ page }) => {
  await openTutor(page, course("A"));
  await ask(page, "Fransa'nın başkenti neresi?");
  await waitForAnswer(page);

  await expect(page.getByText("Bu soru için ders materyalinde yeterli bilgi bulunamadı", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Tekrar sor" })).toHaveCount(0);
  await expect(page.getByText(/Cevap hazırlanamadı|Ders servisine ulaşılamıyor/)).toHaveCount(0);
});
