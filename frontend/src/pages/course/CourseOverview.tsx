import { ArrowRight, MessageSquareText, Pencil, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";

import type { CourseActivity, DocumentOut } from "../../api/types";
import { useAuth } from "../../auth/useAuth";
import CourseInfoDialog from "../../features/courses/CourseInfoDialog";
import JoinCodePanel from "../../features/courses/JoinCodePanel";
import { useCourseOutlet } from "../../features/courses/courseOutlet";
import { MATERIAL_LABELS, TYPE_ORDER, materialTotals, totalsHeading } from "../../labels";
import { formatTime } from "../../text";
import { instructorService } from "../../services/instructorService";
import { buttonClasses } from "../../ui/buttonStyles";
import InlineError from "../../ui/InlineError";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import Notice from "../../ui/Notice";
import PageTitle from "../../ui/PageTitle";
import { SkeletonRows } from "../../ui/Skeleton";
import StatRow from "../../ui/StatRow";
import { Table, TD, TH, THead, TR } from "../../ui/Table";

/** Dersin ana sayfası (iki rol): ders hakkında, materyal özeti ve role göre bir sonraki adım. */
export default function CourseOverview() {
  const { user } = useAuth();
  const { course, documents, documentsFailed, reloadDocuments } = useCourseOutlet();
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
        ) : instructor ? (
          <Notice
            action={
              <Button size="sm" icon={Pencil} onClick={() => setEditing(true)}>
                Açıklama ekle
              </Button>
            }
          >
            Dersin açıklaması henüz eklenmedi. Öğrencilerin dersi tanıması için kapsamı ve ön koşulları yaz.
          </Notice>
        ) : (
          <p className="text-md text-graphite">Bu dersin açıklaması henüz eklenmedi.</p>
        )}
      </section>

      {!instructor && (
        <Card
          as="section"
          variant="callout"
          aria-labelledby="tutor-cta-title"
          className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"
        >
          <div>
            <h2 id="tutor-cta-title" className="text-lg font-bold text-ink">
              AI Tutor'a soru sor
            </h2>
            <p className="mt-1 text-base text-graphite">
              Cevaplar bu dersin materyaline dayanır ve dayandığı sayfayla birlikte gelir.
            </p>
          </div>
          <Link to={`${base}/tutor`} className={buttonClasses("primary", "lg")}>
            <MessageSquareText size={18} aria-hidden />
            AI Tutor'u aç
          </Link>
        </Card>
      )}

      <section>
        <PageTitle
          level={2}
          title="Bu dersin materyali"
          actions={
            <Link to={`${base}/materials`} className={buttonClasses("secondary", "sm")}>
              {instructor ? "Materyalleri yönet" : "Tüm materyaller"}
              <ArrowRight size={14} aria-hidden className="opacity-70" />
            </Link>
          }
        />
        <MaterialSummary
          documents={documents}
          failed={documentsFailed}
          onRetry={reloadDocuments}
          instructor={instructor}
          base={base}
        />
      </section>

      {course.role === "instructor" && <JoinCodePanel courseId={course.id} />}

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
  onRetry,
  instructor,
  base,
}: {
  documents: DocumentOut[] | null;
  failed: boolean;
  onRetry: () => void;
  instructor: boolean;
  base: string;
}) {
  if (failed) return <InlineError message="Materyal listesine şu an ulaşılamıyor." onRetry={onRetry} />;
  if (documents === null) return <SkeletonRows rows={2} />;
  if (documents.length === 0) {
    return instructor ? (
      <Notice
        tone="warning"
        action={
          <Link to={`${base}/materials`} className={buttonClasses("primary", "sm")}>
            <Upload size={14} aria-hidden />
            Materyal yükle
          </Link>
        }
      >
        Henüz materyal yok; öğrenciler bu derste AI Tutor'a soru soramaz.
      </Notice>
    ) : (
      <p className="text-md text-graphite">Eğitmen henüz materyal yüklemedi.</p>
    );
  }
  const rows = TYPE_ORDER.map((type) => {
    const ofType = documents.filter((d) => d.material_type === type);
    return { type, count: ofType.length, totals: materialTotals(ofType) };
  }).filter((row) => row.count > 0);
  return (
    <Table label="Materyal türleri">
      <THead>
        <tr>
          <TH>Tür</TH>
          <TH className="text-right">Doküman</TH>
          <TH className="text-right">{totalsHeading(materialTotals(documents))}</TH>
        </tr>
      </THead>
      <tbody>
        {rows.map((row) => (
          <TR key={row.type}>
            <TD className="font-medium text-ink">{MATERIAL_LABELS[row.type]}</TD>
            <TD className="text-right tabular-nums">{row.count}</TD>
            <TD className="text-right tabular-nums">{row.totals.hasVideo ? formatTime(row.totals.videoSeconds) : row.totals.pages}</TD>
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
  const [attempt, setAttempt] = useState(0);

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
  }, [courseId, attempt]);

  function retry() {
    setFailed(false);
    setActivity(null);
    setAttempt((value) => value + 1);
  }

  return (
    <section>
      <PageTitle
        level={2}
        title="Öğrenci etkinliği"
        actions={
          <Link to={`${base}/activity`} className={buttonClasses("secondary", "sm")}>
            Etkinlik ve analitik
            <ArrowRight size={14} aria-hidden className="opacity-70" />
          </Link>
        }
      />
      {failed ? (
        <InlineError message="Etkinlik bilgisine şu an ulaşılamıyor." onRetry={retry} />
      ) : activity === null ? (
        <SkeletonRows rows={1} />
      ) : activity.questions === 0 ? (
        // Sıfır "hiç soru yok" demek değildir: kayıt ve en az üç öğrenci kuralı (ADR-4, #105).
        <p className="text-md text-graphite">
          Gösterilecek etkinlik yok. Etkinlik, araştırma kaydını açan en az üç farklı öğrenci soru
          sorduğunda görünür.
        </p>
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
