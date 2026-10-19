import {
  LayoutDashboard,
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

/** Rol başına üst bar menüsü. Dersin bölümleri ders sayfasının solundadır. */
export const NAVIGATION: Record<Role, NavItem[]> = {
  instructor: [{ to: "/instructor", label: "Derslerim", icon: LayoutDashboard, end: true }],
  student: [
    { to: "/student", label: "Derslerim", icon: LayoutDashboard, end: true },
    { to: "/student/tutor", label: "AI Tutor", icon: MessageSquareText },
  ],
};

/** Bir dersin ana sayfası (genel bakış); bölümler bunun altındadır. */
export function coursePath(role: Role, courseId: number): string {
  return `/${role}/courses/${courseId}`;
}

export const ROLE_LABELS: Record<Role, string> = {
  instructor: "Eğitmen",
  student: "Öğrenci",
};
