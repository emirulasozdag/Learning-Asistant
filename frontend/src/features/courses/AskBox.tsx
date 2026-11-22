import { ArrowRight, ChevronDown } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import type { Course } from "../../services/courseService";
import Button from "../../ui/Button";
import { cx } from "../../ui/cx";
import { inputClasses } from "../../ui/Field";

/** Alan biçimi, karşılama alanına göre daha yüksek: yükseklik, iç boşluk ve yazı boyu burada verilir. */
const askField = inputClasses.replace(/(^|\s)(h-10|px-3|text-base)(?=\s|$)/g, "$1").trim();

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
    <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <label htmlFor="home-question" className="sr-only">
        Sorun
      </label>
      <input
        id="home-question"
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        placeholder="Ders notlarına bir soru sor…"
        className={cx(askField, "h-12 min-w-0 px-4 text-md sm:flex-1")}
      />
      <div className="flex items-center gap-2">
        <label htmlFor="home-course" className="sr-only">
          Ders
        </label>
        <div className="relative min-w-0 flex-1 sm:w-60 sm:flex-none">
          <select
            id="home-course"
            value={courseId}
            onChange={(event) => setCourseId(Number(event.target.value))}
            className={cx(askField, "h-12 appearance-none truncate pr-9 pl-3 text-base font-medium")}
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
        <Button type="submit" variant="primary" size="icon" icon={ArrowRight} aria-label="Sor" />
      </div>
    </form>
  );
}
