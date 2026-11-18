import { expect, request, test, type APIRequestContext, type Page } from "@playwright/test";

import { PRIVACY_POLICY_VERSION } from "../src/services/authService";
import { INSTRUCTOR, apiLogin } from "./accounts";
import { ask, course, loginAsStudent, submitLogin } from "./helpers";

// Öğrenme döngüsünün ekranları (#22): öğrenme kaydı, hesabım (veri silme), eğitmen incelemesi
// ve ders videosu. Test sistemi LLM'siz çalıştığı için pratik denemesi ve tutor cevabı
// üretilemez; yalnızca bu uçların cevapları `route.fulfill` ile verilir (biçimleri backend
// sözleşmesiyle aynıdır, CONTRACTS.md §2.1, §9). Boş durumlar, ayarlar, veri silme ve video
// yüklemesi gerçek API'ye gider.

const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:5273";

function json(body: unknown) {
  return { status: 200, contentType: "application/json", body: JSON.stringify(body) };
}

async function loginAsInstructor(page: Page) {
  await page.goto("/login");
  await submitLogin(page, INSTRUCTOR);
  await page.waitForURL(/\/instructor/);
}

function learningRecord(courseId: number, documentTitle: string) {
  return {
    course_id: courseId,
    logging_enabled: true,
    attempts: [
      {
        item_id: 11,
        attempt_id: 21,
        type: "short_answer",
        concept: "ikili arama karmaşıklığı",
        score: 1,
        max_score: 4,
        missing_concepts: ["log n"],
        attempted_at: new Date().toISOString(),
        withdrawn: false,
      },
      {
        item_id: 10,
        attempt_id: 20,
        type: "mcq",
        concept: "ikili arama adımı",
        score: 1,
        max_score: 1,
        missing_concepts: [],
        attempted_at: new Date(Date.now() - 3600_000).toISOString(),
        withdrawn: true,
      },
    ],
    concepts: [
      {
        concept: "ikili arama karmaşıklığı",
        attempts: 1,
        last_score_ratio: 0.25,
        best_score_ratio: 0.25,
        open_gaps: ["log n"],
        source: { source_id: "e2e-kaynak-1", document_title: documentTitle, page: 1, t_start: null, t_end: null },
      },
      {
        concept: "ikili arama adımı",
        attempts: 1,
        last_score_ratio: 1,
        best_score_ratio: 1,
        open_gaps: [],
        source: null,
      },
    ],
  };
}

