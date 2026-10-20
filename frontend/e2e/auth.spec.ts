import { expect, test } from "@playwright/test";

import { STUDENT } from "./accounts";
import { course, loginAsStudent, submitLogin } from "./helpers";

// Gerçek oturum (#12): giriş/çıkış, oturum düşmesi, yetkisiz gezinme, yetki hataları ve ilk giriş onayı.

test("yanlış şifreyle giriş yapılamaz ve sade bir hata gösterilir", async ({ page }) => {
  await page.goto("/login");
  await submitLogin(page, { email: STUDENT.email, password: "yanlis-sifre-123" });

  await expect(page.getByText("E-posta veya şifre hatalı.")).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});

test("girişsiz korumalı sayfa girişe yönlendirir; girişten sonra istenen sayfa açılır", async ({ page }) => {
  const algorithms = course("A");
  await page.goto(`/student/courses/${algorithms.id}/tutor`);
  await expect(page).toHaveURL(/\/login$/);

  await submitLogin(page, STUDENT);

  await expect(page).toHaveURL(new RegExp(`/student/courses/${algorithms.id}/tutor$`));
  await expect(page.getByRole("heading", { name: `${algorithms.name} dersine sor` })).toBeVisible();
});

test("çıkış yapınca oturum kapanır; korumalı sayfalar girişe döner", async ({ page }) => {
  await loginAsStudent(page);
  await page.getByRole("button", { name: "Çıkış yap" }).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.goto("/student");
  await expect(page).toHaveURL(/\/login$/);
});

test("oturum ortada düşerse (süre dolması) sonraki istekte girişe dönülür", async ({ page, context }) => {
  const algorithms = course("A");
  await loginAsStudent(page);
  await expect(page.getByRole("link", { name: algorithms.name })).toBeVisible();

  await context.clearCookies();
  await page.getByRole("link", { name: algorithms.name }).click();

  await expect(page).toHaveURL(/\/login$/);
});

test("öğrenci eğitmen alanına giremez; kendi ana sayfasına yönlendirilir", async ({ page }) => {
  await loginAsStudent(page);
  await page.goto("/instructor");
  await expect(page).toHaveURL(/\/student$/);
});

test("üye olunmayan ders bulunmaz; rolün yetmediği işlem 403 döner", async ({ page }) => {
  await loginAsStudent(page);

  await page.goto("/student/courses/999999");
  await expect(page.getByRole("heading", { name: "Ders bulunamadı" })).toBeVisible();
  const missing = await page.request.get("/api/courses/999999/outline");
  expect(missing.status()).toBe(404);

  // Öğrenci, üye olduğu dersin bilgisini düzenleyemez (yalnızca eğitmen).
  const forbidden = await page.request.patch(`/api/courses/${course("A").id}`, { data: { term: "Bahar" } });
  expect(forbidden.status()).toBe(403);
  expect((await forbidden.json()).code).toBe("insufficient_role");
});

test("yeni öğrenci: aydınlatma metni önce gelir; onaydan sonra katılım koduyla derse katılır", async ({ page }) => {
  const email = `e2e-yeni-${Date.now().toString(36)}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Ad soyad").fill("Yeni Öğrenci");
  await page.getByLabel("Üniversite e-postası").fill(email);
  await page.getByLabel("Şifre", { exact: true }).fill("yeni-ogrenci-sifre");
  await page.getByRole("button", { name: "Öğrenci hesabı oluştur" }).click();

  await expect(page.getByRole("heading", { name: "Aydınlatma metni" })).toBeVisible();
  await page.getByRole("button", { name: "Okudum, kabul ediyorum" }).click();

  await expect(page.getByRole("heading", { name: "Henüz kayıtlı dersin yok" })).toBeVisible();
  await page.getByLabel("Katılım kodu").fill("YANLISKOD");
  await page.getByRole("button", { name: "Derse katıl" }).click();
  await expect(page.getByText("Bu kodla bir ders bulunamadı.", { exact: false })).toBeVisible();
});
