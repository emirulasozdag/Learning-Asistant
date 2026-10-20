import { expect, type Page } from "@playwright/test";

import { STUDENT } from "./accounts";
import { COURSE_A, COURSE_B } from "./fixtures/pdf";

export interface SetupCourse {
  id: number;
  name: string;
  documentTitle: string;
}

/** `global-setup` içinde oluşturulan ders. */
export function course(key: "A" | "B"): SetupCourse {
  const id = Number(process.env[`E2E_COURSE_${key}_ID`]);
  const name = process.env[`E2E_COURSE_${key}_NAME`];
  if (!id || !name) throw new Error("Test dersleri yok: global-setup çalışmadı");
  return { id, name, documentTitle: (key === "A" ? COURSE_A : COURSE_B).documentTitle };
}

/** Giriş formunu doldurup gönderir (sayfa zaten /login'de olmalı). */
export async function submitLogin(page: Page, account: { email: string; password: string }) {
  await page.getByLabel("E-posta").fill(account.email);
  await page.getByLabel("Şifre", { exact: true }).fill(account.password);
  await page.getByRole("button", { name: "Giriş yap" }).click();
}

/** Test öğrencisiyle giriş formundan girer (aydınlatma metni global-setup'ta onaylandı). */
export async function loginAsStudent(page: Page) {
  await page.goto("/login");
  await submitLogin(page, STUDENT);
  await page.waitForURL(/\/student/);
}

export async function openTutor(page: Page, target: SetupCourse) {
  await page.goto(`/student/courses/${target.id}/tutor`);
  await expect(page.getByRole("heading", { name: `${target.name} dersine sor` })).toBeVisible();
}

export function questionBox(page: Page) {
  return page.getByRole("textbox", { name: "Sorun" });
}

export async function ask(page: Page, text: string) {
  await questionBox(page).fill(text);
  await questionBox(page).press("Enter");
}

/** Son cevaptaki ilk kaynak numarası (cevap metnindeki sarı [1]). */
export function firstCitation(page: Page) {
  return page.getByRole("button", { name: /^Kaynak 1:/ }).last();
}

/** Cevap tamamlanana kadar bekler: "Durdur" kaybolur. */
export async function waitForAnswer(page: Page) {
  await expect(page.getByRole("button", { name: "Durdur" })).toHaveCount(0, { timeout: 30_000 });
}

/** Ekran okuyucu duyuru bölgesi. */
export function liveRegion(page: Page) {
  return page.locator('[aria-live="polite"]');
}
