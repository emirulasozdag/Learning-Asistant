import type { AskResponse, RetrievalHit, TutorBlock } from "../../api/types";

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

/** Bir kaynaklı cevabın durumu: arıyor → yazıyor → doğrulanmış cevap / ret / hata. */
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
  /** Sorunun gönderildiği ve doğrulanmış cevabın geldiği an (ms); cevap süresi için. */
  startedAt?: number;
  finishedAt?: number;
}

export interface SelectSourceProps {
  selectedSourceId: string | null;
  onSelectSource: (sourceId: string) => void;
}

/**
 * AI Tutor turunda bir blok: araç çalışırken taslak, sonra doğrulanmış blok (CONTRACTS.md §9).
 * `tool` bloğu üreten araçtır; blok gelmeden önce taslağın ne olduğunu söyler.
 */
export interface Segment {
  tool: string;
  hits?: RetrievalHit[];
  streamText: string;
  block?: TutorBlock;
}

/** Sohbette öğrencinin bir mesajı ve tutor'un (gelmekte olan ya da gelmiş) blokları. */
export interface TutorTurn {
  id: string;
  question: string;
  /** Şu an çalışan araç ve arayüz etiketi ("Ders materyalinde aranıyor…"). */
  tool?: string;
  status?: string;
  segments: Segment[];
  done?: boolean;
  failure?: TutorFailure;
  stopped?: boolean;
  /** Mesajın gönderildiği ve turun bittiği an (ms); cevap süresi için. */
  startedAt?: number;
  finishedAt?: number;
}
