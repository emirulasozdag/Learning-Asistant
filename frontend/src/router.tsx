import { Navigate, createBrowserRouter } from "react-router";

import RequireRole from "./auth/RequireRole";
import AppShell from "./layouts/AppShell";
import AuthLayout from "./layouts/AuthLayout";
import LoginPage from "./pages/auth/LoginPage";
import RegisterPage from "./pages/auth/RegisterPage";
import CourseLayout from "./pages/instructor/CourseLayout";
import { CourseAnalytics, CourseOverview, CourseStudents } from "./pages/instructor/CourseSections";
import InstructorDashboard from "./pages/instructor/InstructorDashboard";
import MaterialsPage from "./pages/instructor/MaterialsPage";
import PracticePage from "./pages/student/PracticePage";
import StudentDashboard from "./pages/student/StudentDashboard";
import TutorIndex from "./pages/student/TutorIndex";
import TutorPage from "./pages/student/TutorPage";
import { NotFound, RootRedirect } from "./pages/system";

/**
 * Uygulama adresleri.
 *   /login, /register
 *   /instructor                          eğitmen ana sayfası
 *   /instructor/courses/:id/{overview|materials|students|analytics}
 *   /student                             öğrenci ana sayfası
 *   /student/courses/:id/tutor           AI Tutor
 *   /student/practice                    pratik
 */
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
        element: <CourseLayout />,
        children: [
          // Genel bakış geliştirilene kadar ders, materyallerle açılır.
          { index: true, element: <Navigate to="materials" replace /> },
          { path: "overview", element: <CourseOverview /> },
          { path: "materials", element: <MaterialsPage /> },
          { path: "students", element: <CourseStudents /> },
          { path: "analytics", element: <CourseAnalytics /> },
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
      { path: "courses/:courseId/tutor", element: <TutorPage /> },
      { path: "practice", element: <PracticePage /> },
    ],
  },
  { path: "*", element: <NotFound /> },
]);
