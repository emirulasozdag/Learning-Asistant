import { request, type FullConfig } from "@playwright/test";

import { INSTRUCTOR, apiLogin } from "./accounts";

/**
 * Testlerin yüklediği dokümanları siler. Dersler API ile silinemez (`DELETE /courses` yok);
 * test sistemi `docker compose ... down -v` ile tamamen kaldırılır.
 */
export default async function globalTeardown(config: FullConfig) {
  const ids = (process.env.E2E_DOCUMENT_IDS ?? "").split(",").filter(Boolean);
  if (ids.length === 0) return;
  const api = await request.newContext({ baseURL: config.projects[0].use.baseURL });
  try {
    await apiLogin(api, INSTRUCTOR);
    for (const id of ids) await api.delete(`/api/documents/${id}`);
  } finally {
    await api.dispose();
  }
}
