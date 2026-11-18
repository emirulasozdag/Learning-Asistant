import {
  BarChart3,
  CalendarDays,
  ClipboardCheck,
  ClipboardList,
  FileText,
  FolderOpen,
  LayoutList,
  ListChecks,
  MessageSquareText,
  NotebookText,
  PencilLine,
  Video,
  type LucideIcon,
} from "lucide-react";

import type { MaterialType } from "../../api/types";
import type { SectionLink } from "../../ui/SectionNav";

/** Materyal türlerine göre dolan ders bölümleri (OCW sol menüsü: Lecture Notes, Quizzes…). */
export interface MaterialSection {
  /** Adres parçası: `/student/courses/1/lecture-notes`. */
  path: string;
  label: string;
  /** Sayfa başlığının altındaki kısa açıklama. */
  description: string;
  icon: LucideIcon;
  types: MaterialType[];
  /** Bölüm boşken gösterilen metin. */
  empty: string;
}

export const MATERIAL_SECTIONS: MaterialSection[] = [
  {
    path: "videos",
    label: "Ders videoları",
    description: "Ders kayıtları ve transkriptleri.",
    icon: Video,
    types: ["video", "transcript"],
    empty: "Bu derse henüz video eklenmedi.",
  },
  {
    path: "lecture-notes",
    label: "Ders notları",
    description: "Ders ve recitation notları, slaytlar ve ders kitabı bölümleri.",
    icon: NotebookText,
    types: ["notes", "slides", "textbook"],
    empty: "Bu derse henüz ders notu eklenmedi.",
  },
  {
    path: "quizzes",
    label: "Sınavlar",
    description: "Geçmiş sınavlar, sınav hazırlık setleri ve çözümleri.",
    icon: ClipboardCheck,
    types: ["past_exam"],
    empty: "Bu derse henüz sınav eklenmedi.",
  },
  {
    path: "practice-problems",
    label: "Pratik problemler",
    description: "Problem oturumlarının soruları ve çözümleri.",
    icon: PencilLine,
    types: ["practice_problem"],
    empty: "Bu derse henüz pratik problem eklenmedi.",
  },
  {
    path: "assignments",
    label: "Ödevler",
    description: "Problem setleri ve çözümleri.",
    icon: ClipboardList,
    types: ["assignment"],
    empty: "Bu derse henüz ödev eklenmedi.",
  },
];

/** Dersin araçları: rolün ana işleri (üstte). */
export function toolSections(role: "student" | "instructor", base: string): SectionLink[] {
  return role === "instructor"
    ? [
        { to: base, label: "Genel bakış", icon: LayoutList, end: true },
        { to: `${base}/materials`, label: "Materyaller", icon: FolderOpen },
        { to: `${base}/activity`, label: "Etkinlik ve analitik", icon: BarChart3 },
        { to: `${base}/review`, label: "İnceleme ve sık hatalar", icon: ListChecks },
      ]
    : [
        { to: base, label: "Genel bakış", icon: LayoutList, end: true },
        { to: `${base}/tutor`, label: "AI Tutor", icon: MessageSquareText },
        { to: `${base}/learning`, label: "Öğrenme kaydım", icon: BarChart3 },
      ];
}

/** Dersin içeriği (OCW düzeni): izlence, takvim ve materyal bölümleri. */
export function contentSections(role: "student" | "instructor", base: string): SectionLink[] {
  const links: SectionLink[] = [
    { to: `${base}/syllabus`, label: "İzlence", icon: FileText },
    { to: `${base}/calendar`, label: "Takvim", icon: CalendarDays },
    ...MATERIAL_SECTIONS.map(({ path, label, icon }) => ({ to: `${base}/${path}`, label, icon })),
  ];
  if (role === "student") {
    links.push({ to: `${base}/materials`, label: "Tüm materyaller", icon: FolderOpen });
  }
  return links;
}

/**
 * Konum şeridinin (Topbar) bölüm adları: menüyle aynı etiketler, tek kaynak (#103).
 * Adresin son parçası → etiket.
 */
export const SECTION_LABELS: Record<string, string> = {
  tutor: "AI Tutor",
  learning: "Öğrenme kaydım",
  materials: "Materyaller",
  activity: "Etkinlik ve analitik",
  review: "İnceleme ve sık hatalar",
  syllabus: "İzlence",
  calendar: "Takvim",
  account: "Hesabım",
  ...Object.fromEntries(MATERIAL_SECTIONS.map((section) => [section.path, section.label])),
};
