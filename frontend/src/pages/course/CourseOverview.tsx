import { MessageSquareText, Pencil, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";

import type { CourseActivity, DocumentOut } from "../../api/types";
import { useAuth } from "../../auth/useAuth";
import CourseInfoDialog from "../../features/courses/CourseInfoDialog";
import { useCourseOutlet } from "../../features/courses/courseOutlet";
import { MATERIAL_LABELS, TYPE_ORDER } from "../../labels";
import { instructorService } from "../../services/instructorService";
import { buttonClasses } from "../../ui/buttonStyles";
import Button from "../../ui/Button";
import PageTitle from "../../ui/PageTitle";
import { SkeletonRows } from "../../ui/Skeleton";
import StatRow from "../../ui/StatRow";
import { Table, TD, TH, THead, TR } from "../../ui/Table";

/** Dersin ana sayfası (iki rol): ders hakkında, materyal özeti ve role göre bir sonraki adım. */
export default function CourseOverview() {
  const { user } = useAuth();
  const { course, documents, documentsFailed } = useCourseOutlet();
  const instructor = user?.role === "instructor";
  const [editing, setEditing] = useState(false);
  const base = `/${user?.role ?? "student"}/courses/${course.id}`;

  return (
    <div className="flex flex-col gap-10">
      <section>
        <PageTitle
          title="Ders hakkında"
          actions={
            instructor && (
              <Button icon={Pencil} onClick={() => setEditing(true)}>
                Ders bilgilerini düzenle
              </Button>
            )
          }
        />
        {course.description ? (
          <p className="max-w-3xl text-md leading-relaxed whitespace-pre-line text-ink">{course.description}</p>
        ) : (
          <p className="text-md text-graphite">
            {instructor
              ? "Dersin açıklaması henüz eklenmedi. Öğrencilerin dersi tanıması için kapsamı ve ön koşulları yaz."
              : "Bu dersin açıklaması henüz eklenmedi."}
          </p>
        )}
      </section>

      {!instructor && (
        <section className="flex flex-col gap-4 rounded-panel border border-line border-l-4 border-l-accent bg-surface px-6 py-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-bold text-ink">AI Tutor'a soru sor</h2>
            <p className="mt-1 text-base text-graphite">
              Cevaplar bu dersin materyaline dayanır ve dayandığı sayfayla birlikte gelir.
            </p>
          </div>
          <Link to={`${base}/tutor`} className={buttonClasses("primary", "lg")}>
            <MessageSquareText size={18} aria-hidden />
            AI Tutor'u aç
          </Link>
        </section>
      )}

      <section>
        <PageTitle
          title="Bu dersin materyali"
          actions={
            <Link to={`${base}/materials`} className="link text-base">
              {instructor ? "Materyalleri yönet" : "Tüm materyaller"}
            </Link>
          }
        />
        <MaterialSummary documents={documents} failed={documentsFailed} instructor={instructor} base={base} />
      </section>

      {instructor && <ActivitySummary courseId={course.id} base={base} />}

      {instructor && editing && (
        <CourseInfoDialog course={course} open onClose={() => setEditing(false)} />
      )}
    </div>
  );
}

function MaterialSummary({
  documents,
  failed,
  instructor,
  base,
}: {
  documents: DocumentOut[] | null;
  failed: boolean;
  instructor: boolean;
  base: string;
}) {
  if (failed) return <p className="text-md text-danger">Materyal listesine şu an ulaşılamıyor.</p>;
  if (documents === null) return <SkeletonRows rows={2} />;
  if (documents.length === 0) {
    return instructor ? (
      <div className="flex flex-col items-start gap-3">
        <p className="text-md text-graphite">
          Henüz materyal yok; öğrenciler bu derste AI Tutor'a soru soramaz.
        </p>
        <Link to={`${base}/materials`} className={buttonClasses("primary")}>
          <Upload size={16} aria-hidden />
          Materyal yükle
        </Link>
      </div>
    ) : (
      <p className="text-md text-graphite">Eğitmen henüz materyal yüklemedi.</p>
    );
  }
  const rows = TYPE_ORDER.map((type) => {
    const ofType = documents.filter((d) => d.material_type === type);
    return { type, count: ofType.length, pages: ofType.reduce((sum, d) => sum + d.page_count, 0) };
  }).filter((row) => row.count > 0);
  return (
    <Table label="Materyal türleri">
      <THead>
        <tr>
          <TH>Tür</TH>
          <TH className="text-right">Doküman</TH>
          <TH className="text-right">Sayfa</TH>
        </tr>
      </THead>
      <tbody>
        {rows.map((row) => (
          <TR key={row.type}>
            <TD className="font-medium text-ink">{MATERIAL_LABELS[row.type]}</TD>
            <TD className="text-right tabular-nums">{row.count}</TD>
            <TD className="text-right tabular-nums">{row.pages}</TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}

/** Eğitmen için son etkinlik özeti; ayrıntısı "Etkinlik ve analitik" bölümünde. */
function ActivitySummary({ courseId, base }: { courseId: number; base: string }) {
  const [activity, setActivity] = useState<CourseActivity | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    instructorService
      .activity(courseId, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setActivity(data);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [courseId]);

  return (
    <section>
      <PageTitle
        title="Öğrenci etkinliği"
        actions={
          <Link to={`${base}/activity`} className="link text-base">
            Etkinlik ve analitik
          </Link>
        }
      />
      {failed ? (
        <p className="text-md text-danger">Etkinlik bilgisine şu an ulaşılamıyor.</p>
      ) : activity === null ? (
        <SkeletonRows rows={1} />
      ) : activity.questions === 0 ? (
        <p className="text-md text-graphite">Öğrenciler bu derste henüz soru sormadı.</p>
      ) : (
        <StatRow
          stats={[
            { label: "Soru", value: activity.questions },
            { label: "Kaynaklı cevap", value: activity.answered },
            { label: "Materyalde yok", value: activity.not_covered },
          ]}
        />
      )}
    </section>
  );
}