test.describe("öğrenci", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsStudent(page);
  });

  test("öğrenme kaydı: kayıt kapalıyken açıklama ve boş durum gerçek API'den gelir", async ({ page }) => {
    const algorithms = course("A");
    await page.goto(`/student/courses/${algorithms.id}/learning`);

    await expect(page.getByRole("heading", { name: "Öğrenme kaydım" })).toBeVisible();
    await expect(page.getByRole("note")).toContainText("Öğrenme kaydın şu an kapalı");
    await expect(page.getByText("Henüz kayıtlı deneme yok")).toBeVisible();
    await page.getByRole("link", { name: "Ayarı değiştir" }).click();
    await expect(page).toHaveURL(/\/student\/account$/);
  });

  test("öğrenme kaydı: kavramlar eksiği olan önce, denemeler puanla; kaynak yanda açılır", async ({ page }) => {
    const algorithms = course("A");
    await page.route(`**/api/courses/${algorithms.id}/learning-record`, (route) =>
      route.fulfill(json(learningRecord(algorithms.id, algorithms.documentTitle))),
    );
    await page.goto(`/student/courses/${algorithms.id}/learning`);

    const concepts = page.getByRole("listitem").filter({ hasText: "Son puan" });
    await expect(concepts.first()).toContainText("ikili arama karmaşıklığı");
    await expect(concepts.first()).toContainText("Tekrar et");
    await expect(concepts.first()).toContainText("log n");
    await expect(concepts.nth(1)).toContainText("Son deneme tam");
    await expect(page.getByText("1 / 4")).toBeVisible();
    await expect(page.getByText("Bu soru eğitmen tarafından düzeltildi ve geri çekildi.")).toBeVisible();
    await expect(page.getByRole("note")).toHaveCount(0);

    await page.getByRole("button", { name: /Kaynağı aç/ }).click();
    await expect(page.getByRole("dialog", { name: "Kaynak" })).toBeVisible();
  });

  test("öğrenme kaydı dar ekranda taşmadan okunur @dar-ekran", async ({ page }) => {
    const algorithms = course("A");
    await page.route(`**/api/courses/${algorithms.id}/learning-record`, (route) =>
      route.fulfill(json(learningRecord(algorithms.id, algorithms.documentTitle))),
    );
    await page.goto(`/student/courses/${algorithms.id}/learning`);

    await expect(page.getByText("ikili arama karmaşıklığı").first()).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test("hesabım: araştırma kaydı açılıp kapanır; verilerimi sil onay ister ve gerçek API ile siler", async ({
    page,
  }) => {
    await page.goto("/student");
    await page.getByRole("link", { name: /Hesabım/ }).click();
    await expect(page.getByRole("heading", { name: "Hesabım" })).toBeVisible();

    const research = page.getByRole("checkbox", { name: /Öğrenme kaydımı tut/ });
    await expect(research).not.toBeChecked();
    await research.check();
    await expect(page.getByText("Öğrenme kaydı açıldı")).toBeVisible();
    await expect(research).toBeChecked();
    await research.uncheck();
    await expect(page.getByText("Öğrenme kaydı kapatıldı")).toBeVisible();

    await page.getByRole("button", { name: "Verilerimi sil" }).click();
    const dialog = page.getByRole("dialog", { name: "Verilerin silinsin mi?" });
    await expect(dialog).toContainText("geri alınamaz");
    await dialog.getByRole("button", { name: "Vazgeç" }).click();
    await expect(dialog).toHaveCount(0);

    await page.getByRole("button", { name: "Verilerimi sil" }).click();
    await page.getByRole("button", { name: "Verilerimi kalıcı olarak sil" }).click();
    await expect(page.getByText("Verilerin silindi")).toBeVisible();
  });

  test("öğrenme kaydı yüklenemezse söylenir; tekrar dene ile gelir", async ({ page }) => {
    const algorithms = course("A");
    const path = `**/api/courses/${algorithms.id}/learning-record`;
    await page.route(path, (route) => route.fulfill({ status: 500, body: "" }));
    await page.goto(`/student/courses/${algorithms.id}/learning`);

    await expect(page.getByText("Öğrenme kaydı yüklenemedi")).toBeVisible();
    await page.unroute(path);
    await page.getByRole("button", { name: "Tekrar dene" }).click();
    await expect(page.getByText("Henüz kayıtlı deneme yok")).toBeVisible();
  });

  test("hesabım: tercih ya da silme kaydedilemezse söylenir; kutucuk eski hâline döner", async ({ page }) => {
    await page.route("**/api/me/consent", (route) => route.fulfill({ status: 500, body: "" }));
    await page.route("**/api/me/data", (route) => route.fulfill({ status: 500, body: "" }));
    await page.goto("/student/account");

    const research = page.getByRole("checkbox", { name: /Öğrenme kaydımı tut/ });
    await research.click();
    await expect(page.getByText("Tercih kaydedilemedi")).toBeVisible();
    await expect(research).not.toBeChecked();

    await page.getByRole("button", { name: "Verilerimi sil" }).click();
    const dialog = page.getByRole("dialog", { name: "Verilerin silinsin mi?" });
    await dialog.getByRole("button", { name: "Verilerimi kalıcı olarak sil" }).click();
    await expect(dialog.getByRole("alert")).toContainText("Silme işlemi tamamlanamadı");
    await expect(dialog).toBeVisible();
  });

  test("yetki: öğrenci eğitmen incelemesine giremez, inceleme API'si 403 döner; üye olmadığı ders bulunmaz", async ({
    page,
  }) => {
    const algorithms = course("A");
    await page.goto(`/instructor/courses/${algorithms.id}/review`);
    await expect(page).toHaveURL(/\/student$/);

    const items = await page.request.get(`/api/instructor/courses/${algorithms.id}/practice-items`);
    expect(items.status()).toBe(403);
    const review = await page.request.post("/api/instructor/reviews", {
      data: { target_type: "practice_item", target_id: 1, decision: "approve" },
      headers: { Origin: BASE_URL },
    });
    expect([403, 404]).toContain(review.status());

    await page.goto("/student/courses/999999/learning");
    await expect(page.getByText("Ders bulunamadı")).toBeVisible();
    const record = await page.request.get("/api/courses/999999/learning-record");
    expect(record.status()).toBe(404);
  });
});

