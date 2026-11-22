import { expect, request, test, type APIRequestContext, type Page } from "@playwright/test";

import { INSTRUCTOR, apiLogin } from "./accounts";
import { ask, course, loginAsStudent, openTutor, switchCourse, waitForAnswer, type SetupCourse } from "./helpers";

// Çoklu ders yalıtımı (#28): A dersinden B'ye geçince A'nın sohbeti, videosu, karesi ve cevabı
// B'de görünmez; tarayıcıda saklanan oturumlar (sessionStorage) ders başınadır. İki derse aynı
// altyazılı video yüklenir (benzer içerik). Test sistemi LLM'siz: cevaplar gerçek API'nin
// alıntılarıdır; kareler henüz dev sistemde çıkarılmadığı için yalnızca A'nın videosuna verilir.

const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:5273";
const VTT =
  "WEBVTT\n\n00:00:00.000 --> 00:01:00.000\nIkili arama sirali dizide ortadaki elemana bakar.\n\n" +
  "00:02:00.000 --> 00:03:00.000\nHer adimda aralik yariya iner, bu yuzden O(log n) zaman alir.\n";
const QUESTION = "Burayı anlamadım";
// 1×1 PNG: kare görüntüsü yerine.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

/** A'nın videosunun kareleri (FrameRef biçimi): tek slayt, A'ya özgü yazıyla. */
async function mockFramesOfA(page: Page, videoId: number) {
  const frame = {
    frame_id: 990,
    document_id: videoId,
    t_start: 0,
    t_end: 180,
    t_frame: 5,
    image_url: `/api/documents/${videoId}/frames/990.png`,
    status: "readable",
    text: "A dersinin slaydı",
    confidence: 0.9,
    extractor: "e2e",
  };
  await page.route(new RegExp(`/api/documents/${videoId}/frames$`), (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([frame]) }),
  );
  await page.route(new RegExp(`/api/documents/${videoId}/frames/\\d+\\.png`), (route) =>
    route.fulfill({ status: 200, contentType: "image/png", body: PNG }),
  );
}

/** Bu sekmenin sessionStorage'ındaki tutor oturumları: anahtar → içerik. */
/**
 * Sekmedeki Tutor kayıtları. Anahtarlar kullanıcıya bağlıdır (`la.tutor.u<kullanıcı>.<ders>…`, #134);
 * karşılaştırma kolay olsun diye kullanıcı kısmı çıkarılır (`la.tutor.<ders>…`).
 */
async function tutorStorage(page: Page): Promise<Record<string, string>> {
  const entries = await page.evaluate(() =>
    Object.keys(sessionStorage)
      .filter((key) => key.startsWith("la.tutor."))
      .map((key) => [key, sessionStorage.getItem(key) ?? ""] as const),
  );
  for (const [key] of entries) expect(key).toMatch(/^la\.tutor\.u\d+\./);
  return Object.fromEntries(entries.map(([key, value]) => [key.replace(/^la\.tutor\.u\d+\./, "la.tutor."), value]));
}

/** Bir dersin anahtarlarında geçen içerik (`la.tutor.<id>` ve `la.tutor.<id>.<kapsam>`). */
function storedFor(storage: Record<string, string>, target: SetupCourse): string {
  return Object.entries(storage)
    .filter(([key]) => key === `la.tutor.${target.id}` || key.startsWith(`la.tutor.${target.id}.`))
    .map(([, value]) => value)
    .join("\n");
}

async function uploadVideo(api: APIRequestContext, target: SetupCourse, title: string): Promise<number> {
  const uploaded = await api.post(`/api/courses/${target.id}/materials`, {
    multipart: {
      material_type: "video",
      declaration: "true",
      title,
      media_url: `https://example.org/${encodeURIComponent(title)}.mp4`,
      file: { name: "e2e-ders.vtt", mimeType: "text/vtt", buffer: Buffer.from(VTT) },
    },
  });
  expect(uploaded.ok(), await uploaded.text()).toBeTruthy();
  return ((await uploaded.json()) as { id: number }).id;
}

