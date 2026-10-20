import { expect, test, type Page } from "@playwright/test";

import { ask, course, loginAsStudent, openTutor } from "./helpers";

// AI Tutor turu ve pratik döngüsünün arayüzü. Test sistemi LLM'siz çalıştığı için soru üretimi
// ve değerlendirme burada yapılamaz (backend tarafı pytest'te sınanır: test_tutor.py,
// test_practice.py). Bu testte yalnızca bu uçların cevapları `route.fulfill` ile verilir;
// biçimleri backend sözleşmesiyle birebir aynıdır (CONTRACTS.md §2, §9). Uygulamaya sahte veri
// eklenmez.

const SOURCE_ID = "e2e-kaynak-1";

function citation(documentTitle: string) {
  return { source_id: SOURCE_ID, document_title: documentTitle, page: 1, t_start: null, t_end: null };
}

function answerBlock(documentTitle: string) {
  return {
    type: "course_answer",
    provenance: "course",
    response: {
      answer:
        "**İkili arama** her adımda aralığı yarıya indirir [1].\n\n" +
        "1. Ortadaki eleman karşılaştırılır [1].\n2. Toplam süre $O(\\log n)$ olur [1].",
      mode: "llm",
      outcome: "answered",
      unsupported_removed: 0,
      coverage_gap: "Materyalde ispatın ayrıntısı yok.",
      citations: [citation(documentTitle)],
      declined: false,
      decline_reason: null,
      suggested_sources: [],
      conversation_id: 1,
      retrieval: [],
      similarity_threshold: null,
      best_similarity: null,
      model: "gemini-3.8-flash",
    },
  };
}

function practiceItem(id: number, courseId: number, documentTitle: string, prompt: string) {
  return {
    id,
    course_id: courseId,
    type: "mcq",
    topic: "ikili arama",
    difficulty: "medium",
    prompt,
    options: ["Yarıyı atar", "Baştan sona tarar", "Diziyi sıralar", "Rastgele seçer"],
    source: citation(documentTitle),
  };
}

function sse(events: [string, unknown][]): string {
  return events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join("");
}

async function mockTurn(page: Page, events: [string, unknown][]) {
  await page.route("**/api/tutor/turn/stream", (route) =>
    route.fulfill({ status: 200, contentType: "text/event-stream", body: sse(events) }),
  );
}

