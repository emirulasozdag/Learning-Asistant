import { createContext } from "react";

/** Kenar çubuğundaki "Bu sohbet" listesinin bir satırı. */
export interface ConversationEntry {
  id: string;
  question: string;
  /** Cevabın kısa durumu: kenar çubuğunda küçük işaret olarak gösterilir. */
  state: "pending" | "answered" | "declined" | "failed";
}

export interface StudioContextValue {
  entries: ConversationEntry[];
  activeId: string | null;
  /** Sayfa, sohbetini kenar çubuğuna bildirir. */
  publish: (entries: ConversationEntry[], activeId: string | null) => void;
  /** Kenar çubuğunda bir soruya tıklanınca sayfaya iletilir. */
  select: (id: string) => void;
  /** Sayfa, seçim isteklerini dinlemek için kendi işleyicisini kaydeder. */
  onSelect: (handler: ((id: string) => void) | null) => void;
  /** Komut paletinden gelen soru; sayfa sorup temizler. */
  queuedQuestion: string | null;
  queueQuestion: (question: string | null) => void;
}

export const StudioContext = createContext<StudioContextValue | null>(null);
