import { BookOpen, ChevronLeft, ChevronRight, ServerOff, SquarePen } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router";

import type { AskResponse, DocumentOut } from "../../api/types";
import { useCourse } from "../../features/courses/context";
import type { ConversationEntry } from "../../features/studio/context";
import { useStudio } from "../../features/studio/useStudio";
import AnswerBlock from "../../features/tutor/AnswerBlock";
import { isStructurable, stripExtractiveIntro, structureAnswer, type Claim, type StructuredAnswer } from "../../features/tutor/claims";
import Composer from "../../features/tutor/Composer";
import { classifyFailure, classifyResponse, describeTurn } from "../../features/tutor/outcome";
import SourceViewer from "../../features/tutor/SourceViewer";
import ClaimAnswer from "../../features/tutor/studio/ClaimAnswer";
import EvidencePanel from "../../features/tutor/studio/EvidencePanel";
import EvidenceThread from "../../features/tutor/studio/EvidenceThread";
import RetrievalMeter from "../../features/tutor/studio/RetrievalMeter";
import type { Turn } from "../../features/tutor/types";
import { useIsDesktop } from "../../features/tutor/useIsDesktop";
import { describeTotals, documentExtent, materialLabel, materialTotals } from "../../labels";
import { courseService, type Course } from "../../services/courseService";
import { tutorService, type QuickAction } from "../../services/tutorService";
import Button from "../../ui/Button";
import EmptyState from "../../ui/EmptyState";
import FileBadge from "../../ui/FileBadge";
import IconButton from "../../ui/IconButton";
import { SkeletonRows } from "../../ui/Skeleton";

/**
 * AI Tutor: dersin materyalinden, kaynaklı ve akışlı cevaplar. Ürünün ana ekranı; çalışma
 * alanının (StudioShell) içinde açılır. Ders yükleme durumları kabukta çözülür.
 */
export default function TutorPage() {
  const courseId = Number(useParams().courseId);
  const course = useCourse(courseId);
  if (!course) return null;
  // `key`: ders değişince sohbet, açık kaynak, materyal durumu ve süren istekler sıfırlanır.
  return <TutorSession key={course.id} course={course} />;
}

/** Aktif turun seçimi: hangi iddia seçili, öğrenci elle başka bir kaynak açtı mı. */
interface Selection {
  turnId: string | null;
  claim: number | null;
  /** Atıf etiketi ya da "Nasıl bulundu" satırından açılan kaynak (iddianın kaynağını ezer). */
  sourceOverride: string | null;
}

const NO_SELECTION: Selection = { turnId: null, claim: null, sourceOverride: null };

/** Cevap iddia görünümünde gösterilebilir mi; gösterilebilirse cümlelere ayrılmış hâli. */
function structuredView(response: AskResponse | undefined): StructuredAnswer | null {
  if (!response?.answer) return null;
  const outcome = classifyResponse(response);
  if (outcome !== "answered" && outcome !== "ai_unavailable") return null;
  const text = outcome === "ai_unavailable" ? stripExtractiveIntro(response.answer) : response.answer;
  if (!isStructurable(text)) return null;
  const structured = structureAnswer(text);
  return structured.claims.length > 0 || structured.lead ? structured : null;
}

function entryState(turn: Turn): ConversationEntry["state"] {
  if (turn.failure || turn.stopped) return "failed";
  if (!turn.response) return "pending";
  const outcome = classifyResponse(turn.response);
  if (outcome === "out_of_scope") return "declined";
  if (outcome === "not_generated") return "failed";
  return "answered";
}

