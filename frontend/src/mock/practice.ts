/**
 * Pratik çalışma alanı için örnek soru ve değerlendirme (ekip görevi: docs/UI_GOREVLERI.md).
 * Gerçek kaynak: POST /practice (FR-11) ve POST /practice/{id}/answer (FR-13).
 */

export interface PracticeQuestion {
  id: string;
  courseCode: string;
  topic: string;
  type: "short_answer" | "mcq" | "code_tracing";
  difficulty: "Kolay" | "Orta" | "Zor";
  prompt: string;
  source: { documentTitle: string; page: number };
}

export interface PracticeFeedback {
  score: number;
  maxScore: number;
  understood: string[];
  missing: string[];
  explanation: string;
  source: { documentTitle: string; page: number };
}

export const SAMPLE_QUESTION: PracticeQuestion = {
  id: "p-1",
  courseCode: "BLM2512",
  topic: "İkili arama",
  type: "short_answer",
  difficulty: "Orta",
  prompt:
    "Sıralı bir dizide ikili arama yaparken hedef, ortadaki elemandan küçükse neden dizinin sağ yarısını tamamen eleyebiliriz? Cevabında sıralılık koşulunu ve bir adımdaki arama aralığının nasıl değiştiğini açıkla.",
  source: { documentTitle: "ikili_arama_notlari", page: 2 },
};

export const SAMPLE_FEEDBACK: PracticeFeedback = {
  score: 8,
  maxScore: 10,
  understood: [
    "Dizi sıralı olduğu için ortanın sağındaki tüm elemanların hedeften büyük olduğunu doğru belirttin.",
    "Her adımda aralığın yarıya indiğini söyledin.",
  ],
  missing: ["Yeni aralığın sınırlarını (hi = mid - 1) açıkça yazmadın."],
  explanation:
    "Hedef A[mid]'den küçükse arama sol yarıda sürer ve üst sınır hi = mid - 1 olur. mid dahil edilmez, çünkü A[mid] zaten hedeften büyüktür.",
  source: { documentTitle: "ikili_arama_notlari", page: 3 },
};
