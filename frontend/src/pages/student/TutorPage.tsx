import { ArrowUpRight, BookOpen, ServerOff, SquarePen } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router";

import type { DocumentOut } from "../../api/types";
import { useCourse, useCourses } from "../../features/courses/context";
import AnswerBlock from "../../features/tutor/AnswerBlock";
import Composer from "../../features/tutor/Composer";
import { classifyFailure, describeTurn } from "../../features/tutor/outcome";
import SourceViewer from "../../features/tutor/SourceViewer";
import type { Turn } from "../../features/tutor/types";
import { isDesktopNow } from "../../features/tutor/useIsDesktop";
import { materialLabel } from "../../labels";
import { courseService, type Course } from "../../services/courseService";
import { tutorService, type QuickAction } from "../../services/tutorService";
import Badge from "../../ui/Badge";
import Button from "../../ui/Button";
import EmptyState from "../../ui/EmptyState";
import FileBadge from "../../ui/FileBadge";
import { SkeletonRows } from "../../ui/Skeleton";

/**
 * AI Tutor: dersin materyalinden, kaynaklı ve akışlı cevaplar. Ürünün ana ekranı.
 * Ders listesinin durumunu (yükleniyor / hata / ders yok) burada çözer; sohbet `TutorSession`'da.
 */
export default function TutorPage() {
  const courseId = Number(useParams().courseId);
  const course = useCourse(courseId);
  const { loading, error, refresh } = useCourses();
  const [retrying, setRetrying] = useState(false);

  async function retryCourses() {
    setRetrying(true);
    await refresh();
    setRetrying(false);
  }

  if (!course) {
    if (loading) {
      return (
        <div className="mx-auto max-w-3xl px-6 pt-10">
          <SkeletonRows rows={2} />
        </div>
      );
    }
    if (error) {
      return (
        <EmptyState
          icon={ServerOff}
          tone="danger"
          title="Dersler yüklenemedi"
          description="Ders listesine şu an ulaşılamıyor. Bağlantını kontrol edip tekrar dene."
          action={
            <Button loading={retrying} onClick={() => void retryCourses()}>
              Tekrar dene
            </Button>
          }
          className="py-24"
        />
      );
    }
    return (
      <EmptyState
        icon={BookOpen}
        title="Ders bulunamadı"
        description="Soldaki menüden bir ders seç."
        className="py-24"
      />
    );
  }

  // `key`: ders değişince sohbet, açık kaynak, materyal durumu ve süren istekler sıfırlanır.
  return <TutorSession key={course.id} course={course} />;
}

