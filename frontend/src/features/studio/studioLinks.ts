import {
  BarChart3,
  FolderOpen,
  LayoutList,
  MessageSquareText,
  PencilLine,
  Video,
  type LucideIcon,
} from "lucide-react";

export interface StudioLink {
  label: string;
  icon: LucideIcon;
  /** Yoksa öğe henüz kullanılamaz ("yakında"). */
  to?: string;
  end?: boolean;
}

/** Öğrencinin ders araçları; adresler ders sayfasının bölümleridir. */
export function studioLinks(base: string): StudioLink[] {
  return [
    { label: "AI Tutor", icon: MessageSquareText, to: `${base}/tutor` },
    { label: "Ders videoları", icon: Video, to: `${base}/videos` },
    { label: "Pratik", icon: PencilLine, to: `${base}/practice-problems` },
    { label: "Materyaller", icon: FolderOpen, to: `${base}/materials` },
    { label: "Öğrenme kaydım", icon: BarChart3 },
    { label: "Ders sayfası", icon: LayoutList, to: base, end: true },
  ];
}
