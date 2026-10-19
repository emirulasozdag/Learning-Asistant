import { useOutletContext } from "react-router";

import type { DocumentOut } from "../../api/types";
import type { Course } from "../../services/courseService";

/** Ders iskeletinin (CourseShell) bölüm sayfalarına verdiği ortak veri. */
export interface CourseOutlet {
  course: Course;
  /** Dersin dokümanları; `null` = yükleniyor. */
  documents: DocumentOut[] | null;
  documentsFailed: boolean;
  /** Yükleme ya da silme sonrası listeyi (ve sağ paneli) tazeler. */
  reloadDocuments: () => void;
}

export function useCourseOutlet(): CourseOutlet {
  return useOutletContext<CourseOutlet>();
}
