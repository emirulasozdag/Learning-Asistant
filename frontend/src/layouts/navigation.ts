import {
  LayoutDashboard,
  ListChecks,
  MessageSquareText,
  type LucideIcon,
} from "lucide-react";

import type { Role } from "../services/authService";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Alt adreslerde de etkin sayılsın mı? */
  end?: boolean;
}

/** Rol başına ana menü. Dersler, menünün altında ayrıca listelenir. */
export const NAVIGATION: Record<Role, NavItem[]> = {
  instructor: [{ to: "/instructor", label: "Genel bakış", icon: LayoutDashboard, end: true }],
  student: [
    { to: "/student", label: "Ana sayfa", icon: LayoutDashboard, end: true },
    { to: "/student/tutor", label: "AI Tutor", icon: MessageSquareText },
    { to: "/student/practice", label: "Pratik", icon: ListChecks },
  ],
};

/** Bir dersin, role göre açılacağı sayfa. */
export function coursePath(role: Role, courseId: number): string {
  return role === "instructor"
    ? `/instructor/courses/${courseId}`
    : `/student/courses/${courseId}/tutor`;
}

export const ROLE_LABELS: Record<Role, string> = {
  instructor: "Eğitmen",
  student: "Öğrenci",
};
