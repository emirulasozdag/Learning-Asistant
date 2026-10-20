import type { Browser } from "@playwright/test";

/**
 * Test dersleri ve PDF içerikleri. Metinler bu testler için yazıldı; gerçek ders materyali
 * değildir. Her `pages` öğesi PDF'te ayrı bir sayfa olur.
 */
export interface TestCourse {
  key: "A" | "B";
  name: string;
  documentTitle: string;
  pages: { heading: string; paragraphs: string[] }[];
}

export const COURSE_A: TestCourse = {
  key: "A",
  name: "E2E Algoritmalar",
  documentTitle: "E2E algoritma notları",
  pages: [
    {
      heading: "İkili arama",
      paragraphs: [
        "İkili arama sıralı bir dizide aranan değeri bulmak için kullanılır.",
        // "çalışır" testlerin sorusunda geçer: sahte embedder'la alakasızlık kapısı kelime kapsamasına bakar.
        "İkili arama şöyle çalışır: her adımda dizinin ortasındaki eleman aranan değerle karşılaştırılır. Aranan değer ortadaki elemandan küçükse sağ yarı atılır, büyükse sol yarı atılır.",
        "Böylece her adımda arama alanı yarıya iner ve ikili aramanın zaman karmaşıklığı logaritmiktir.",
      ],
    },
    {
      heading: "Kabarcık sıralaması",
      paragraphs: [
        "Kabarcık sıralaması komşu elemanları karşılaştırır ve yanlış sıradaysa yerlerini değiştirir.",
        "Dizi sıralanana kadar geçişler tekrarlanır. En kötü durumda kabarcık sıralamasının zaman karmaşıklığı kareseldir.",
      ],
    },
  ],
};

export const COURSE_B: TestCourse = {
  key: "B",
  name: "E2E Veri Yapıları",
  documentTitle: "E2E veri yapısı notları",
  pages: [
    {
      heading: "Yığın",
      paragraphs: [
        "Yığın son giren ilk çıkar ilkesiyle çalışan bir veri yapısıdır.",
        "Ekleme işlemine push, çıkarma işlemine pop denir. Yığın, fonksiyon çağrılarını ve geri alma işlemlerini saklamak için kullanılır.",
      ],
    },
    {
      heading: "Kuyruk",
      paragraphs: [
        "Kuyruk ilk giren ilk çıkar ilkesiyle çalışır.",
        "Elemanlar kuyruğun sonuna eklenir ve başından çıkarılır. Yazıcı işleri ve görev sıraları kuyrukla yönetilir.",
      ],
    },
  ],
};

/** Basit bir HTML sayfasını tarayıcıda PDF'e çevirir (her bölüm ayrı sayfa). */
export async function renderPdf(browser: Browser, course: TestCourse): Promise<Buffer> {
  const sections = course.pages
    .map(
      (page) =>
        `<section><h1>${page.heading}</h1>${page.paragraphs.map((text) => `<p>${text}</p>`).join("")}</section>`,
    )
    .join("");
  const page = await browser.newPage();
  try {
    await page.setContent(
      `<!doctype html><html lang="tr"><head><meta charset="utf-8"><style>
        body { font-family: Arial, sans-serif; font-size: 14pt; line-height: 1.5; }
        section { page-break-after: always; }
        section:last-child { page-break-after: auto; }
      </style></head><body>${sections}</body></html>`,
    );
    return await page.pdf({ format: "A4", margin: { top: "2cm", bottom: "2cm", left: "2cm", right: "2cm" } });
  } finally {
    await page.close();
  }
}
