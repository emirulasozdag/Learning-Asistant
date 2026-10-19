import { ApiError } from "../../api/client";
import type { AskResponse } from "../../api/types";
import type { TutorFailure, Turn } from "./types";

/** Öğrenciye gösterilen sonucun türü. Her tür farklı bir şey söyler ve farklı bir şey önerir. */
export type ResponseOutcome =
  /** Kaynaklı cevap hazır. */
  | "answered"
  /** Yapay zekâ kullanılamıyor; ders materyalinden ilgili bölüm aynen gösterildi. */
  | "ai_unavailable"
  /** Kaynak bulundu ama dayanaklı bir cevap üretilemedi (soru kapsam dışı değil). */
  | "not_generated"
  /** Soru için ders materyalinde yeterli bilgi yok. */
  | "out_of_scope";

// GEÇİCİ: backend şimdilik ret nedenini yalnızca metin olarak veriyor. Bu sabitler
// backend/app/generation/answer.py içindeki UNSUPPORTED / REFUSED / NOT_COVERED ile birebir
// aynı olmalı. Backend `AskResponse`'a bir kod alanı (ör. `decline_code`) eklediğinde bu
// eşleştirme silinip o alan kullanılacak.
const DECLINE_UNSUPPORTED = "Cevap ders kaynaklarına dayandırılamadı; bu yüzden gösterilmedi.";
const DECLINE_REFUSED = "Model bu soruyu yanıtlamadı.";
const DECLINE_NOT_COVERED =
  "Bu konu ders materyalinde yer almıyor; cevap uydurmamak için yanıt verilmedi.";

/**
 * Backend cevabını öğrenciye gösterilecek türe çevirir.
 *
 * `mode === "extractive"` yapısal işarettir (yapay zekâ yok). Retlerde yalnızca
 * `decline_reason` ayırt edici: UNSUPPORTED ve REFUSED, soru ilgisizlik kapısını
 * geçtikten sonra üretimde oluşur. Benzerlik değerine (`best_similarity`) bakılmaz, çünkü
 * kelime eşleşmesiyle kapıyı geçen düşük benzerlikli bir soruda da bu retler çıkabilir
 * ve "kapsam dışı" diye yanlış etiketlenirdi. Geri kalan her ret (kapıda elenen ya da
 * modelin "materyalde yok" demesi) kapsam dışıdır.
 */
export function classifyResponse(response: AskResponse): ResponseOutcome {
  if (!response.declined) return response.mode === "extractive" ? "ai_unavailable" : "answered";
  if (response.decline_reason === DECLINE_UNSUPPORTED || response.decline_reason === DECLINE_REFUSED) {
    return "not_generated";
  }
  return "out_of_scope";
}

/**
 * Kapsam dışı retin öğrenciye gösterilecek açıklaması. Backend'in sabit cümlesi kesin bir
 * iddia ("yer almıyor") içerdiği için yerine sade bir yönlendirme gelir; modelin kendi yazdığı
 * eksik-bilgi cümlesi olduğu gibi gösterilir. GEÇİCİ: `classifyResponse` ile birlikte,
 * backend ret kodu gelince sadeleşecek.
 */
export function declineExplanation(response: AskResponse): string {
  const reason = response.decline_reason;
  if (reason && reason !== DECLINE_NOT_COVERED) return reason;
  return "Soruyu farklı kelimelerle sormayı dene. Ders materyalinde bu konuya yetecek bir bölüm bulamadık.";
}

/**
 * Ekran okuyucuya duyurulacak durum cümlesi. Yalnızca durum değişince değişir: akan metnin
 * her parçası duyurulmaz. Hatalar `role="alert"` ile ayrıca duyurulduğu için burada boştur.
 */
export function describeTurn(turn: Turn): string {
  if (turn.failure) return "";
  if (turn.stopped) return "Durduruldu.";
  const { response } = turn;
  if (response) {
    switch (classifyResponse(response)) {
      case "answered":
        return `Cevap hazır. ${response.citations.length} kaynak gösterildi.`;
      case "ai_unavailable":
        return "Yapay zekâ şu an kullanılamıyor; ders materyalindeki ilgili bölüm gösterildi.";
      case "not_generated":
        return "Cevap hazırlanamadı.";
      case "out_of_scope":
        return "Bu soru için ders materyalinde yeterli bilgi bulunamadı.";
    }
  }
  if (turn.streamText) return "Cevap yazılıyor.";
  if (turn.hits) return "İlgili bölümler bulundu, cevap hazırlanıyor.";
  return "Ders materyalinde aranıyor.";
}

/**
 * İstek ya da akış hatasını öğrenciye gösterilecek hataya çevirir.
 * - Ağ hatası, sunucu hatası (5xx) ve yarıda kesilen akış: servis erişilemiyor.
 * - Diğer HTTP hataları (4xx): sunucu isteği reddetti; backend'in mesajı gösterilir.
 */
export function classifyFailure(reason: unknown): TutorFailure {
  if (reason instanceof ApiError && reason.kind === "http" && (reason.status ?? 0) < 500) {
    return { kind: "rejected", detail: reason.message };
  }
  return { kind: "unavailable" };
}
