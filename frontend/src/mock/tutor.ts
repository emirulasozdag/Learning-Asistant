/** AI Tutor boşken önerilen sorular. Anahtar: ders kodu; yoksa genel öneriler. */
export const SUGGESTED_QUESTIONS: Record<string, string[]> = {
  BLM2512: [
    "Binary search neden sıralı bir dizi gerektirir?",
    "İkili aramada neden sağ yarıyı atabiliyoruz?",
    "İkili aramanın zaman karmaşıklığı nedir?",
  ],
  BLM3021: [
    "Binary search neden sıralı bir dizi gerektirir?",
    "İkili aramanın zaman karmaşıklığı nedir?",
    "mid değeri nasıl hesaplanır?",
  ],
};

export const GENERIC_QUESTIONS = [
  "Bu dersin ilk haftasında hangi konular işlendi?",
  "Ders notlarındaki temel tanımları özetler misin?",
];