function TutorSession({ course }: { course: Course }) {
  const courseId = course.id;
  const navigate = useNavigate();

  const [materials, setMaterials] = useState<DocumentOut[] | null>(null);
  const [materialsFailed, setMaterialsFailed] = useState(false);
  const [materialsAttempt, setMaterialsAttempt] = useState(0);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [sourceId, setSourceId] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    courseService
      .materials(courseId, controller.signal)
      .then((list) => {
        if (!controller.signal.aborted) setMaterials(list);
      })
      .catch(() => {
        if (!controller.signal.aborted) setMaterialsFailed(true);
      });
    return () => controller.abort();
  }, [courseId, materialsAttempt]);

  // Sayfadan ya da dersten ayrılırken süren soruyu iptal et.
  useEffect(() => () => abortRef.current?.abort(), []);

  function reloadMaterials() {
    setMaterialsFailed(false);
    setMaterials(null);
    setMaterialsAttempt((attempt) => attempt + 1);
  }

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
            // Dar ekranda kaynak tam ekran açılır; öğrenci istemeden cevabın üstünü örtmesin.
            if (first && isDesktopNow()) setSourceId(first.source_id);
          } else {
            // Akıştaki `error` olayı kod taşımıyor: veritabanı, arama ya da üretim hatasını
            // ayıramayız. Hepsi "geçici sorun" olarak gösterilir, asla "konu derste yok" olarak değil.
            updateTurn(id, (t) => ({ ...t, failure: { kind: "temporary" } }));
          }
        },
        controller.signal,
      );
      updateTurn(id, (t) => {
        if (t.response || t.failure) return t;
        return controller.signal.aborted ? { ...t, stopped: true } : { ...t, failure: { kind: "unavailable" } };
      });
    } catch (reason) {
      updateTurn(id, (t) => {
        if (t.response || t.failure) return t;
        return controller.signal.aborted ? { ...t, stopped: true } : { ...t, failure: classifyFailure(reason) };
      });
    } finally {
      // Yeni sohbet başladıysa eski isteğin bitişi yeni isteğin durumunu bozmasın.
      if (abortRef.current === controller) setBusy(false);
    }
  }

  /** Süren cevabı durdurur; tur "Durduruldu" olarak işaretlenir (ask içindeki catch'te). */
  function stop() {
    abortRef.current?.abort();
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

  const noMaterials = materials !== null && materials.length === 0;

  return (
    <div className="flex h-full min-h-0">
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-12 shrink-0 items-center gap-3 border-b border-line bg-surface px-5">
          <Badge>{course.code}</Badge>
          <p className="truncate text-base font-medium text-ink">{course.name}</p>
          <div className="ml-auto flex shrink-0 items-center gap-3">
            <span
              className={`hidden items-center gap-1.5 text-sm whitespace-nowrap text-graphite md:flex ${
                sourceId ? "lg:hidden 2xl:flex" : ""
              }`}
            >
              <BookOpen size={14} aria-hidden className="text-graphite" />
              Cevaplar bu dersin materyaline dayandırılır
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
              <TutorWelcome
                course={course}
                materials={materials}
                failed={materialsFailed}
                onReload={reloadMaterials}
                onAsk={(text) => void ask(text)}
              />
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
              onStop={stop}
              disabled={noMaterials}
              placeholder={
                noMaterials
                  ? "Bu derse henüz materyal yüklenmedi"
                  : turns.length > 0
                    ? "Takip sorusu sor"
                    : "Bu ders hakkında bir soru sor"
              }
              hint="Cevaplar ders materyalindeki bölümlere dayandırılır; önemli konularda kaynağı açıp kontrol et."
            />
          </div>
        </div>
      </section>

      {sourceId && <SourceViewer sourceId={sourceId} onClose={() => setSourceId(null)} />}

      {/* Ekran okuyucu için durum duyurusu: yalnızca durum değişince güncellenir. */}
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        {turns.length > 0 ? describeTurn(turns[turns.length - 1]) : ""}
      </div>
    </div>
  );
}

function TutorWelcome({
  course,
  materials,
  failed,
  onReload,
  onAsk,
}: {
  course: Course;
  materials: DocumentOut[] | null;
  /** Materyal listesi yüklenemedi: "materyal yok"tan farklı bir durum. */
  failed: boolean;
  onReload: () => void;
  onAsk: (text: string) => void;
}) {
  if (failed) {
    return (
      <EmptyState
        icon={ServerOff}
        tone="danger"
        title="Materyaller yüklenemedi"
        description="Ders materyaline şu an ulaşılamıyor. Bağlantını kontrol edip tekrar dene."
        action={<Button onClick={onReload}>Tekrar dene</Button>}
        className="py-24"
      />
    );
  }
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
          ? `Cevaplar bu dersin ${materials.length} dokümanındaki (${pages} sayfa) bölümlere dayandırılır ve kaynak sayfaları gösterilir. Yine de önemli konularda kaynağı açıp kontrol et.`
          : "Cevaplar bu dersin materyalindeki bölümlere dayandırılır ve kaynak sayfaları gösterilir. Önemli konularda kaynağı açıp kontrol et."}
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

      {materials === null && (
        <>
          <h2 className="mt-10 mb-3 text-sm text-graphite">Bu derste aranan materyal</h2>
          <SkeletonRows rows={2} />
        </>
      )}

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