function practiceItem(documentTitle: string) {
  return {
    id: 77,
    type: "mcq",
    topic: "ikili arama",
    difficulty: "medium",
    prompt: "İkili arama her adımda ne yapar?",
    options: ["Yarıyı atar", "Baştan tarar", "Diziyi sıralar", "Rastgele seçer"],
    correct_option: 0,
    reference_answer: null,
    explanation: "Aralığın yarısı atılır.",
    status: "released",
    rubric_approved: false,
    source: { source_id: "e2e-kaynak-1", document_title: documentTitle, page: 1, t_start: null, t_end: null },
    created_at: new Date().toISOString(),
    latest_review: null,
  };
}

function reviewOut(targetType: string, targetId: number, decision: string, correction: string | null) {
  return {
    id: 1,
    target_type: targetType,
    target_id: targetId,
    decision,
    correction,
    created_at: new Date().toISOString(),
  };
}

/** Üç öğrencinin soruları olan bir ders etkinliği (gerçek sistemde en az üç öğrenci gerekir). */
function activity() {
  const today = new Date();
  const daily = Array.from({ length: 14 }, (_, index) => {
    const day = new Date(today);
    day.setDate(today.getDate() - 13 + index);
    return { day: day.toISOString().slice(0, 10), questions: index === 13 ? 3 : 0 };
  });
  const question = (text: string, id: number) => ({
    question: text,
    outcome: "answered",
    asked_at: today.toISOString(),
    answer_message_id: id,
  });
  return {
    questions: 3,
    conversations: 3,
    answered: 3,
    not_covered: 0,
    not_generated: 0,
    unavailable: 0,
    daily,
    top_sources: [],
    recent_questions: [question("İkili arama neden hızlı?", 501), question("Dizi sıralı değilse ne olur?", 502)],
    unanswered_questions: [],
  };
}

