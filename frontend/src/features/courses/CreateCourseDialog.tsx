import { useState, type FormEvent } from "react";

import { courseService, type Course } from "../../services/courseService";
import Button from "../../ui/Button";
import Dialog from "../../ui/Dialog";
import Field from "../../ui/Field";
import SegmentedControl from "../../ui/SegmentedControl";
import CourseInfoFields from "./CourseInfoFields";
import { EMPTY_INFO_DRAFT, infoFromDraft } from "./courseInfoDraft";

interface CreateCourseDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated: (course: Course) => void;
}

export default function CreateCourseDialog({ open, onClose, onCreated }: CreateCourseDialogProps) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [language, setLanguage] = useState<"tr" | "en">("tr");
  const [info, setInfo] = useState(EMPTY_INFO_DRAFT);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      onCreated(await courseService.create({ code, name, language, ...infoFromDraft(info) }));
      setCode("");
      setName("");
      setInfo(EMPTY_INFO_DRAFT);
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
      title="Ders oluştur"
      description="Her dersin bilgi tabanı ayrıdır; öğrenci soruları yalnızca o dersin materyalinde aranır."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Vazgeç
          </Button>
          <Button variant="primary" type="submit" form="create-course" loading={saving}>
            Dersi oluştur
          </Button>
        </>
      }
    >
      <form id="create-course" onSubmit={submit} className="flex flex-col gap-4">
        <div className="grid grid-cols-[8rem_1fr] gap-3">
          <Field
            label="Ders kodu"
            value={code}
            onChange={(event) => setCode(event.target.value.toLocaleUpperCase("tr"))}
            placeholder="BLM2512"
            required
            minLength={2}
            maxLength={32}
            data-autofocus
          />
          <Field
            label="Ders adı"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Veri Yapıları ve Algoritmalar"
            required
            minLength={2}
          />
        </div>
        <SegmentedControl
          name="course-language"
          label="Materyalin dili"
          value={language}
          onChange={setLanguage}
          options={[
            { value: "tr", label: "Türkçe" },
            { value: "en", label: "İngilizce" },
          ]}
        />
        <div className="border-t border-line pt-4">
          <p className="mb-3 text-sm text-graphite">
            Ders bilgileri öğrencilere ders sayfasında gösterilir. Şimdi boş bırakıp sonra da
            ekleyebilirsin.
          </p>
          <CourseInfoFields draft={info} onChange={setInfo} />
        </div>
        {error && (
          <p role="alert" className="text-base text-danger">
            {error}
          </p>
        )}
      </form>
    </Dialog>
  );
}
