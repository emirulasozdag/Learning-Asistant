/**
 * Dersler ve materyaller. Ders listesi, oluşturma ve materyal işlemleri GERÇEK API;
 * öğrenci/soru sayıları şimdilik mock (öğrenme kaydı backend'i henüz yok).
 */
import { api } from "../api/client";
import type { CourseCreate, CourseSummary, DocumentOut, MaterialType } from "../api/types";
import { COURSE_STATS, DEFAULT_COURSE_STATS, type CourseStats } from "../mock/courseStats";

export interface Course extends CourseSummary {
  stats: CourseStats;
}

function withStats(course: CourseSummary): Course {
  return { ...course, stats: COURSE_STATS[course.code] ?? DEFAULT_COURSE_STATS };
}

export const courseService = {
  async list(): Promise<Course[]> {
    return (await api.courses()).map(withStats);
  },

  async get(courseId: number): Promise<Course | null> {
    return (await courseService.list()).find((course) => course.id === courseId) ?? null;
  },

  async create(input: CourseCreate): Promise<Course> {
    return withStats(await api.createCourse(input));
  },

  materials(courseId: number): Promise<DocumentOut[]> {
    return api.materials(courseId);
  },

  uploadMaterial(courseId: number, type: MaterialType, file: File): Promise<DocumentOut> {
    return api.uploadMaterial(courseId, type, file);
  },

  deleteMaterial(documentId: number): Promise<void> {
    return api.deleteDocument(documentId);
  },

  chunks(documentId: number) {
    return api.documentChunks(documentId);
  },
};

/** Dosya adından materyal türü tahmini (yükleme sonrası değiştirilebilir hale getirilecek). */
export function guessMaterialType(filename: string): MaterialType {
  const name = filename.toLocaleLowerCase("tr");
  if (name.endsWith(".pptx") || /slayt|slide|sunum/.test(name)) return "slides";
  if (/sınav|sinav|midterm|final|vize|exam|quiz/.test(name)) return "past_exam";
  if (/kitap|book|chapter|bölüm/.test(name)) return "textbook";
  return "notes";
}
