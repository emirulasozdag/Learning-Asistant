import type { AskResponse, RetrievalHit } from "../../api/types";

/**
 * Sorunun cevaplanamamasının nedeni.
 * - "unavailable": servise ulaşılamadı ya da bağlantı koptu.
 * - "temporary": cevap üretilirken sunucuda geçici bir sorun oluştu (akıştaki `error` olayı).
 * - "rejected": sunucu isteği reddetti; `detail` backend'in mesajı.
 */
export interface TutorFailure {
  kind: "unavailable" | "temporary" | "rejected";
  detail?: string;
}

/** Sohbette bir soru ve (gelmekte olan ya da gelmiş) cevabı. */
export interface Turn {
  id: string;
  question: string;
  /** Aramanın getirdiği parçalar (cevap yazılmadan önce gelir). */
  hits?: RetrievalHit[];
  /** Model yazarken biriken metin. */
  streamText: string;
  response?: AskResponse;
  failure?: TutorFailure;
  /** Öğrenci "Durdur"a bastı; cevap tamamlanmadı. */
  stopped?: boolean;
}

export interface SelectSourceProps {
  selectedSourceId: string | null;
  onSelectSource: (sourceId: string) => void;
}
