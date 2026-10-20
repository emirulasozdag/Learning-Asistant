import { chromium, request, type FullConfig } from "@playwright/test";

import { PRIVACY_POLICY_VERSION } from "../src/services/authService";
import { INSTRUCTOR, STUDENT, apiLogin } from "./accounts";
import { COURSE_A, COURSE_B, renderPdf } from "./fixtures/pdf";

/**
 * Test verisini gerçek API ile kurar: eğitmen iki ders açar ve her birine kendi PDF'ini yükler;
 * öğrenci aydınlatma metnini onaylar ve katılım koduyla iki derse de katılır.
 * Ders adlarına çalıştırma damgası eklenir; aynı sistemde tekrar çalıştırmada karışmaz.
 * Kimlikler ortam değişkenleriyle testlere ve `global-teardown`'a aktarılır.
 */
export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0].use.baseURL;
  if (!baseURL) throw new Error("playwright.config.ts içinde baseURL tanımlı değil");

  const api = await request.newContext({ baseURL });
  const health = await api.get("/api/health").catch(() => null);
  if (!health?.ok()) {
    await api.dispose();
    throw new Error(
      `Test sistemine ulaşılamadı (${baseURL}). Önce başlat:\n` +
        "docker compose -p learning-e2e -f docker-compose.yml -f docker-compose.e2e.yml up -d --build",
    );
  }

  const student = await request.newContext({ baseURL });
  const browser = await chromium.launch();
  const stamp = Date.now().toString(36).toUpperCase();
  const documentIds: number[] = [];
  try {
    await apiLogin(api, INSTRUCTOR);
    await apiLogin(student, STUDENT);
    // Aydınlatma metni (ADR-4): onaylanmadan soru sorulamaz; testler onay ekranını atlar.
    const consent = await student.put("/api/me/consent", {
      data: { research_logging: false, policy_version: PRIVACY_POLICY_VERSION },
    });
    if (!consent.ok()) throw new Error(`Aydınlatma metni onaylanamadı: ${consent.status()} ${await consent.text()}`);

    for (const course of [COURSE_A, COURSE_B]) {
      const name = `${course.name} ${stamp}`;
      const created = await api.post("/api/courses", {
        data: { code: `E2E${course.key}${stamp}`, name, language: "tr" },
      });
      if (!created.ok()) throw new Error(`Ders oluşturulamadı: ${created.status()} ${await created.text()}`);
      const { id } = (await created.json()) as { id: number };

      const uploaded = await api.post(`/api/courses/${id}/materials`, {
        multipart: {
          material_type: "notes",
          declaration: "true",
          title: course.documentTitle,
          file: { name: "e2e-notlar.pdf", mimeType: "application/pdf", buffer: await renderPdf(browser, course) },
        },
        timeout: 120_000,
      });
      if (!uploaded.ok()) throw new Error(`PDF yüklenemedi: ${uploaded.status()} ${await uploaded.text()}`);
      documentIds.push(((await uploaded.json()) as { id: number }).id);

      const joinCode = await api.get(`/api/courses/${id}/join-code`);
      if (!joinCode.ok()) throw new Error(`Katılım kodu alınamadı: ${joinCode.status()}`);
      const { code } = (await joinCode.json()) as { code: string };
      const joined = await student.post("/api/courses/join", { data: { code } });
      if (!joined.ok()) throw new Error(`Öğrenci derse katılamadı: ${joined.status()} ${await joined.text()}`);

      process.env[`E2E_COURSE_${course.key}_ID`] = String(id);
      process.env[`E2E_COURSE_${course.key}_NAME`] = name;
    }
  } finally {
    await browser.close();
    await api.dispose();
    await student.dispose();
  }
  process.env.E2E_DOCUMENT_IDS = documentIds.join(",");
}
