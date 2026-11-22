import { expect, test, type Page } from "@playwright/test";

import { INSTRUCTOR, apiLogin } from "./accounts";
import { ask, course, firstClaim, loginAsStudent, openTutor, waitForAnswer } from "./helpers";

// Paylaşılan bilgisayar (#134): sekmede saklanan Tutor sohbeti ve pratik oturumu kullanıcıya
// bağlıdır; çıkışta ve veriler silinince temizlenir.

const QUESTION = "İkili arama nasıl çalışır?";

function studyCacheKeys(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    Object.keys(sessionStorage).filter((key) => key.startsWith("la.tutor.") || key.startsWith("la.practice.")),
  );
}

test("çıkış yapan öğrencinin sohbeti aynı sekmede sonraki öğrenciye kalmaz; veriler silinince sohbet geri gelmez", async ({
  page,
  playwright,
  baseURL,
}) => {
  const algorithms = course("A");

  // A öğrencisi soru sorar; sohbet sekmede saklanır (kendi kullanıcı anahtarıyla).
  await loginAsStudent(page);
  await openTutor(page, algorithms);
  await ask(page, QUESTION);
  await waitForAnswer(page);
  const keysBefore = await studyCacheKeys(page);
  expect(keysBefore.length).toBeGreaterThan(0);
  expect(keysBefore.every((key) => /^la\.(tutor|practice)\.u\d+\./.test(key))).toBeTruthy();

  // Çıkışta sekmedeki çalışma önbelleği temizlenir.
  await page.getByRole("button", { name: "Çıkış yap" }).click();
  await page.waitForURL(/\/login/);
  expect(await studyCacheKeys(page)).toEqual([]);

  // B öğrencisi aynı sekmede kaydolur ve aynı derse katılır.
  const instructor = await playwright.request.newContext({ baseURL });
  await apiLogin(instructor, INSTRUCTOR);
  const joinCode = await instructor.get(`/api/courses/${algorithms.id}/join-code`);
  expect(joinCode.ok()).toBeTruthy();
  const { code } = (await joinCode.json()) as { code: string };
  await instructor.dispose();

  await page.goto("/register");
  await page.getByLabel("Ad soyad").fill("İkinci Öğrenci");
  await page.getByLabel("Üniversite e-postası").fill(`e2e-ikinci-${Date.now().toString(36)}@example.com`);
  await page.getByLabel("Şifre", { exact: true }).fill("ikinci-ogrenci-sifre");
  await page.getByRole("button", { name: "Öğrenci hesabı oluştur" }).click();
  await page.getByRole("button", { name: "Okudum, kabul ediyorum" }).click();
  await expect(page.getByRole("heading", { name: "Henüz kayıtlı dersin yok" })).toBeVisible();
  const joined = await page.request.post("/api/courses/join", { data: { code } });
  expect(joined.ok()).toBeTruthy();

  // B'nin Tutor'u boş açılır ve ilk sorusu (eski sohbet kimliği gitmeden) cevaplanır.
  await openTutor(page, algorithms);
  await expect(page.getByText("Henüz soru sorulmadı.")).toBeVisible();
  await ask(page, QUESTION);
  await waitForAnswer(page);
  await expect(firstClaim(page)).toBeVisible();

  // B verilerini siler: Tutor'a dönünce sohbet önbellekten geri gelmez.
  await page.goto("/student/account");
  await page.getByRole("button", { name: "Verilerimi sil" }).click();
  await page.getByRole("button", { name: "Verilerimi kalıcı olarak sil" }).click();
  await expect(page.getByText("Verilerin silindi")).toBeVisible();
  expect(await studyCacheKeys(page)).toEqual([]);
  await openTutor(page, algorithms);
  await expect(page.getByText("Henüz soru sorulmadı.")).toBeVisible();
});
