import { chromium, request, type FullConfig } from "@playwright/test";

import { COURSE_A, COURSE_B, renderPdf } from "./fixtures/pdf";

/**
 * Test verisini gerçek API ile kurar: iki ders, her birine kendi PDF'i.
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

  const browser = await chromium.launch();
  const stamp = Date.now().toString(36).toUpperCase();
  const documentIds: number[] = [];
  try {
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
          title: course.documentTitle,
          file: { name: "e2e-notlar.pdf", mimeType: "application/pdf", buffer: await renderPdf(browser, course) },
        },
        timeout: 120_000,
      });
      if (!uploaded.ok()) throw new Error(`PDF yüklenemedi: ${uploaded.status()} ${await uploaded.text()}`);
      documentIds.push(((await uploaded.json()) as { id: number }).id);

      process.env[`E2E_COURSE_${course.key}_ID`] = String(id);
      process.env[`E2E_COURSE_${course.key}_NAME`] = name;
    }
  } finally {
    await browser.close();
    await api.dispose();
  }
  process.env.E2E_DOCUMENT_IDS = documentIds.join(",");
}
