import { BarChart3, LayoutDashboard, Users } from "lucide-react";
import { Link, useParams } from "react-router";

import { buttonClasses } from "../../ui/buttonStyles";
import UpcomingPage from "../UpcomingPage";

/*
 * Ders sekmelerinden henüz yapılmamış olanlar (ekip görevi: docs/UI_GOREVLERI.md).
 * Hazır bileşenler: src/ui/*, veri: src/services/dashboardService.ts.
 */

export function CourseOverview() {
  const { courseId } = useParams();
  return (
    <UpcomingPage
      icon={LayoutDashboard}
      title="Ders özeti geliştiriliyor"
      description="Bu hafta en çok sorulan konular, materyal kapsamı ve son öğrenci soruları burada yer alacak."
      action={
        <Link to={`/instructor/courses/${courseId}/materials`} className={buttonClasses("secondary")}>
          Materyallere git
        </Link>
      }
    />
  );
}

export function CourseStudents() {
  return (
    <UpcomingPage
      icon={Users}
      title="Öğrenci listesi geliştiriliyor"
      description="Kayıtlı öğrenciler, her öğrencinin soru ve pratik etkinliği burada görünecek."
    />
  );
}

export function CourseAnalytics() {
  return (
    <UpcomingPage
      icon={BarChart3}
      title="Analitik geliştiriliyor"
      description="Sık yapılan hatalar, cevaplanamayan sorular ve materyalin hangi bölümlerinin işe yaradığı burada görünecek."
    />
  );
}
