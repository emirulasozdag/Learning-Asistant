import { FolderOpen, ServerOff } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { ConceptProgress } from "../../api/types";
import { useAuth } from "../../auth/useAuth";
import { useCourseOutlet } from "../../features/courses/courseOutlet";
import PracticeSessionView from "../../features/practice/PracticeSession";
import PracticeSetup from "../../features/practice/PracticeSetup";
import PracticeSummary from "../../features/practice/PracticeSummary";
import { usePracticeSession } from "../../features/practice/usePracticeSession";
import { SourceDrawer } from "../../features/tutor/SourceViewer";
import { courseTopics } from "../../features/tutor/suggestions";
import { learningService } from "../../services/learningService";
import Button from "../../ui/Button";
import EmptyState from "../../ui/EmptyState";
import PageTitle from "../../ui/PageTitle";
import { SkeletonRows } from "../../ui/Skeleton";

// Not verilen ödevler pratik kaynağı olmaz (backend `EXCLUDED_TYPES`); yalnızca hazır materyal.
const EXCLUDED_TYPES = new Set(["assignment"]);
const MAX_TOPICS = 8;
const MAX_GAPS = 4;

/**
 * Öğrencinin pratik sayfası (#17). Üç görünüm: kurulum (konu, tür, zorluk), oturum (tek soru
 * odakta, ilerleme, kısayollar) ve özet. Sorular gerçek `POST /practice`'ten gelir, otomatik
 * kontrolden geçmiştir; cevap anahtarı cevaptan önce hiçbir yanıtta yoktur.
 */
export default function PracticePage() {
  const { course, documents, documentsFailed, reloadDocuments } = useCourseOutlet();
  const { user } = useAuth();
  const session = usePracticeSession(course.id);
  const [sourceId, setSourceId] = useState<string | null>(null);
  const [gaps, setGaps] = useState<ConceptProgress[]>([]);

  const usable = useMemo(
    () => documents?.filter((d) => d.status === "ready" && !EXCLUDED_TYPES.has(d.material_type)) ?? null,
    [documents],
  );
  const topics = useMemo(() => (usable ? courseTopics(usable, MAX_TOPICS) : []), [usable]);

  // Öğrenme kaydındaki hâlâ eksik kavramlar (önce en düşük son puan): konu önerisi olarak.
  useEffect(() => {
    const controller = new AbortController();
    learningService
      .record(course.id, controller.signal)
      .then((record) => {
        if (controller.signal.aborted) return;
        setGaps(
          record.concepts
            .filter((concept) => concept.last_score_ratio < 1)
            .sort((a, b) => a.last_score_ratio - b.last_score_ratio)
            .slice(0, MAX_GAPS),
        );
      })
      .catch(() => {
        // Öneriler isteğe bağlıdır; kayıt alınamazsa yalnızca dersin konuları gösterilir.
      });
    return () => controller.abort();
  }, [course.id]);

  const header = (
    <PageTitle
      title="Pratik"
      description="Ders materyalinden üretilen, bağımsız bir çözümle kontrol edilmiş sorularla kendini sına."
    />
  );

  if (documentsFailed) {
    return (
      <div>
        {header}
        <EmptyState
          icon={ServerOff}
          tone="danger"
          title="Materyaller yüklenemedi"
          description="Ders materyaline şu an ulaşılamıyor. Bağlantını kontrol edip tekrar dene."
          action={<Button onClick={reloadDocuments}>Tekrar dene</Button>}
        />
      </div>
    );
  }
  if (usable === null) {
    return (
      <div>
        {header}
        <SkeletonRows rows={4} />
      </div>
    );
  }
  if (usable.length === 0) {
    return (
      <div>
        {header}
        <EmptyState
          icon={FolderOpen}
          title="Henüz soru üretilecek materyal yok"
          description="Eğitmen bu derse ders notu, slayt ya da video ekleyince buradan pratik yapabilirsin."
        />
      </div>
    );
  }

  const researchLogging = user?.researchLogging ?? false;

  return (
    <div>
      {header}
      {session.view === "setup" ? (
        <PracticeSetup
          initial={session.settings}
          gaps={gaps}
          topics={topics}
          researchLogging={researchLogging}
          activeQuestions={session.entries.length}
          onStart={session.start}
          onResume={session.backToSession}
        />
      ) : session.view === "summary" ? (
        <PracticeSummary
          entries={session.entries}
          settings={session.settings}
          courseId={course.id}
          researchLogging={researchLogging}
          onPractice={session.start}
          onResume={session.backToSession}
          onNewSession={session.reset}
        />
      ) : (
        <PracticeSessionView session={session} selectedSourceId={sourceId} onSelectSource={setSourceId} />
      )}
      {sourceId && <SourceDrawer sourceId={sourceId} onClose={() => setSourceId(null)} />}
    </div>
  );
}
