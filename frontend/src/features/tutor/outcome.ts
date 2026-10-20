import { ApiError } from "../../api/client";
import type { AskResponse } from "../../api/types";
import type { TutorFailure, TutorTurn, Turn } from "./types";

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

// Backend'in "materyalde yok" sabit cümlesi; öğrenciye yerine sade bir yönlendirme gösterilir.
const DECLINE_NOT_COVERED =
  "Bu konu ders materyalinde yer almıyor; cevap uydurmamak için yanıt verilmedi.";

/**
 * Backend cevabını öğrenciye gösterilecek türe çevirir; backend'in `outcome` alanını kullanır.
 * - provider_failure ya da LLM'siz mod (extractive): yapay zekâ yok, ilgili bölüm gösterildi
 * - unsupported / model_refusal: kaynak bulundu ama dayanaklı cevap üretilemedi
 * - insufficient_evidence: soru için materyalde yeterli bilgi yok
 */
export function classifyResponse(response: AskResponse): ResponseOutcome {
  switch (response.outcome) {
    case "answered":
      return response.mode === "extractive" ? "ai_unavailable" : "answered";
    case "provider_failure":
      return "ai_unavailable";
    case "unsupported":
    case "model_refusal":
      return "not_generated";
    case "insufficient_evidence":
      return "out_of_scope";
  }
}

/**
 * Kapsam dışı retin öğrenciye gösterilecek açıklaması. Backend'in sabit cümlesi kesin bir
 * iddia ("yer almıyor") içerdiği için yerine sade bir yönlendirme gelir; modelin kendi yazdığı
 * eksik-bilgi cümlesi olduğu gibi gösterilir.
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

/** AI Tutor turu için ekran okuyucu duyurusu: son içerik bloğuna göre. */
export function describeTutorTurn(turn: TutorTurn): string {
  if (turn.failure) return "";
  if (turn.stopped) return "Durduruldu.";
  const segments = turn.segments.filter((s) => s.block?.type !== "follow_ups");
  const last = segments[segments.length - 1];
  if (!last) return turn.status ?? "Mesajın inceleniyor.";
  const { block } = last;
  if (!block) {
    if (last.tool === "answer_from_course") {
      return describeTurn({ id: turn.id, question: turn.question, hits: last.hits, streamText: last.streamText });
    }
    return turn.status ?? "Cevap hazırlanıyor.";
  }
  switch (block.type) {
    case "course_answer":
      return describeTurn({ id: turn.id, question: turn.question, streamText: "", response: block.response });
    case "general_explanation":
      return "Genel bilgi açıklaması hazır; ders materyalinden değildir.";
    case "practice":
      return "Pratik sorusu hazır.";
    case "clarification":
      return `Netleştirme sorusu: ${block.question}`;
    case "notice":
      return block.text;
    default:
      return "";
  }
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
