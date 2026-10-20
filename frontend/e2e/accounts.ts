import type { APIRequestContext } from "@playwright/test";

/**
 * Test sisteminin hesapları. `docker-compose.e2e.yml` API'yi SEED_DEV_ACCOUNTS ile açar; hesaplar
 * açılışta bu bilgilerle oluşturulur. Yalnızca geçici test sistemi içindir.
 */
export const INSTRUCTOR = {
  email: process.env.E2E_INSTRUCTOR_EMAIL ?? "e2e-egitmen@example.com",
  password: process.env.E2E_INSTRUCTOR_PASSWORD ?? "e2e-egitmen-sifre",
};

export const STUDENT = {
  email: process.env.E2E_STUDENT_EMAIL ?? "e2e-ogrenci@example.com",
  password: process.env.E2E_STUDENT_PASSWORD ?? "e2e-ogrenci-sifre",
};

/** API bağlamında oturum açar; çerez bağlamda saklanır ve sonraki isteklerle gider. */
export async function apiLogin(api: APIRequestContext, account: { email: string; password: string }) {
  const response = await api.post("/api/auth/login", { data: account });
  if (!response.ok()) {
    throw new Error(
      `${account.email} ile giriş yapılamadı (${response.status()}). Test sistemi SEED_DEV_ACCOUNTS ile ` +
        "açıldı mı? docker-compose.e2e.yml",
    );
  }
}
