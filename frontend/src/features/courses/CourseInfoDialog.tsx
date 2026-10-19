import { useState, type FormEvent } from "react";

import { courseService, type Course } from "../../services/courseService";
import Button from "../../ui/Button";
import Dialog from "../../ui/Dialog";
import { useToast } from "../../ui/toast/context";
import CourseInfoFields from "./CourseInfoFields";
import { draftFrom, infoFromDraft } from "./courseInfoDraft";
import { useCourses } from "./context";

/** Eğitmenin ders bilgisini (eğitmen, dönem, seviye, bölüm, açıklama) düzenlediği pencere. */
export default function CourseInfoDialog({
  course,
  open,
  onClose,
}: {
  course: Course;
  open: boolean;
  onClose: () => void;
}) {
  const { replace } = useCourses();
  const toast = useToast();
  const [draft, setDraft] = useState(() => draftFrom(course));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      replace(await courseService.update(course.id, infoFromDraft(draft)));
      toast.show({ tone: "success", title: "Ders bilgileri kaydedildi" });
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      size="lg"
      title="Ders bilgilerini düzenle"
      description={`${course.code} ${course.name}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Vazgeç
          </Button>
          <Button variant="primary" type="submit" form="course-info" loading={saving}>
            Kaydet
          </Button>
        </>
      }
    >
      <form id="course-info" onSubmit={submit}>
        <CourseInfoFields draft={draft} onChange={setDraft} />
        {error && (
          <p role="alert" className="mt-3 text-base text-danger">
            {error}
          </p>
        )}
      </form>
    </Dialog>
  );
}
