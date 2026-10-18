import { createContext, useContext } from "react";

import type { Course } from "../../services/courseService";

export interface CoursesContextValue {
  courses: Course[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  add: (course: Course) => void;
  /** Ders oluşturma diyaloğunu açar (sidebar ve dashboard'dan). */
  openCreate: () => void;
}

export const CoursesContext = createContext<CoursesContextValue | null>(null);

export function useCourses(): CoursesContextValue {
  const context = useContext(CoursesContext);
  if (!context) throw new Error("useCourses, CoursesProvider içinde kullanılmalı");
  return context;
}

export function useCourse(courseId: number | null): Course | null {
  const { courses } = useCourses();
  return courses.find((course) => course.id === courseId) ?? null;
}
