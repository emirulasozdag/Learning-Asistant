import { expect, test } from "@playwright/test";
import { INSTRUCTOR } from "./accounts";
import { PRIVACY_POLICY_VERSION } from "../src/services/authService";

import {
  ask,
  course,
  firstCitation,
  liveRegion,
  loginAsStudent,
  openTutor,
  questionBox,
  submitLogin,
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
  // Aynı metin otomatik açılan kaynak panelinde de bulunur; cevap DOM'da önce gelir.
  await expect(page.getByText("sağ yarı atılır").first()).toBeVisible();
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
  await expect(page.getByText("son giren ilk çıkar").first()).toBeVisible();
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

test("kod ve sayılar yüklemeden kaynak görünümüne kadar korunur", async ({ page, browser }, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const teacherContext = await browser.newContext({ baseURL: testInfo.project.use.baseURL });
  const teacher = await teacherContext.newPage();
  teacher.on("pageerror", (error) => errors.push(error.message));
  let documentId: number | undefined;
  try {
    await teacher.goto("/login");
    await submitLogin(teacher, INSTRUCTOR);
    await teacher.waitForURL(/\/instructor/);
    const consent = await teacher.request.put("/api/me/consent", {
      data: { research_logging: false, policy_version: PRIVACY_POLICY_VERSION },
    });
    expect(consent.ok()).toBeTruthy();
    const created = await teacher.request.post("/api/courses", {
      data: { code: `CODE${Date.now()}`, name: "Kod ve sayılar", language: "tr" },
    });
    expect(created.ok()).toBeTruthy();
    const target = await created.json() as { id: number; name: string };
    const pdfPage = await browser.newPage();
    const code = "def answer():\n    if True:\n        return 42";
    let pdf: Buffer;
    try {
      await pdfPage.setContent(
        `<html><body><pre style="font: 14px monospace">${code}\n\n42\nx = n - 1\n\nvalue    count\n42       7</pre></body></html>`,
      );
      pdf = await pdfPage.pdf({ format: "A4", margin: { top: "2cm", left: "2cm" } });
    } finally {
      await pdfPage.close();
    }
    await teacher.goto(`/instructor/courses/${target.id}/materials`);
    await teacher.getByRole("checkbox").check();
    const responsePromise = teacher.waitForResponse((response) =>
      response.url().endsWith(`/courses/${target.id}/materials`) && response.request().method() === "POST",
    );
    await teacher.locator('input[type="file"]').setInputFiles({ name: "Kod notları.pdf", mimeType: "application/pdf", buffer: pdf });
    const uploaded = await responsePromise;
    expect(uploaded.status()).toBe(201);
    const document = await uploaded.json() as { id: number; report: { warnings: string[] } };
    documentId = document.id;
    const chunksResponse = await teacher.request.get(`/api/documents/${document.id}/chunks`);
    const chunks = await chunksResponse.json() as { text: string }[];
    expect(chunks[0].text).toContain(code);
    expect(chunks[0].text).toContain("\n42\n");
    expect(chunks[0].text).toContain("value    count");
    expect(document.report.warnings.length).toBeGreaterThan(0);
    await teacher.getByRole("button", { name: "Kod notları", exact: true }).click();
    const preview = teacher.getByRole("dialog").locator("p.whitespace-pre-wrap").first();
    await expect.poll(() => preview.textContent()).toBe(chunks[0].text);
    await expect(teacher.getByRole("region", { name: "Yükleme raporu" })).toBeVisible();
    await teacher.screenshot({ path: testInfo.outputPath("code-upload.png"), animations: "disabled" });

    const joinCode = await (await teacher.request.get(`/api/courses/${target.id}/join-code`)).json() as { code: string };
    expect((await page.request.post("/api/courses/join", { data: joinCode })).ok()).toBeTruthy();
    await openTutor(page, { id: target.id, name: target.name, documentTitle: "Kod notları" });
    await ask(page, "def answer return 42");
    await waitForAnswer(page);
    const quoted = page.locator("div.border-l-2").first();
    await expect.poll(() => quoted.textContent()).toContain(code);
    const panel = page.getByRole("complementary", { name: "Kaynak" });
    await expect(panel.getByRole("img")).toBeVisible();
    await expect(panel.getByRole("img")).toHaveCSS("opacity", "1");
    await panel.getByText("Alıntılanan bölümü metin olarak göster").click();
    const excerpt = panel.locator("details p.whitespace-pre-wrap");
    await expect.poll(() => excerpt.textContent()).toBe(chunks[0].text);
    await excerpt.scrollIntoViewIfNeeded();
    await quoted.scrollIntoViewIfNeeded();
    await expect(page).toHaveURL(new RegExp(`/student/courses/${target.id}/tutor$`));
    await expect(page.locator("vite-error-overlay")).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath("code-source.png"), animations: "disabled" });
    expect(errors).toEqual([]);
  } finally {
    if (documentId !== undefined) {
      expect((await teacher.request.delete(`/api/documents/${documentId}`)).ok()).toBeTruthy();
    }
    await teacherContext.close();
  }
});
