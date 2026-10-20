/** Dersler ve materyaller: tamamı gerçek API. */
import { api } from "../api/client";
import type { CourseCreate, CourseSummary, CourseUpdate, DocumentOut, MaterialType } from "../api/types";

export type Course = CourseSummary;

export const courseService = {
  async list(): Promise<Course[]> {
    return api.courses();
  },

  async get(courseId: number): Promise<Course | null> {
    return (await courseService.list()).find((course) => course.id === courseId) ?? null;
  },

  async create(input: CourseCreate): Promise<Course> {
    return api.createCourse(input);
  },

  update(courseId: number, input: CourseUpdate): Promise<Course> {
    return api.updateCourse(courseId, input);
  },

  materials(courseId: number, signal?: AbortSignal): Promise<DocumentOut[]> {
    return api.materials(courseId, signal);
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
  if (name.endsWith(".vtt")) return "video";
  if (name.endsWith(".pptx") || /slayt|slide|sunum/.test(name)) return "slides";
  if (/sınav|sinav|midterm|final|vize|exam|quiz/.test(name)) return "past_exam";
  if (/kitap|book|chapter|bölüm/.test(name)) return "textbook";
  return "notes";
}
