import { ArrowRight, ChevronDown } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import type { Course } from "../../services/courseService";

/**
 * Ana sayfadaki büyük soru kutusu: ders seç, sorunu yaz, AI Tutor'da cevabı al.
 * Soru, tutor sayfasına `?q=` ile taşınır ve orada bir kez sorulur.
 */
export default function AskBox({ courses }: { courses: Course[] }) {
  const navigate = useNavigate();
  const [courseId, setCourseId] = useState<number>(courses[0]?.id ?? 0);
  const [question, setQuestion] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!courseId) return;
    const query = text ? `?q=${encodeURIComponent(text)}` : "";
    navigate(`/student/courses/${courseId}/tutor${query}`);
  }

  return (
    <form
      onSubmit={submit}
      className="flex flex-col overflow-hidden rounded-panel border border-line-strong bg-surface shadow-card focus-within:border-accent focus-within:ring-3 focus-within:ring-accent/12 sm:flex-row"
    >
      <label htmlFor="home-question" className="sr-only">
        Sorun
      </label>
      <input
        id="home-question"
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        placeholder="Ders notlarına bir soru sor…"
        className="h-14 w-full min-w-0 shrink-0 bg-transparent px-5 text-md text-ink placeholder:text-faint focus:outline-none sm:w-auto sm:flex-1"
      />
      <div className="flex border-t border-line sm:border-t-0 sm:border-l">
        <label htmlFor="home-course" className="sr-only">
          Ders
        </label>
        <div className="relative flex-1 sm:flex-none">
          <select
            id="home-course"
            value={courseId}
            onChange={(event) => setCourseId(Number(event.target.value))}
            className="h-14 w-full appearance-none truncate bg-transparent pr-9 pl-4 text-base font-medium text-ink-2 focus:outline-none sm:w-64"
          >
            {courses.map((course) => (
              <option key={course.id} value={course.id}>
                {course.name}
              </option>
            ))}
          </select>
          <ChevronDown
            size={16}
            aria-hidden
            className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-graphite"
          />
        </div>
        <button
          type="submit"
          aria-label="Sor"
          className="flex h-14 w-14 shrink-0 items-center justify-center bg-accent text-on-accent transition-colors hover:bg-accent-hover"
        >
          <ArrowRight size={20} aria-hidden />
        </button>
      </div>
    </form>
  );
}