async function mockSource(page: Page, documentTitle: string) {
  await page.route(`**/api/sources/${SOURCE_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        source_id: SOURCE_ID,
        document_id: 1,
        document_title: documentTitle,
        material_type: "notes",
        text: "Ikili arama her adimda araligin yarisini atar.",
        page: 1,
        t_start: null,
        t_end: null,
        media_url: null,
        page_image_url: null,
        highlights: [],
      }),
    }),
  );
}

test.beforeEach(async ({ page }) => {
  await loginAsStudent(page);
});

test("cevap iddia iddia gösterilir: liste maddeleri ayrı iddia, kalın yazı ve formül biçimlenir; eksik kısım ayrıca söylenir", async ({
  page,
}) => {
  const algorithms = course("A");
  await mockSource(page, algorithms.documentTitle);
  await mockTurn(page, [
    ["status", { tool: "answer_from_course", label: "Ders materyalinde aranıyor…" }],
    ["block", { index: 0, block: answerBlock(algorithms.documentTitle) }],
    ["done", { conversation_id: 1, blocks: [answerBlock(algorithms.documentTitle)], trace: {} }],
  ]);
  await openTutor(page, algorithms);

  await ask(page, "İkili arama neden hızlı?");

  const answer = page.getByRole("article").filter({ hasText: "İkili arama neden hızlı?" });
  const lead = answer.getByRole("heading", { level: 2 });
  await expect(lead.locator("strong", { hasText: "İkili arama" })).toBeVisible();
  // Numaralı liste düz metne düşmez: her madde kendi iddiası olur.
  const claims = answer.getByRole("list", { name: /Cevabın iddiaları/ });
  await expect(claims.getByRole("listitem")).toHaveCount(2);
  await expect(claims.locator(".katex").first()).toBeVisible();
  await expect(answer.getByText(/\*\*|\$/)).toHaveCount(0);
  await expect(answer.getByText("Materyalde ispatın ayrıntısı yok.")).toBeVisible();
  await expect(answer.getByText("3/3 iddia kaynağa bağlı")).toBeVisible();
  await expect(answer.getByRole("button", { name: "Bunu bana soru olarak sor" })).toBeVisible();

  await claims.getByRole("button").nth(1).click();
  await expect(
    page.getByRole("complementary", { name: "Kaynak" }).getByText(algorithms.documentTitle, { exact: true }).first(),
  ).toBeVisible();
});

test("pratik: şık seçilir, geri bildirim gelir, eksik kavram üzerine yeni soru eklenir", async ({ page }) => {
  const algorithms = course("A");
  const first = practiceItem(9001, algorithms.id, algorithms.documentTitle, "İkili arama her adımda ne yapar?");
  const next = practiceItem(9002, algorithms.id, algorithms.documentTitle, "Takip: aralık neden yarıya iner?");
  await mockSource(page, algorithms.documentTitle);
  await mockTurn(page, [
    ["status", { tool: "generate_practice", label: "Pratik sorusu hazırlanıyor ve kontrol ediliyor…" }],
    ["status", { tool: "generate_practice", label: "Soru bağımsız çözümle kontrol ediliyor…" }],
    ["block", { index: 0, block: { type: "practice", provenance: "course", item: first } }],
    ["done", { conversation_id: 1, blocks: [{ type: "practice", provenance: "course", item: first }], trace: {} }],
  ]);
  const answers: unknown[] = [];
  await page.route("**/api/practice/9001/answer", async (route) => {
    answers.push(route.request().postDataJSON());
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        attempt_id: 77,
        item_id: 9001,
        score: 0,
        max_score: 1,
        understood: [],
        missing_concepts: ["ikili arama adımı"],
        explanation: "Doğru cevap: A) Yarıyı atar. Her adımda aralığın **yarısı** atılır.",
        citations: [citation(algorithms.documentTitle)],
        follow_up_item_id: null,
        correct_option: 0,
        reference_answer: null,
        criteria: [],
      }),
    });
  });
  const requests: unknown[] = [];
  await page.route("**/api/practice", async (route) => {
    requests.push(route.request().postDataJSON());
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(next) });
  });
  await openTutor(page, algorithms);

  await ask(page, "Bana bir soru sor");

  const card = page.getByRole("region", { name: "Pratik sorusu" }).first();
  await expect(card.getByText("İkili arama her adımda ne yapar?")).toBeVisible();
  // Anahtar cevaptan önce hiçbir yerde yok; şık seçilmeden gönderilemez.
  await expect(page.getByText("Doğru cevap")).toHaveCount(0);
  const submit = card.getByRole("button", { name: "Cevabı gönder" });
  await expect(submit).toBeDisabled();

  await card.getByRole("radio").nth(1).check();
  await submit.click();

  await expect(card.getByText("Doğru değil")).toBeVisible();
  await expect(card.getByText("0 / 1 puan")).toBeVisible();
  await expect(card.locator("strong", { hasText: "yarısı" })).toBeVisible();
  await expect(card.getByText("ikili arama adımı")).toBeVisible();
  expect(answers).toEqual([{ selected_option: 1 }]);

  await card.getByRole("button", { name: "Eksiklerim üzerine yeni soru" }).click();

  await expect(page.getByRole("region", { name: "Pratik sorusu" })).toHaveCount(2);
  await expect(page.getByText("Takip: aralık neden yarıya iner?")).toBeVisible();
  expect(requests).toEqual([
    { course_id: algorithms.id, type: "mcq", difficulty: "medium", follow_up_of_attempt_id: 77 },
  ]);
});

test("kontrolden geçen soru üretilemezse dürüstçe söylenir", async ({ page }) => {
  const algorithms = course("A");
  const notice = {
    type: "notice",
    provenance: "none",
    kind: "not_covered",
    text: "Kontrollerden geçen bir soru üretilemedi. Konuyu biraz daha belirgin yazıp tekrar dene.",
  };
  await mockTurn(page, [
    ["block", { index: 0, block: notice }],
    ["done", { conversation_id: 1, blocks: [notice], trace: {} }],
  ]);
  await openTutor(page, algorithms);

  await ask(page, "Bana bir soru sor");

  await expect(page.getByRole("paragraph").filter({ hasText: notice.text })).toBeVisible();
  await expect(page.getByRole("region", { name: "Pratik sorusu" })).toHaveCount(0);
});
