import { useEffect, useState } from "react";

import type { CourseActivity } from "../../api/types";
import type { Course } from "../../services/courseService";
import { instructorService } from "../../services/instructorService";

/** Ders başına etkinlik; `undefined` = yükleniyor, `null` = alınamadı. */
export type CourseActivities = Record<number, CourseActivity | null | undefined>;

/** Eğitmenin derslerinin etkinliklerini paralel getirir; biri başarısız olursa diğerleri etkilenmez. */
export function useCourseActivities(courses: Course[]): CourseActivities {
  const [activities, setActivities] = useState<CourseActivities>({});
  const key = courses.map((course) => course.id).join(",");

  useEffect(() => {
    const controller = new AbortController();
    for (const id of key ? key.split(",").map(Number) : []) {
      instructorService
        .activity(id, controller.signal)
        .then((activity) => {
          if (!controller.signal.aborted) setActivities((map) => ({ ...map, [id]: activity }));
        })
        .catch(() => {
          if (!controller.signal.aborted) setActivities((map) => ({ ...map, [id]: null }));
        });
    }
    return () => controller.abort();
  }, [key]);

  return activities;
}
