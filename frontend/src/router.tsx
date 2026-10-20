import { Navigate, createBrowserRouter } from "react-router";

import RequireRole from "./auth/RequireRole";
import AppShell from "./layouts/AppShell";
import AuthLayout from "./layouts/AuthLayout";
import { MATERIAL_SECTIONS } from "./features/courses/sections";
import CourseShell from "./layouts/CourseShell";
import CalendarPage from "./pages/course/CalendarPage";
import CourseOverview from "./pages/course/CourseOverview";
import CourseSectionPage from "./pages/course/CourseSectionPage";
import SyllabusPage from "./pages/course/SyllabusPage";
import LoginPage from "./pages/auth/LoginPage";
import RegisterPage from "./pages/auth/RegisterPage";
import CourseActivityPage from "./pages/instructor/CourseActivityPage";
import InstructorDashboard from "./pages/instructor/InstructorDashboard";
import MaterialsPage from "./pages/instructor/MaterialsPage";
import CourseMaterialsPage from "./pages/student/CourseMaterialsPage";
import StudentDashboard from "./pages/student/StudentDashboard";
import TutorIndex from "./pages/student/TutorIndex";
import TutorPage from "./pages/student/TutorPage";
import { NotFound, RootRedirect } from "./pages/system";

/**
 * Uygulama adresleri.
 *   /login, /register
 *   /instructor                              eğitmen: derslerim
 *   /instructor/courses/:id                  ders genel bakış
 *   /instructor/courses/:id/materials        materyaller (bilgi tabanı, yükleme)
 *   /instructor/courses/:id/activity         etkinlik ve analitik
 *   /student                                 öğrenci: derslerim
 *   /student/courses/:id                     ders genel bakış
 *   /student/courses/:id/materials           ders materyalleri
 *   /student/courses/:id/tutor               AI Tutor
 * Her iki rolde ders içeriği (OCW düzeni):
 *   …/courses/:id/syllabus, /calendar        izlence, takvim
 *   …/courses/:id/videos, /lecture-notes, /quizzes, /practice-problems, /assignments
 */

/** İki rolde ortak ders içeriği bölümleri. */
const contentRoutes = [
  { path: "syllabus", element: <SyllabusPage /> },
  { path: "calendar", element: <CalendarPage /> },
  ...MATERIAL_SECTIONS.map((section) => ({
    path: section.path,
    element: <CourseSectionPage key={section.path} section={section} />,
  })),
];
export const router = createBrowserRouter([
  { path: "/", element: <RootRedirect /> },
  {
    element: <AuthLayout />,
    children: [
      { path: "/login", element: <LoginPage /> },
      { path: "/register", element: <RegisterPage /> },
    ],
  },
  {
    path: "/instructor",
    element: (
      <RequireRole role="instructor">
        <AppShell />
      </RequireRole>
    ),
    children: [
      { index: true, element: <InstructorDashboard /> },
      {
        path: "courses/:courseId",
        element: <CourseShell />,
        children: [
          { index: true, element: <CourseOverview /> },
          { path: "materials", element: <MaterialsPage /> },
          { path: "activity", element: <CourseActivityPage /> },
          ...contentRoutes,
          // Eski sekme adresleri (yer imleri) genel bakışa düşer.
          { path: "*", element: <Navigate to=".." relative="path" replace /> },
        ],
      },
    ],
  },
  {
    path: "/student",
    element: (
      <RequireRole role="student">
        <AppShell />
      </RequireRole>
    ),
    children: [
      { index: true, element: <StudentDashboard /> },
      { path: "tutor", element: <TutorIndex /> },
      { path: "practice", element: <Navigate to="/student" replace /> },
      {
        path: "courses/:courseId",
        element: <CourseShell />,
        children: [
          { index: true, element: <CourseOverview /> },
          { path: "materials", element: <CourseMaterialsPage /> },
          { path: "tutor", element: <TutorPage /> },
          ...contentRoutes,
        ],
      },
    ],
  },
  { path: "*", element: <NotFound /> },
]);
