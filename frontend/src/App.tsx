import { useState } from "react";

import CourseSelector from "./features/courses/CourseSelector";
import InstructorPage from "./pages/InstructorPage";
import StudentPage from "./pages/StudentPage";

type View = "student" | "instructor";

const VIEWS: { id: View; label: string }[] = [
  { id: "student", label: "Öğrenci" },
  { id: "instructor", label: "Eğitmen" },
];

export default function App() {
  const [view, setView] = useState<View>("student");

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Interactive Learning Assistant</h1>
          <p className="text-sm text-slate-500">Proje iskeleti — özellikler henüz uygulanmadı.</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <CourseSelector />
          <nav className="flex gap-1 rounded-lg bg-slate-100 p-1">
            {VIEWS.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                onClick={() => setView(id)}
                className={`rounded-md px-3 py-1 text-sm ${
                  view === id ? "bg-white shadow-sm" : "text-slate-600"
                }`}
              >
                {label}
              </button>
            ))}
          </nav>
        </div>
      </header>
      {view === "student" ? <StudentPage /> : <InstructorPage />}
    </div>
  );
}
