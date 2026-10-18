import { BookOpen } from "lucide-react";
import { Navigate } from "react-router";

import { useCourses } from "../../features/courses/context";
import EmptyState from "../../ui/EmptyState";
import { SkeletonRows } from "../../ui/Skeleton";

/** "AI Tutor" menüsü: ilk dersin tutor'una yönlendirir. */
export default function TutorIndex() {
  const { courses, loading } = useCourses();
  if (loading) {
    return (
      <div className="mx-auto max-w-3xl px-6 pt-10">
        <SkeletonRows rows={2} />
      </div>
    );
  }
  if (courses.length === 0) {
    return (
      <EmptyState
        icon={BookOpen}
        title="AI Tutor için bir ders gerekli"
        description="Kayıtlı olduğun bir ders olduğunda burada soru sorabileceksin."
        className="py-24"
      />
    );
  }
  return <Navigate to={`/student/courses/${courses[0].id}/tutor`} replace />;
}