test.describe("eğitmen", () => {
  test.beforeAll(async () => {
    // Test eğitmeni aydınlatma metnini bir kez onaylar (öğrenciye global-setup'ta yapılıyor).
    const api = await request.newContext({ baseURL: BASE_URL });
    await apiLogin(api, INSTRUCTOR);
    const consent = await api.put("/api/me/consent", {
      data: { research_logging: false, policy_version: PRIVACY_POLICY_VERSION },
    });
    expect(consent.ok(), await consent.text()).toBeTruthy();
    await api.dispose();
  });

  test.beforeEach(async ({ page }) => {
    await loginAsInstructor(page);
  });

  test("inceleme: sık hata yoksa nedeni söylenir; pratik sorusu cevap anahtarıyla görünür ve düzeltilir", async ({
    page,
  }) => {
    const algorithms = course("A");
    await page.route(`**/api/instructor/courses/${algorithms.id}/practice-items`, (route) =>
      route.fulfill(json([practiceItem(algorithms.documentTitle)])),
    );
    const reviews: unknown[] = [];
    await page.route("**/api/instructor/reviews", async (route) => {
      reviews.push(route.request().postDataJSON());
      await route.fulfill(json(reviewOut("practice_item", 77, "correct", "B şıkkı da savunulabilir.")));
    });

    await page.goto(`/instructor/courses/${algorithms.id}/review`);
    await expect(page.getByRole("heading", { name: "İnceleme ve sık hatalar" })).toBeVisible();

    // Sık hatalar gerçek API'den: test sisteminde deneme yok.
    await expect(page.getByText("Henüz yeterli veri yok")).toBeVisible();
    const card = page.getByRole("listitem").filter({ hasText: "İkili arama her adımda ne yapar?" });
    await expect(card.getByText("(doğru cevap)")).toBeAttached();
    await expect(card).toContainText("Henüz incelenmedi");

    await card.getByRole("button", { name: "Düzelt" }).click();
    const dialog = page.getByRole("dialog", { name: "Pratik sorusunu düzelt" });
    await dialog.getByRole("button", { name: "Düzeltmeyi kaydet" }).click();
    await expect(dialog.getByRole("alert")).toContainText("Neyin yanlış olduğunu");
    await dialog.getByRole("textbox", { name: "Düzeltme" }).fill("B şıkkı da savunulabilir.");
    await dialog.getByRole("button", { name: "Düzeltmeyi kaydet" }).click();

    await expect(card).toContainText("Düzeltildi, öğrencilere sunulmuyor.");
    await expect(card.getByRole("button", { name: "Yeniden onayla" })).toBeVisible();
    expect(reviews).toEqual([
      { target_type: "practice_item", target_id: 77, decision: "correct", correction: "B şıkkı da savunulabilir." },
    ]);
  });

  test("inceleme: sık hatalar yüklenemezse söylenir; düzeltme kaydedilemezse diyalog açık kalır", async ({ page }) => {
    const algorithms = course("A");
    await page.route(`**/api/instructor/courses/${algorithms.id}/mistakes`, (route) =>
      route.fulfill({ status: 500, body: "" }),
    );
    await page.route(`**/api/instructor/courses/${algorithms.id}/practice-items`, (route) =>
      route.fulfill(json([practiceItem(algorithms.documentTitle)])),
    );
    await page.route("**/api/instructor/reviews", (route) => route.fulfill({ status: 500, body: "" }));

    await page.goto(`/instructor/courses/${algorithms.id}/review`);
    await expect(page.getByText("Sık hatalar yüklenemedi")).toBeVisible();

    const card = page.getByRole("listitem").filter({ hasText: "İkili arama her adımda ne yapar?" });
    await card.getByRole("button", { name: "Düzelt" }).click();
    const dialog = page.getByRole("dialog", { name: "Pratik sorusunu düzelt" });
    await dialog.getByRole("textbox", { name: "Düzeltme" }).fill("Şıklar belirsiz.");
    await dialog.getByRole("button", { name: "Düzeltmeyi kaydet" }).click();
    await expect(dialog.getByRole("alert")).toContainText("Düzeltme kaydedilemedi");
    await expect(dialog.getByRole("textbox", { name: "Düzeltme" })).toHaveValue("Şıklar belirsiz.");
    await expect(card).toContainText("Henüz incelenmedi");

    await dialog.getByRole("button", { name: "Vazgeç" }).click();
    await card.getByRole("button", { name: "Onayla" }).click();
    await expect(page.getByText("Onay kaydedilemedi")).toBeVisible();
  });

  test("etkinlik: asistanın cevabı onaylanır ya da düzeltilir; onay kaydedilemezse söylenir", async ({ page }) => {
    const algorithms = course("A");
    await page.route(`**/api/instructor/courses/${algorithms.id}/activity`, (route) => route.fulfill(json(activity())));
    const reviews: { target_id: number; decision: string }[] = [];
    let failNext = true;
    await page.route("**/api/instructor/reviews", async (route) => {
      const body = route.request().postDataJSON() as { target_id: number; decision: string; correction?: string };
      if (failNext) {
        failNext = false;
        await route.fulfill({ status: 500, body: "" });
        return;
      }
      reviews.push(body);
      await route.fulfill(json(reviewOut("message", body.target_id, body.decision, body.correction ?? null)));
    });

    await page.goto(`/instructor/courses/${algorithms.id}/activity`);
    await page.getByRole("button", { name: "Cevabı onayla: İkili arama neden hızlı?" }).click();
    await expect(page.getByText("Onay kaydedilemedi")).toBeVisible();
    await page.getByRole("button", { name: "Cevabı onayla: İkili arama neden hızlı?" }).click();
    await expect(page.getByText("Cevabı onayladın")).toBeVisible();

    await page.getByRole("button", { name: "Cevabı düzelt: Dizi sıralı değilse ne olur?" }).click();
    const dialog = page.getByRole("dialog", { name: "Asistanın cevabını düzelt" });
    await expect(dialog).toContainText("Dizi sıralı değilse ne olur?");
    await dialog.getByRole("textbox", { name: "Düzeltme" }).fill("İkili arama sıralı dizi ister.");
    await dialog.getByRole("button", { name: "Düzeltmeyi kaydet" }).click();
    await expect(page.getByText("Düzeltmen kaydedildi")).toBeVisible();
    expect(reviews.map((review) => [review.target_id, review.decision])).toEqual([
      [501, "approve"],
      [502, "correct"],
    ]);
  });

  test("inceleme dar ekranda taşmadan kullanılır @dar-ekran", async ({ page }) => {
    const algorithms = course("A");
    await page.route(`**/api/instructor/courses/${algorithms.id}/practice-items`, (route) =>
      route.fulfill(json([practiceItem(algorithms.documentTitle)])),
    );
    await page.goto(`/instructor/courses/${algorithms.id}/review`);

    const card = page.getByRole("listitem").filter({ hasText: "İkili arama her adımda ne yapar?" });
    await expect(card.getByRole("button", { name: "Düzelt" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    await card.getByRole("button", { name: "Düzelt" }).click();
    await expect(page.getByRole("dialog", { name: "Pratik sorusunu düzelt" }).getByRole("button", { name: "Düzeltmeyi kaydet" })).toBeInViewport();
  });

  test("yetki: eğitmen öğrencinin öğrenme kaydı sayfasına giremez", async ({ page }) => {
    await page.goto(`/student/courses/${course("A").id}/learning`);
    await expect(page).toHaveURL(/\/instructor$/);
  });
});

const VIDEO_SOURCE = "e2e-video-kaynak";

/** Tutor turu ve video alıntısı (sözleşmeyle aynı biçim); gönderilen turlar `turns` dizisine yazılır. */
async function mockVideoAnswer(page: Page, videoId: number): Promise<{ video?: unknown }[]> {
  const turns: { video?: unknown }[] = [];
  const citation = { source_id: VIDEO_SOURCE, document_title: "E2E ders videosu", page: null, t_start: 125, t_end: 180 };
  const block = {
    type: "course_answer",
    provenance: "course",
    response: {
      answer: "Her adımda aralık yarıya iner [1].",
      mode: "llm",
      outcome: "answered",
      unsupported_removed: 0,
      coverage_gap: null,
      citations: [citation],
      declined: false,
      decline_reason: null,
      suggested_sources: [],
      conversation_id: 1,
      retrieval: [],
      similarity_threshold: null,
      best_similarity: null,
      model: "gemini-3.8-flash",
      // Backend durdurulan anın bölümünü bildirir (#102).
      video_moment: { document_id: videoId, document_title: "E2E ders videosu", t_start: 125, t_end: 180, deictic: true },
    },
  };
  await page.route("**/api/tutor/turn/stream", async (route) => {
    turns.push(route.request().postDataJSON());
    const events: [string, unknown][] = [
      ["block", { index: 0, block }],
      ["done", { conversation_id: 1, blocks: [block], trace: {} }],
    ];
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join(""),
    });
  });
  await page.route(`**/api/sources/${VIDEO_SOURCE}`, (route) =>
    route.fulfill(
      json({
        source_id: VIDEO_SOURCE,
        document_id: videoId,
        document_title: "E2E ders videosu",
        material_type: "video",
        text: "Her adimda aralik yariya iner, bu yuzden O(log n) zaman alir.",
        page: null,
        t_start: 125,
        t_end: 180,
        media_url: "https://example.org/e2e-ders.mp4",
        page_image_url: null,
        highlights: [],
        alternatives: [],
        frames: [],
      }),
    ),
  );
  return turns;
}

test.describe("ders videosu", () => {
  let instructor: APIRequestContext;
  let videoId: number;

  test.beforeAll(async () => {
    // Gerçek API: eğitmen dersin videosunu altyazısı ve oynatma adresiyle ekler.
    instructor = await request.newContext({ baseURL: BASE_URL });
    await apiLogin(instructor, INSTRUCTOR);
    const vtt =
      "WEBVTT\n\n00:00:00.000 --> 00:01:00.000\nIkili arama sirali dizide ortadaki elemana bakar.\n\n" +
      "00:02:00.000 --> 00:03:00.000\nHer adimda aralik yariya iner, bu yuzden O(log n) zaman alir.\n";
    const uploaded = await instructor.post(`/api/courses/${course("A").id}/materials`, {
      multipart: {
        material_type: "video",
        declaration: "true",
        title: "E2E ders videosu",
        media_url: "https://example.org/e2e-ders.mp4",
        file: { name: "e2e-ders.vtt", mimeType: "text/vtt", buffer: Buffer.from(vtt) },
      },
    });
    expect(uploaded.ok(), await uploaded.text()).toBeTruthy();
    videoId = ((await uploaded.json()) as { id: number }).id;
  });

  test.afterAll(async () => {
    await instructor.delete(`/api/documents/${videoId}`);
    await instructor.dispose();
  });

  test.beforeEach(async ({ page }) => {
    await loginAsStudent(page);
  });

  test("Tutor'da video: soru durdurulan anla gider; video alıntısından o ana atlanır", async ({ page }) => {
    const algorithms = course("A");
    const turns = await mockVideoAnswer(page, videoId);

    // AI Tutor'da da video açılabilir (alıntıdaki "Videoda göster"): soru o anla gider.
    await page.goto(`/student/courses/${algorithms.id}/tutor?video=${videoId}&t=30`);
    await expect(page.getByText("Soruların videonun 0:30 anıyla birlikte gider")).toBeVisible();
    await ask(page, "Burada neden yarıya iniyor?");
    await expect.poll(() => turns.length).toBe(1);
    expect(turns[0].video).toEqual({ document_id: videoId, time_s: 30 });

    // Cevap durdurulan anın bölümüne dayanır ve bunu söyler; kaynak "video" olarak sayılır (#102).
    await expect(page.getByText("Sorunu videonun 2:05–3:00 kısmına göre anladım")).toBeVisible();
    await expect(page.getByText("1 video", { exact: true })).toBeVisible();
    await expect(page.getByText(/\d+ belge/)).toHaveCount(0);
    await page.getByRole("button", { name: "Videoda 2:05–3:00 kısmına git" }).click();
    await expect(page.getByText("Soruların videonun 2:05 anıyla birlikte gider")).toBeVisible();

    await page.getByRole("button", { name: "Videoyu kapat" }).click();
    await page.goto(`/student/courses/${algorithms.id}/tutor?video=${videoId}&t=30`);
    await ask(page, "Burada neden yarıya iniyor?");
    await page.getByRole("list", { name: /Cevabın iddiaları/ }).getByRole("button").first().click();
    await page.getByRole("button", { name: "Videoda bu ana git" }).click();
    await expect(page.getByText("Soruların videonun 2:05 anıyla birlikte gider")).toBeVisible();

    await page.getByRole("button", { name: "Videoyu kapat" }).click();
    await expect(page).toHaveURL(new RegExp(`/student/courses/${algorithms.id}/tutor$`));
    await expect(page.getByLabel("E2E ders videosu")).toHaveCount(0);
  });

  test("oynatılamayan video kimliği oynatıcı açmaz; soru videosuz gider", async ({ page }) => {
    const algorithms = course("A");
    const turns = await mockVideoAnswer(page, videoId);
    const pdfId = (process.env.E2E_DOCUMENT_IDS ?? "").split(",")[0];

    for (const id of [pdfId, "999999"]) {
      await page.goto(`/student/courses/${algorithms.id}/tutor?video=${id}&t=30`);
      await expect(page.getByRole("heading", { name: `${algorithms.name} dersine sor` })).toBeVisible();
      await expect(page.getByRole("button", { name: "Videoyu kapat" })).toHaveCount(0);
      await expect(page.getByText("Soruların videonun")).toHaveCount(0);
    }
    await ask(page, "İkili arama nedir?");
    await expect.poll(() => turns.length).toBe(1);
    expect(turns[0].video).toBeNull();
  });

  test("dar ekranda video sığar; alıntıdan o ana atlanır @dar-ekran", async ({ page }) => {
    const algorithms = course("A");
    await mockVideoAnswer(page, videoId);
    await page.goto(`/student/courses/${algorithms.id}/tutor?video=${videoId}&t=30`);

    await expect(page.getByLabel("E2E ders videosu")).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    await ask(page, "Burada neden yarıya iniyor?");
    await page.getByRole("list", { name: /Cevabın iddiaları/ }).getByRole("button").first().click();
    const source = page.getByRole("dialog", { name: "Kaynak" });
    await source.getByRole("button", { name: "Videoda bu ana git" }).click();
    await expect(source).toHaveCount(0);
    await expect(page.getByText("Soruların videonun 2:05 anıyla birlikte gider")).toBeVisible();
  });
});


test.describe("video çalışma ekranı", () => {
  let instructor: APIRequestContext;
  let videoId: number;

  test.beforeAll(async () => {
    instructor = await request.newContext({ baseURL: BASE_URL });
    await apiLogin(instructor, INSTRUCTOR);
    const vtt =
      "WEBVTT\n\n00:00:00.000 --> 00:01:00.000\nIkili arama sirali dizide ortadaki elemana bakar.\n\n" +
      "00:02:00.000 --> 00:03:00.000\nHer adimda aralik yariya iner, bu yuzden O(log n) zaman alir.\n";
    const uploaded = await instructor.post(`/api/courses/${course("A").id}/materials`, {
      multipart: {
        material_type: "video",
        declaration: "true",
        title: "E2E ders videosu",
        media_url: "https://example.org/e2e-ders.mp4",
        file: { name: "e2e-ders.vtt", mimeType: "text/vtt", buffer: Buffer.from(vtt) },
      },
    });
    expect(uploaded.ok(), await uploaded.text()).toBeTruthy();
    videoId = ((await uploaded.json()) as { id: number }).id;
  });

  test.afterAll(async () => {
    await instructor.delete(`/api/documents/${videoId}`);
    await instructor.dispose();
  });

  test.beforeEach(async ({ page }) => {
    await loginAsStudent(page);
  });

  test("izle ve sor: video, transkript ve sohbet bir arada; cevabın video kısmı işaretlenir", async ({ page }) => {
    const algorithms = course("A");
    const turns = await mockVideoAnswer(page, videoId);

    await page.goto(`/student/courses/${algorithms.id}/videos`);
    await page.getByRole("link", { name: "İzle ve sor" }).click();
    await expect(page).toHaveURL(new RegExp(`/student/courses/${algorithms.id}/watch/${videoId}$`));
    await expect(page.getByLabel("E2E ders videosu")).toBeVisible();

    // Transkript kapalı başlar; açılınca zamanlarıyla gelir, satıra tıklayınca video o ana gider.
    const transcript = page.getByRole("region", { name: "Transkript" });
    const toggle = transcript.getByRole("button", { name: /Transkript/ });
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(transcript.getByText("Her adimda aralik yariya iner", { exact: false })).toBeHidden();
    await toggle.click();
    await expect(transcript.getByText("Her adimda aralik yariya iner", { exact: false })).toBeVisible();
    await transcript.getByRole("button", { name: /2:00/ }).click();
    await expect(page.getByText("Sorun videonun 2:00 anıyla gider.")).toBeVisible();

    // Kapalıyken gelen cevap videoya dayanıyorsa transkript kendiliğinden açılır.
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await ask(page, "Burayı anlamadım");
    await expect.poll(() => turns.length).toBe(1);
    expect(turns[0].video).toEqual({ document_id: videoId, time_s: 120 });
    await expect(toggle).toHaveAttribute("aria-expanded", "true");

    const chat = page.getByRole("complementary", { name: "Videoya soru sor" });
    await expect(chat.getByRole("button", { name: "Videodan · 2:05–3:00" })).toBeVisible();
    await expect(page.getByText(/işaretli: cevabın dayandığı kısım/)).toBeVisible();
    await expect(chat.getByRole("button", { name: "Videoya devam et" })).toBeVisible();

    // Cevaptaki video alıntısı videoyu o ana götürür (sayfadan çıkmadan).
    await chat.getByRole("button", { name: "Videodan · 2:05–3:00" }).click();
    await expect(page.getByText("Sorun videonun 2:05 anıyla gider.")).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`/watch/${videoId}$`));
  });

  test("video çalışma ekranı dar ekranda sığar @dar-ekran", async ({ page }) => {
    await page.goto(`/student/courses/${course("A").id}/watch/${videoId}`);
    await expect(page.getByLabel("E2E ders videosu")).toBeInViewport();
    await expect(page.getByRole("textbox", { name: "Sorun" })).toBeVisible();
    // Sayfanın içerik alanı yana taşmaz (video, zaman çizgisi, sohbet, transkript alt alta).
    const overflow = await page.evaluate(() => {
      const main = document.querySelector("main");
      return main ? main.scrollWidth - main.clientWidth : 0;
    });
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