function TutorSession({ course }: { course: Course }) {
  const courseId = course.id;
  const studio = useStudio();
  const desktop = useIsDesktop();

  const [materials, setMaterials] = useState<DocumentOut[] | null>(null);
  const [materialsFailed, setMaterialsFailed] = useState(false);
  const [materialsAttempt, setMaterialsAttempt] = useState(0);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection>(NO_SELECTION);
  const [question, setQuestion] = useState("");
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [claimElement, setClaimElement] = useState<HTMLElement | null>(null);
  const [anchorElement, setAnchorElement] = useState<HTMLElement | null>(null);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const answerScrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Ana sayfadaki soru kutusundan gelen soru (?q=): materyal hazır olunca bir kez sorulur.
  const [searchParams, setSearchParams] = useSearchParams();
  const pendingQuestion = useRef(searchParams.get("q"));

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

  const activeTurn = turns.find((turn) => turn.id === activeId) ?? turns[turns.length - 1] ?? null;
  const activeIndex = activeTurn ? turns.indexOf(activeTurn) : -1;
  const structured = useMemo(() => structuredView(activeTurn?.response), [activeTurn?.response]);

  // Kenar çubuğundaki "Bu sohbet" listesi.
  const { publish, onSelect, queuedQuestion, queueQuestion } = studio;
  useEffect(() => {
    publish(
      turns.map((turn) => ({ id: turn.id, question: turn.question, state: entryState(turn) })),
      activeTurn?.id ?? null,
    );
  }, [turns, activeTurn?.id, publish]);
  useEffect(() => () => publish([], null), [publish]);
  useEffect(() => {
    onSelect((id) => setActiveId(id));
    return () => onSelect(null);
  }, [onSelect]);

  const updateTurn = useCallback((id: string, change: (turn: Turn) => Turn) => {
    setTurns((list) => list.map((turn) => (turn.id === id ? change(turn) : turn)));
  }, []);

  async function ask(text: string) {
    text = text.trim();
    if (!text || busy) return;
    const id = `${Date.now()}`;
    setQuestion("");
    setBusy(true);
    setTurns((list) => [...list, { id, question: text, streamText: "", startedAt: performance.now() }]);
    setActiveId(id);
    setSelection(NO_SELECTION);
    answerScrollRef.current?.scrollTo({ top: 0 });
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
            updateTurn(id, (t) => ({ ...t, response: event.response, finishedAt: performance.now() }));
            setConversationId(event.response.conversation_id);
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

  useEffect(() => {
    const text = pendingQuestion.current;
    if (!text || !materials || materials.length === 0) return;
    pendingQuestion.current = null;
    setSearchParams({}, { replace: true });
    void ask(text);
    // `ask` her çizimde yeniden oluşur; soru yalnızca materyal ilk yüklendiğinde sorulmalı.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [materials]);

  useEffect(() => {
    if (!queuedQuestion || busy || !materials || materials.length === 0) return;
    queueQuestion(null);
    void ask(queuedQuestion);
    // Komut paletinden gelen soru bir kez sorulur.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queuedQuestion, busy, materials]);

  /** Süren cevabı durdurur; tur "Durduruldu" olarak işaretlenir (ask içindeki catch'te). */
  function stop() {
    abortRef.current?.abort();
  }

  function newConversation() {
    abortRef.current?.abort();
    setTurns([]);
    setActiveId(null);
    setSelection(NO_SELECTION);
    setConversationId(null);
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

  // Seçim aktif tura aittir; tur değişince ilk iddia seçilir.
  const current: Selection =
    selection.turnId === activeTurn?.id
      ? selection
      : { turnId: activeTurn?.id ?? null, claim: structured?.claims[0]?.number ?? null, sourceOverride: null };
  const response = activeTurn?.response;
  const selectedClaim = structured?.claims.find((claim) => claim.number === current.claim) ?? null;
  const claimSource = selectedClaim
    ? response?.citations[(selectedClaim.citations[0] ?? 0) - 1]?.source_id
    : undefined;
  const firstCitation = response?.citations[0]?.source_id;
  const sourceId = current.sourceOverride ?? claimSource ?? (structured ? firstCitation : undefined) ?? null;
  const showThread = Boolean(structured && selectedClaim && !current.sourceOverride && desktop);

  function selectClaim(claim: Claim) {
    // Dar ekranda kaynak yan panelde değil tam ekran açılır; iddiaya dokunmak onu açar.
    const source = desktop ? null : (response?.citations[(claim.citations[0] ?? 0) - 1]?.source_id ?? null);
    setSelection({ turnId: activeTurn?.id ?? null, claim: claim.number, sourceOverride: source });
  }

  /** Yukarı/aşağı ok: bir önceki ya da sonraki iddiaya geçer (odak cevap alanındayken). */
  function moveClaim(step: 1 | -1) {
    const claims = structured?.claims ?? [];
    if (claims.length === 0) return;
    const index = claims.findIndex((claim) => claim.number === current.claim);
    const next = claims[Math.min(Math.max(index + step, 0), claims.length - 1)];
    selectClaim(next);
    requestAnimationFrame(() =>
      answerScrollRef.current
        ?.querySelector<HTMLButtonElement>(`[data-claim="${next.number}"]`)
        ?.focus({ preventScroll: false }),
    );
  }

  function selectSource(id: string) {
    setSelection({ ...current, sourceOverride: id });
  }

  function closeSource() {
    setSelection({ ...current, claim: null, sourceOverride: null });
  }

  const noMaterials = materials !== null && materials.length === 0;
  // Dar ekranda kaynak tam ekran açılır; yalnızca öğrenci açıkça istediğinde.
  const mobileSource = !desktop && current.sourceOverride;
  const evidenceOpen = desktop && sourceId && (current.claim != null || current.sourceOverride);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={workspaceRef} className="relative flex min-h-0 flex-1 gap-8 px-4 sm:px-6">
        <section className="flex min-w-0 flex-1 flex-col">
          {turns.length > 0 && (
            <div className="flex shrink-0 items-center gap-2 pb-2">
              <span className="font-mono text-xs text-graphite">
                Soru {activeIndex + 1} / {turns.length}
              </span>
              <IconButton
                icon={ChevronLeft}
                label="Önceki soru"
                size="sm"
                disabled={activeIndex <= 0}
                onClick={() => setActiveId(turns[activeIndex - 1]?.id ?? null)}
              />
              <IconButton
                icon={ChevronRight}
                label="Sonraki soru"
                size="sm"
                disabled={activeIndex >= turns.length - 1}
                onClick={() => setActiveId(turns[activeIndex + 1]?.id ?? null)}
              />
              <Button size="sm" variant="ghost" icon={SquarePen} onClick={newConversation} className="ml-auto">
                Yeni sohbet
              </Button>
            </div>
          )}

          <div
            ref={answerScrollRef}
            onKeyDown={(event) => {
              if (!structured || !(event.target instanceof HTMLElement) || !event.target.dataset.claim) return;
              if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                moveClaim(event.key === "ArrowDown" ? 1 : -1);
              }
            }}
            className="min-h-0 flex-1 overflow-y-auto pr-1 pb-6"
          >
            {!activeTurn ? (
              <TutorWelcome
                course={course}
                materials={materials}
                failed={materialsFailed}
                onReload={() => {
                  setMaterialsFailed(false);
                  setMaterials(null);
                  setMaterialsAttempt((attempt) => attempt + 1);
                }}
              />
            ) : structured && response ? (
              <>
                {classifyResponse(response) === "ai_unavailable" && (
                  <p className="mb-4 rounded-panel border border-line bg-surface px-3 py-2 text-sm text-graphite">
                    Yapay zekâ şu an kullanılamıyor; ders materyalindeki ilgili bölüm olduğu gibi, cümle cümle
                    gösteriliyor.
                  </p>
                )}
                <ClaimAnswer
                  question={activeTurn.question}
                  response={response}
                  answer={structured}
                  selectedClaim={current.claim}
                  onSelectClaim={selectClaim}
                  claimRef={setClaimElement}
                  onSelectSource={selectSource}
                  isLatest={activeIndex === turns.length - 1}
                  onQuickAction={quickAction}
                  elapsedMs={
                    activeTurn.startedAt != null && activeTurn.finishedAt != null
                      ? activeTurn.finishedAt - activeTurn.startedAt
                      : null
                  }
                />
              </>
            ) : (
              <div className="flex flex-col gap-5">
                <p className="max-w-[46rem] self-start rounded-panel border border-line bg-surface px-4 py-3 text-base text-ink-2 shadow-card">
                  {activeTurn.question}
                </p>
                <AnswerBlock
                  turn={activeTurn}
                  isLatest={activeIndex === turns.length - 1}
                  onQuickAction={quickAction}
                  onRetry={() => retry(activeTurn)}
                  selectedSourceId={sourceId}
                  onSelectSource={selectSource}
                />
              </div>
            )}
          </div>
        </section>

        {evidenceOpen && sourceId && (
          <div className="w-[min(42%,34rem)] shrink-0 overflow-y-auto pb-6">
            <EvidencePanel
              key={sourceId}
              sourceId={sourceId}
              course={course}
              documents={materials}
              claimNumber={!current.sourceOverride ? (selectedClaim?.number ?? null) : null}
              anchorRef={setAnchorElement}
              onClose={closeSource}
            />
          </div>
        )}

        {showThread && evidenceOpen && (
          <EvidenceThread
            containerRef={workspaceRef}
            source={claimElement}
            target={anchorElement}
            drawKey={`${activeTurn?.id}-${current.claim}-${sourceId}`}
          />
        )}
      </div>

      <div className="flex shrink-0 flex-col gap-3 px-4 pt-2 pb-4 sm:px-6">
        {response && structured && (
          <RetrievalMeter
            key={`${activeTurn?.id}-${desktop}`}
            response={response}
            selectedSourceId={sourceId}
            onSelectSource={selectSource}
            initiallyOpen={desktop}
          />
        )}
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

      {mobileSource && <SourceViewer sourceId={mobileSource} onClose={closeSource} />}

      {/* Ekran okuyucu için durum duyurusu: yalnızca durum değişince güncellenir. */}
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        {turns.length > 0 ? describeTurn(turns[turns.length - 1]) : ""}
      </div>
    </div>
  );
}

const HOW_IT_WORKS = [
  { title: "Soru sor", text: "Dersin materyaline ne merak ediyorsan yaz; cevap yalnızca onaylı materyalden gelir." },
  { title: "Cümleye dokun", text: "Cevabın her cümlesi numaralıdır; dokununca dayandığı sayfa yanda açılır." },
  { title: "Kaynağı kontrol et", text: "İşaretli satırı cevapla karşılaştır; materyalde yoksa asistan bunu söyler." },
];

function TutorWelcome({
  course,
  materials,
  failed,
  onReload,
}: {
  course: Course;
  materials: DocumentOut[] | null;
  /** Materyal listesi yüklenemedi: "materyal yok"tan farklı bir durum. */
  failed: boolean;
  onReload: () => void;
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
  const extent = describeTotals(materialTotals(materials ?? []));
  return (
    <div className="max-w-3xl py-10">
      <p className="font-mono text-xs text-graphite">{course.code}</p>
      <h1 className="mt-2 text-[2.5rem] leading-[1.08] font-semibold tracking-tight text-balance text-ink">
        {course.name} dersine sor
      </h1>
      <p className="mt-3 max-w-2xl text-md text-graphite">
        {materials
          ? `Cevaplar bu dersin ${materials.length} dokümanındaki${extent ? ` (${extent})` : ""} bölümlere dayandırılır. Her cümlenin kaynağı yanında açılır; önemli konularda kaynağı açıp kontrol et.`
          : "Cevaplar bu dersin materyalindeki bölümlere dayandırılır. Her cümlenin kaynağı yanında açılır; önemli konularda kaynağı açıp kontrol et."}
      </p>

      <ol className="mt-8 grid gap-3 sm:grid-cols-3">
        {HOW_IT_WORKS.map((step, index) => (
          <li key={step.title} className="flex gap-3 rounded-panel border border-line bg-surface px-4 py-3 shadow-card">
            <span
              aria-hidden
              className="flex size-7 shrink-0 items-center justify-center rounded-full border border-accent-line bg-accent-soft text-xs font-semibold text-accent"
            >
              {index + 1}
            </span>
            <span>
              <span className="block text-base font-semibold text-ink">{step.title}</span>
              <span className="block text-sm text-graphite">{step.text}</span>
            </span>
          </li>
        ))}
      </ol>

      <h2 className="mt-10 mb-3 text-sm font-medium text-ink-2">Cevapların dayandığı materyal</h2>
      {materials === null ? (
        <SkeletonRows rows={2} />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {materials.map((document) => (
            <li
              key={document.id}
              className="flex items-center gap-3 rounded-panel border border-line bg-surface px-4 py-3 shadow-card"
            >
              <FileBadge filename={document.filename} />
              <span className="min-w-0">
                <span className="block truncate text-base font-medium text-ink">{document.title}</span>
                <span className="block text-sm text-graphite">
                  {materialLabel(document.material_type)}, {documentExtent(document)}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
