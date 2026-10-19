import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";

import { courseService, type Course } from "../../services/courseService";
import CreateCourseDialog from "./CreateCourseDialog";
import { CoursesContext } from "./context";

/** Uygulama boyunca paylaşılan ders listesi (sidebar, dashboard, ders sayfaları). */
export default function CoursesProvider({ children }: { children: ReactNode }) {
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();

  const refresh = useCallback(async () => {
    try {
      setCourses(await courseService.list());
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    courseService
      .list()
      .then((list) => {
        if (!cancelled) setCourses(list);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const add = useCallback((course: Course) => {
    setCourses((list) => [...list, course].sort((a, b) => a.code.localeCompare(b.code)));
  }, []);

  const replace = useCallback((course: Course) => {
    setCourses((list) => list.map((item) => (item.id === course.id ? course : item)));
  }, []);

  const value = useMemo(
    () => ({ courses, loading, error, refresh, add, replace, openCreate: () => setCreating(true) }),
    [courses, loading, error, refresh, add, replace],
  );

  return (
    <CoursesContext value={value}>
      {children}
      <CreateCourseDialog
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(course) => {
          add(course);
          setCreating(false);
          navigate(`/instructor/courses/${course.id}`);
        }}
      />
    </CoursesContext>
  );
}
