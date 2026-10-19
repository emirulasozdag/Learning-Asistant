import { defineConfig, devices } from "@playwright/test";

/**
 * Tarayıcı testleri. Ayrı test sistemine karşı çalışır (docker-compose.e2e.yml, port 5273);
 * geliştirme sistemine ve BLM2512'ye dokunmaz. Testler kendi derslerini ve PDF'lerini
 * `e2e/global-setup.ts` içinde gerçek API ile oluşturur.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:5273";

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  // Aynı sunucu ve aynı dersler paylaşıldığı için testler sırayla çalışır.
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "masaustu",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
      grepInvert: /@dar-ekran/,
    },
    {
      name: "dar-ekran",
      use: { ...devices["Desktop Chrome"], viewport: { width: 375, height: 700 } },
      grep: /@dar-ekran/,
    },
  ],
});
