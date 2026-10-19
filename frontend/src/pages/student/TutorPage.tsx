import { ArrowUpRight, BookOpen, ShieldCheck, SquarePen } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router";

import type { DocumentOut } from "../../api/types";
import { useCourse, useCourses } from "../../features/courses/context";
import AnswerBlock from "../../features/tutor/AnswerBlock";
import Composer from "../../features/tutor/Composer";
import { classifyFailure } from "../../features/tutor/outcome";
import SourcePanel from "../../features/tutor/SourcePanel";
import type { Turn } from "../../features/tutor/types";
import { materialLabel } from "../../labels";
import { courseService, type Course } from "../../services/courseService";
import { tutorService, type QuickAction } from "../../services/tutorService";
import Badge from "../../ui/Badge";
import Button from "../../ui/Button";
import EmptyState from "../../ui/EmptyState";
import FileBadge from "../../ui/FileBadge";
import Skeleton from "../../ui/Skeleton";

/** AI Tutor: dersin materyalinden, kaynaklı ve akışlı cevaplar. Ürünün ana ekranı. */
export default function TutorPage() {
  const courseId = Number(useParams().courseId);
  const course = useCourse(courseId);
  const { loading: coursesLoading } = useCourses();
  const navigate = useNavigate();

  const [materials, setMaterials] = useState<DocumentOut[] | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [sourceId, setSourceId] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;
    courseService
      .materials(courseId)
      .then((list) => {
        if (!cancelled) setMaterials(list);
      })
      .catch(() => {
        if (!cancelled) setMaterials([]);
      });
    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
  }, [courseId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  const updateTurn = useCallback((id: string, change: (turn: Turn) => Turn) => {
    setTurns((list) => list.map((turn) => (turn.id === id ? change(turn) : turn)));
  }, []);

  async function ask(text: string) {
    text = text.trim();
    if (!text || busy) return;
    const id = `${Date.now()}`;
    setQuestion("");
    setBusy(true);
    setTurns((list) => [...list, { id, question: text, streamText: "" }]);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await tutorService.ask(
        courseId,
        text,
        conversationId,
        (event) => {
          if (event.type === "retrieval") updateTurn(id, (t) => ({ ...t, hits: event.hits }));
          else if (event.type === "delta")
            updateTurn(id, (t) => ({ ...t, streamText: t.streamText + event.text }));
          else if (event.type === "done") {
            updateTurn(id, (t) => ({ ...t, response: event.response }));
            setConversationId(event.response.conversation_id);
            const first = event.response.citations[0];
            if (first) setSourceId(first.source_id);
          } else {
            // Akıştaki `error` olayı kod taşımıyor: veritabanı, arama ya da üretim hatasını
            // ayıramayız. Hepsi "geçici sorun" olarak gösterilir, asla "konu derste yok" olarak değil.
            updateTurn(id, (t) => ({ ...t, failure: { kind: "temporary" } }));
          }
        },
        controller.signal,
      );
      updateTurn(id, (t) =>
        t.response || t.failure ? t : { ...t, failure: { kind: "unavailable" } },
      );
    } catch (reason) {
      if (!controller.signal.aborted) {
        updateTurn(id, (t) => ({ ...t, failure: classifyFailure(reason) }));
      }
    } finally {
      setBusy(false);
    }
  }

  function newConversation() {
    abortRef.current?.abort();
    setTurns([]);
    setConversationId(null);
    setSourceId(null);
    setBusy(false);
  }

  /** Başarısız ya da üretilemeyen soruyu aynı metinle yeniden sorar; eski deneme listeden çıkar. */
  function retry(turn: Turn) {
    if (busy) return;
    setTurns((list) => list.filter((item) => item.id !== turn.id));
    void ask(turn.question);
  }

  function quickAction(action: QuickAction) {
    void ask(tutorService.quickActionPrompt(action));
  }

  function practice(topic: string) {
    navigate(`/student/practice?course=${courseId}&topic=${encodeURIComponent(topic)}`);
  }

  if (!course && !coursesLoading) {
    return (
      <EmptyState
        icon={BookOpen}
        title="Ders bulunamadı"
        description="Soldaki menüden bir ders seç."
        className="py-24"
      />
    );
  }

  const noMaterials = materials !== null && materials.length === 0;

  return (
    <div className="flex h-full min-h-0">
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-12 shrink-0 items-center gap-3 border-b border-line bg-surface px-5">
          {course ? (
            <>
              <Badge>{course.code}</Badge>
              <p className="truncate text-base font-medium text-ink">{course.name}</p>
            </>
          ) : (
            <Skeleton className="h-3.5 w-64" />
          )}
          <div className="ml-auto flex shrink-0 items-center gap-3">
            <span
              className={`hidden items-center gap-1.5 text-sm whitespace-nowrap text-graphite md:flex ${
                sourceId ? "lg:hidden 2xl:flex" : ""
              }`}
            >
              <ShieldCheck size={14} aria-hidden className="text-accent" />
              Yalnızca bu dersin materyalinden cevaplar
            </span>
            {turns.length > 0 && (
              <Button size="sm" variant="ghost" icon={SquarePen} onClick={newConversation}>
                Yeni sohbet
              </Button>
            )}
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[720px] px-5 sm:px-8">
            {turns.length === 0 ? (
              course && (
                <TutorWelcome
                  course={course}
                  materials={materials}
                  onAsk={(text) => void ask(text)}
                />
              )
            ) : (
              <ol className="pt-8 pb-6">
                {turns.map((turn, index) => (
                  <li key={turn.id} className="border-b border-line py-8 first:pt-0 last:border-b-0">
                    <p className="mb-5 text-lg font-semibold tracking-tight text-ink">{turn.question}</p>
                    <AnswerBlock
                      turn={turn}
                      isLatest={index === turns.length - 1}
                      onQuickAction={quickAction}
                      onPractice={() => practice(turn.question)}
                      onRetry={() => retry(turn)}
                      selectedSourceId={sourceId}
                      onSelectSource={setSourceId}
                    />
                  </li>
                ))}
              </ol>
            )}
            <div ref={endRef} />
          </div>
        </div>

        <div className="shrink-0 px-5 pt-2 pb-4 sm:px-8">
          <div className="mx-auto max-w-[720px]">
            <Composer
              value={question}
              onChange={setQuestion}
              onSubmit={() => void ask(question)}
              busy={busy}
              disabled={noMaterials}
              placeholder={
                noMaterials
                  ? "Bu derse henüz materyal yüklenmedi"
                  : turns.length > 0
                    ? "Takip sorusu sor"
                    : "Bu ders hakkında bir soru sor"
              }
              hint="Cevaplar ders materyaline dayanır; önemli konularda kaynağını kontrol et."
            />
          </div>
        </div>
      </section>

      {sourceId && (
        <>
          <div className="hidden w-[min(46%,560px)] shrink-0 border-l border-line lg:block">
            <SourcePanel sourceId={sourceId} onClose={() => setSourceId(null)} />
          </div>
          <div className="fixed inset-0 z-40 lg:hidden">
            <div className="fade-in absolute inset-0 bg-ink/25" onClick={() => setSourceId(null)} aria-hidden />
            <div className="slide-in-right absolute inset-y-0 right-0 w-full max-w-md shadow-float">
              <SourcePanel sourceId={sourceId} onClose={() => setSourceId(null)} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function TutorWelcome({
  course,
  materials,
  onAsk,
}: {
  course: Course;
  materials: DocumentOut[] | null;
  onAsk: (text: string) => void;
}) {
  if (materials !== null && materials.length === 0) {
    return (
      <EmptyState
        icon={BookOpen}
        title="Bu derse henüz materyal yüklenmedi"
        description="Eğitmenin ders notlarını yüklediğinde buradan soru sorabileceksin."
        className="py-24"
      />
    );
  }
  const pages = materials?.reduce((sum, d) => sum + d.page_count, 0) ?? 0;
  return (
    <div className="py-14">
      <h1 className="text-2xl font-semibold tracking-tight text-ink">{course.name} dersine sor</h1>
      <p className="mt-2 text-md text-graphite">
        {materials
          ? `Cevaplar bu dersin ${materials.length} dokümanından (${pages} sayfa) gelir ve her bilgi dayandığı sayfaya bağlanır. Materyalde olmayan bir şeye cevap uydurmaz.`
          : "Cevaplar yalnızca bu dersin materyalinden gelir ve her bilgi dayandığı sayfaya bağlanır."}
      </p>

      <h2 className="mt-10 mb-2 text-sm text-graphite">Buradan başlayabilirsin</h2>
      <ul className="divide-y divide-line rounded-panel border border-line bg-surface">
        {tutorService.suggestedQuestions(course.code).map((suggestion) => (
          <li key={suggestion}>
            <button
              type="button"
              onClick={() => onAsk(suggestion)}
              className="group flex w-full items-center justify-between gap-4 px-4 py-3 text-left text-md text-ink transition-colors hover:bg-canvas"
            >
              {suggestion}
              <ArrowUpRight
                size={16}
                aria-hidden
                className="shrink-0 text-faint transition-colors group-hover:text-accent"
              />
            </button>
          </li>
        ))}
      </ul>

      {materials && materials.length > 0 && (
        <>
          <h2 className="mt-10 mb-3 text-sm text-graphite">Bu derste aranan materyal</h2>
          <ul className="flex flex-col gap-2">
            {materials.map((document) => (
              <li key={document.id} className="flex items-center gap-3 text-base">
                <FileBadge filename={document.filename} size="sm" />
                <span className="truncate text-ink">{document.title}</span>
                <span className="ml-auto shrink-0 text-sm text-graphite">
                  {materialLabel(document.material_type)}, {document.page_count} sayfa
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
