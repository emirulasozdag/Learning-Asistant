import { expect, request, test, type APIRequestContext, type Page } from "@playwright/test";

import { INSTRUCTOR, apiLogin } from "./accounts";
import { ask, course, loginAsStudent, waitForAnswer } from "./helpers";

// Görsel tutor kullanılabilirliği (#32): sorunun sorulduğu video anı turla saklanır; sayfa
// yenilenince ya da video kapatılınca "durdurduğun anda ekranda" karesi kaybolmaz, zaman çizgisi
// klavyeyle kullanılır ve video ekranı dar ekranda yana taşmaz. Test sistemi LLM'siz; kareler
// dev sistemde çıkarılmadığı için videonun kareleri (FrameRef) testte verilir.

const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:5273";
const TITLE = "Kullanilabilirlik videosu";
const VTT =
  "WEBVTT\n\n00:00:00.000 --> 00:01:00.000\nIkili arama sirali dizide ortadaki elemana bakar.\n\n" +
  "00:01:00.000 --> 00:03:00.000\nHer adimda aralik yariya iner, bu yuzden O(log n) zaman alir.\n";
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

/** Videonun tek slaytlık kareleri: 0–180 sn ekranda. */
async function mockFrames(page: Page, videoId: number) {
  const frame = {
    frame_id: 991,
    document_id: videoId,
    t_start: 0,
    t_end: 180,
    t_frame: 5,
    image_url: `/api/documents/${videoId}/frames/991.png`,
    status: "readable",
    text: "Ikili arama slaydi",
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

/** Sohbette sorunun balonu: soru metni ve sorulduğu an ("Burayı anlamadım · 1:00"). */
function questionBubble(page: Page, question: string) {
  return page.getByRole("article", { name: question }).locator("p").first();
}

test.describe("video ile çalışma: an, kare ve klavye", () => {
  let instructor: APIRequestContext;
  let videoId: number;

  test.beforeAll(async () => {
    instructor = await request.newContext({ baseURL: BASE_URL });
    await apiLogin(instructor, INSTRUCTOR);
    const uploaded = await instructor.post(`/api/courses/${course("A").id}/materials`, {
      multipart: {
        material_type: "video",
        declaration: "true",
        title: TITLE,
        media_url: "https://example.org/kullanilabilirlik.mp4",
        file: { name: "e2e-ders.vtt", mimeType: "text/vtt", buffer: Buffer.from(VTT) },
      },
    });
    expect(uploaded.ok(), await uploaded.text()).toBeTruthy();
    videoId = ((await uploaded.json()) as { id: number }).id;
  });

  test.afterAll(async () => {
    if (videoId) await instructor.delete(`/api/documents/${videoId}`);
    await instructor.dispose();
  });

  test.beforeEach(async ({ page }) => {
    await loginAsStudent(page);
    await mockFrames(page, videoId);
  });

  test("video çalışma ekranı: zaman çizgisi klavyeyle; sorunun anı ve karesi yenileyince kalır", async ({
    page,
  }) => {
    const algorithms = course("A");
    await page.goto(`/student/courses/${algorithms.id}/watch/${videoId}`);
    await expect(page.getByLabel(TITLE)).toBeVisible();

    // Zaman çizgisi: oklar 10 sn, Home/End baş ve son.
    const timeline = page.getByRole("slider", { name: "Video zaman çizgisi" });
    await timeline.focus();
    await timeline.press("End");
    await expect(timeline).toHaveAttribute("aria-valuetext", "2:59");
    await timeline.press("Home");
    await expect(timeline).toHaveAttribute("aria-valuetext", "0:00");
    for (let step = 0; step < 6; step++) await timeline.press("ArrowRight");
    await expect(timeline).toHaveAttribute("aria-valuetext", "1:00");
    await expect(page.getByText("Sorun videonun 1:00 anıyla gider.")).toBeVisible();

    // Soru o anla gider; sohbette an ve o andaki kare görünür.
    const sent: { video?: { document_id: number; time_s: number } }[] = [];
    page.on("request", (req) => {
      if (req.url().includes("/api/tutor/turn")) sent.push(req.postDataJSON());
    });
    const question = "Burayı anlamadım";
    await ask(page, question);
    await waitForAnswer(page);
    expect(sent[0]?.video).toEqual({ document_id: videoId, time_s: 60 });
    await expect(questionBubble(page, question)).toHaveText(`${question}· 1:00`);
    const chat = page.getByRole("complementary", { name: "Videoya soru sor" });
    await expect(chat.getByRole("figure", { name: "Durdurduğun anda ekranda" })).toBeVisible();

    // Sayfa yenilenince sohbet, sorunun anı ve karesiyle geri gelir.
    await page.reload();
    await expect(questionBubble(page, question)).toHaveText(`${question}· 1:00`);
    await expect(chat.getByRole("figure", { name: "Durdurduğun anda ekranda" })).toBeVisible();
  });

  test("AI Tutor: video kapanınca da soru sorulan anın karesi kalır; kareden video o anda açılır", async ({
    page,
  }) => {
    const algorithms = course("A");
    await page.goto(`/student/courses/${algorithms.id}/tutor?video=${videoId}&t=60`);
    await expect(page.getByLabel(TITLE)).toBeVisible();
    await ask(page, "Bu kısmı açıklar mısın?");
    await waitForAnswer(page);
    const frame = page.getByRole("figure", { name: "Durdurduğun anda ekranda" });
    await expect(frame).toBeVisible();

    // Video kapatılır: kare sorunun anına aittir, kaybolmaz.
    await page.getByRole("button", { name: "Videoyu kapat" }).click();
    await expect(page.getByLabel(TITLE)).toHaveCount(0);
    await expect(frame).toBeVisible();

    // Sayfaya dönünce de kare yerinde.
    await page.goto(`/student/courses/${algorithms.id}/tutor`);
    await expect(frame).toBeVisible();

    // "Videoda bu ana git" videoyu sorunun anında yeniden açar.
    await frame.getByRole("button", { name: "Videoda bu ana git" }).first().click();
    await expect(page).toHaveURL(new RegExp(`video=${videoId}&t=60`));
    await expect(page.getByLabel(TITLE)).toBeVisible();
  });

  test("video çalışma ekranı dar ekranda yana taşmaz @dar-ekran", async ({ page }) => {
    const algorithms = course("A");
    await page.goto(`/student/courses/${algorithms.id}/watch/${videoId}`);
    await expect(page.getByLabel(TITLE)).toBeVisible();
    await expect(page.getByRole("complementary", { name: "Videoya soru sor" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});
