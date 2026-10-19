import type { CourseInfo, CourseLevel } from "../../api/types";

export type CourseInfoDraft = { [K in keyof CourseInfo]: string };

export const EMPTY_INFO_DRAFT: CourseInfoDraft = {
  instructor_name: "",
  term: "",
  level: "",
  department: "",
  description: "",
};

export function draftFrom(info: CourseInfo): CourseInfoDraft {
  return {
    instructor_name: info.instructor_name ?? "",
    term: info.term ?? "",
    level: info.level ?? "",
    department: info.department ?? "",
    description: info.description ?? "",
  };
}

/** Formdaki metinleri API'ye uygun hale getirir: boş alan `null` olur. */
export function infoFromDraft(draft: CourseInfoDraft): CourseInfo {
  const text = (value: string) => value.trim() || null;
  return {
    instructor_name: text(draft.instructor_name),
    term: text(draft.term),
    level: (draft.level || null) as CourseLevel | null,
    department: text(draft.department),
    description: text(draft.description),
  };
}