test.describe("ders değişince yalıtım", () => {
  let instructor: APIRequestContext;
  let videoA: number;
  let videoB: number;

  test.beforeAll(async () => {
    instructor = await request.newContext({ baseURL: BASE_URL });
    await apiLogin(instructor, INSTRUCTOR);
    videoA = await uploadVideo(instructor, course("A"), "Yalitim videosu A");
    videoB = await uploadVideo(instructor, course("B"), "Yalitim videosu B");
  });

  test.afterAll(async () => {
    for (const id of [videoA, videoB]) if (id) await instructor.delete(`/api/documents/${id}`);
    await instructor.dispose();
  });

  test.beforeEach(async ({ page }) => {
    await loginAsStudent(page);
  });

  test("video çalışma ekranı: A'nın videosu, karesi ve cevabı B'de görünmez; oturum ders başına", async ({
    page,
  }) => {
    const algorithms = course("A");
    const dataStructures = course("B");
    await mockFramesOfA(page, videoA);

    await page.goto(`/student/courses/${algorithms.id}/watch/${videoA}`);
    await expect(page.getByLabel("Yalitim videosu A")).toBeVisible();
    await expect(page.getByText("Sorun videonun 0:00 anıyla gider.")).toBeVisible();
    await ask(page, QUESTION);
    await waitForAnswer(page);
    const chat = page.getByRole("complementary", { name: "Videoya soru sor" });
    const answered = chat.getByRole("article", { name: QUESTION });
    await expect(answered.getByRole("figure", { name: "Durdurduğun anda ekranda" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Slaytlar" })).toBeVisible();
    expect(storedFor(await tutorStorage(page), algorithms)).toContain(QUESTION);

    // Çalışma ekranında ders menüsü yok: öğrenci ders videolarına dönüp oradan derse geçer.
    const afterSwitch: string[] = [];
    await page.getByRole("link", { name: "Ders videoları" }).click();
    await expect(page).toHaveURL(new RegExp(`/student/courses/${algorithms.id}/videos$`));
    page.on("request", (req) => afterSwitch.push(req.url()));
    await switchCourse(page, algorithms, dataStructures);
    await expect(page).toHaveURL(new RegExp(`/student/courses/${dataStructures.id}/videos$`));
    await expect(page.getByRole("link", { name: "Yalitim videosu B" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Yalitim videosu A" })).toHaveCount(0);

    // B'nin videosu: boş sohbet, A'nın karesi ve cevabı yok; A'nın videosu için istek gitmez.
    await page.getByRole("link", { name: "İzle ve sor" }).click();
    await expect(page).toHaveURL(new RegExp(`/student/courses/${dataStructures.id}/watch/${videoB}$`));
    await expect(page.getByLabel("Yalitim videosu B")).toBeVisible();
    await expect(page.getByText("Sorun videonun 0:00 anıyla gider.")).toBeVisible();
    await expect(page.getByRole("article")).toHaveCount(0);
    await expect(page.getByRole("figure", { name: "Durdurduğun anda ekranda" })).toHaveCount(0);
    await expect(page.getByRole("navigation", { name: "Slaytlar" })).toHaveCount(0);
    await expect(page.getByText("A dersinin slaydı")).toHaveCount(0);
    expect(afterSwitch.filter((url) => url.includes(`/api/documents/${videoA}/`))).toEqual([]);

    // B'de sorulan soru B'nin videosuyla gider; A'nın videosu istekte geçmez.
    const sent: { course_id?: number; video?: { document_id: number } }[] = [];
    page.on("request", (req) => {
      if (req.url().includes("/api/tutor/turn")) sent.push(req.postDataJSON());
    });
    await ask(page, "Peki bu?");
    await waitForAnswer(page);
    expect(sent).toHaveLength(1);
    expect(sent[0].course_id).toBe(dataStructures.id);
    expect(sent[0].video?.document_id).toBe(videoB);
    await expect(page.getByRole("article", { name: QUESTION })).toHaveCount(0);

    // Tarayıcı oturumu: A'nın sohbeti yalnızca A'nın anahtarında; B'nin hiçbir anahtarında yok.
    const storage = await tutorStorage(page);
    expect(storedFor(storage, dataStructures)).not.toContain(QUESTION);
    expect(storedFor(storage, dataStructures)).toContain("Peki bu?");
    expect(storedFor(storage, algorithms)).not.toContain("Peki bu?");
    expect(Object.keys(storage).filter((key) => key.includes(`video-${videoA}`))).toEqual([
      `la.tutor.${algorithms.id}.video-${videoA}`,
    ]);

    // A'ya dönünce A'nın video sohbeti geri gelir (sekme oturumunda, ders + video başına).
    await page.goto(`/student/courses/${algorithms.id}/watch/${videoA}`);
    await expect(page.getByRole("complementary", { name: "Videoya soru sor" }).getByRole("article", { name: QUESTION })).toBeVisible();
  });

  test("AI Tutor: ders değişince sohbet sıfırlanır; oturum kayıtları ders başına", async ({ page }) => {
    const algorithms = course("A");
    const dataStructures = course("B");
    await openTutor(page, algorithms);
    await ask(page, "İkili arama nasıl çalışır?");
    await waitForAnswer(page);
    expect(storedFor(await tutorStorage(page), algorithms)).toContain("İkili arama nasıl çalışır?");

    await switchCourse(page, algorithms, dataStructures);
    await expect(page.getByRole("heading", { name: `${dataStructures.name} dersine sor` })).toBeVisible();
    await expect(page.getByText("İkili arama nasıl çalışır?")).toHaveCount(0);
    await expect(page.getByText(algorithms.documentTitle)).toHaveCount(0);

    await ask(page, "Yığın nasıl çalışır?");
    await waitForAnswer(page);
    // B'nin cevabı yalnızca B'nin kaynağını gösterir.
    const panel = page.getByRole("complementary", { name: "Kaynak" });
    await expect(panel.getByText(dataStructures.documentTitle, { exact: true }).first()).toBeVisible();
    await expect(page.getByText(algorithms.documentTitle)).toHaveCount(0);

    const storage = await tutorStorage(page);
    expect(storedFor(storage, dataStructures)).toContain("Yığın nasıl çalışır?");
    expect(storedFor(storage, dataStructures)).not.toContain("İkili arama nasıl çalışır?");
    expect(storedFor(storage, algorithms)).not.toContain("Yığın nasıl çalışır?");
    const conversation = (target: SetupCourse) =>
      (JSON.parse(storage[`la.tutor.${target.id}`]) as { conversationId: number | null }).conversationId;
    expect(conversation(algorithms)).not.toBeNull();
    expect(conversation(dataStructures)).not.toBe(conversation(algorithms));
  });
});
