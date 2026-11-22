import { ArrowLeft, ChevronDown, FileText, PlayCircle, ServerOff, SquarePen, Video } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import type { ChunkPreview, Citation, DocumentOut, FrameRef, VideoMoment } from "../../api/types";
import { useCourse } from "../../features/courses/context";
import AnswerBlock from "../../features/tutor/AnswerBlock";
import Composer from "../../features/tutor/Composer";
import { SourceDrawer } from "../../features/tutor/SourceViewer";
import TurnExtras from "../../features/tutor/TutorTurnView";
import { answerOf } from "../../features/tutor/turns";
import type { TutorTurn } from "../../features/tutor/types";
import { useTutorTurns } from "../../features/tutor/useTutorTurns";
import FrameAtMoment from "../../features/video/FrameAtMoment";
import { citedFrameIds, useFrames } from "../../features/video/frames";
import LecturePlayer, { type PlayerHandle } from "../../features/video/LecturePlayer";
import SlideStrip from "../../features/video/SlideStrip";
import { courseService } from "../../services/courseService";
import { tutorService, type QuickAction } from "../../services/tutorService";
import { formatTime, formatTimeRange } from "../../text";
import Button from "../../ui/Button";
import { cx } from "../../ui/cx";
import EmptyState from "../../ui/EmptyState";
import { SkeletonRows } from "../../ui/Skeleton";

/**
 * Video çalışma ekranı (#103): büyük video, altında açılıp kapanan transkript, yanda soru-cevap.
 * Öğrenci durdurup sorar; soru o anla gider, cevap önce o kısmın transkriptinden gelir ve
 * kaynağı ("Videodan · 13:32–15:50") açıkça yazılır. Cevabın dayandığı kısım transkriptte ve
 * zaman çizgisinde işaretlenir; "Videoya devam et" kaldığı yerden oynatır.
 */
export default function VideoStudyPage() {
  const params = useParams();
  const courseId = Number(params.courseId);
  const documentId = Number(params.documentId);
  const course = useCourse(courseId);
  // Liste, yüklendiği dersle birlikte tutulur: ders değişince eski dersin listesi (ve onunla
  // açılan sohbet) yeni dersin sayfasında bir an bile görünmez (#28).
  const [loaded, setLoaded] = useState<{ courseId: number; list: DocumentOut[] } | null>(null);
  // Hata da yüklenen derse aittir: bir dersin hatası başka derse geçince ekranda kalmaz (#32).
  const [failedCourse, setFailedCourse] = useState<number | null>(null);
  const [attempt, setAttempt] = useState(0);
  const materials = loaded?.courseId === courseId ? loaded.list : null;
  const failed = failedCourse === courseId;

  useEffect(() => {
    const controller = new AbortController();
    courseService
      .materials(courseId, controller.signal)
      .then((list) => {
        if (!controller.signal.aborted) setLoaded({ courseId, list });
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailedCourse(courseId);
      });
    return () => controller.abort();
  }, [courseId, attempt]);

  const videos = useMemo(
    () =>
      (materials ?? []).filter(
        (doc) =>
          doc.course_id === courseId && doc.material_type === "video" && doc.status === "ready" && Boolean(doc.media_url),
      ),
    [materials, courseId],
  );
  const video = videos.find((doc) => doc.id === documentId);
  const back = `/student/courses/${courseId}/videos`;

  if (failed) {
    return (
      <EmptyState
        icon={ServerOff}
        tone="danger"
        title="Video açılamadı"
        description="Ders materyaline şu an ulaşılamıyor. Bağlantını kontrol edip tekrar dene."
        action={
          <Button
            onClick={() => {
              setFailedCourse(null);
              setAttempt((value) => value + 1);
            }}
          >
            Tekrar dene
          </Button>
        }
        className="py-24"
      />
    );
  }
  if (!course || materials === null) {
    return (
      <div className="page">
        <SkeletonRows rows={4} />
      </div>
    );
  }
  if (!video) {
    return (
      <EmptyState
        icon={Video}
        title="Bu video oynatılamıyor"
        description="Video bulunamadı ya da eğitmen oynatma adresi eklememiş. Ders videoları listesinden başka bir video seç."
        action={
          <Link to={back} className="link">
            Ders videolarına dön
          </Link>
        }
        className="py-24"
      />
    );
  }
  // `key`: başka ders ya da video seçilince sohbet ve oynatıcı baştan kurulur (#28).
  return (
    <StudySession
      key={`${courseId}-${video.id}`}
      courseId={courseId}
      language={course.language}
      video={video}
      videos={videos}
      back={back}
    />
  );
}

function StudySession({
  courseId,
  language,
  video,
  videos,
  back,
}: {
  courseId: number;
  /** Dersin dili: altyazı bu dilde açılır (YouTube tarayıcının diline çevirmesin). */
  language: "tr" | "en";
  video: DocumentOut;
  videos: DocumentOut[];
  back: string;
}) {
  const navigate = useNavigate();
  const playerRef = useRef<PlayerHandle>(null);
  const [time, setTime] = useState(0);
  const [question, setQuestion] = useState("");
  const [drawerSource, setDrawerSource] = useState<string | null>(null);
  const conversation = useTutorTurns(courseId, `video-${video.id}`);
  const { turns, busy } = conversation;
  const chunks = useChunks(video.id);
  // Videodan çıkarılan kareler (#27): bir kez yüklenir; yoksa şerit ve kareler görünmez.
  const frames = useFrames(video.id);
  const chatRef = useRef<HTMLDivElement>(null);
  // Transkript kapalı başlar (ekranı kalabalıklaştırmasın); cevap videoya dayanınca açılır.
  const [transcriptOpen, setTranscriptOpen] = useState(false);

  useEffect(() => {
    const timer = window.setInterval(() => setTime(playerRef.current?.currentTime() ?? 0), 1000);
    return () => window.clearInterval(timer);
  }, []);

  // Yalnızca sohbet kutusu kayar; sayfa (telefonda video) yerinde kalır.
  useEffect(() => {
    const box = chatRef.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [turns.length]);

  const latest = turns.length > 0 ? answerOf(turns[turns.length - 1])?.response : undefined;
  const moment = latest?.video_moment?.document_id === video.id ? latest.video_moment : null;
  const cited = useMemo(
    () => new Set((latest?.citations ?? []).filter((c) => isThisVideo(c, video)).map((c) => c.source_id)),
    [latest, video],
  );

  // Yeni cevap videonun bir kısmına dayanıyorsa transkript açılır ve o kısım görünür.
  // (Efekt yerine çizim sırasında: React'in "önceki değere göre durum ayarlama" kalıbı.)
  const [seenAnswer, setSeenAnswer] = useState(latest);
  if (latest !== seenAnswer) {
    setSeenAnswer(latest);
    if (moment != null || cited.size > 0) setTranscriptOpen(true);
  }

  function seek(seconds: number) {
    playerRef.current?.seek(seconds);
    setTime(seconds);
  }

  async function ask(text: string) {
    const at = Math.floor(playerRef.current?.currentTime() ?? time);
    setQuestion("");
    // Sorunun sorulduğu an turla birlikte saklanır (sohbette "· 15:24" ve o andaki kare).
    await conversation.ask(text, { document_id: video.id, time_s: at });
  }

  function selectSource(sourceId: string) {
    const citation = findCitation(turns, sourceId);
    if (citation && isThisVideo(citation, video) && citation.t_start != null) seek(citation.t_start);
    else setDrawerSource(sourceId);
  }

  function quickAction(action: QuickAction) {
    void ask(tutorService.quickActionPrompt(action));
  }

  return (
    <div className="lg:flex lg:h-full lg:min-h-0 lg:flex-col lg:overflow-hidden">
      <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-line bg-surface/70 px-4 py-2.5 sm:px-6">
        <Link to={back} className="link inline-flex items-center gap-1.5 text-sm">
          <ArrowLeft size={14} aria-hidden />
          Ders videoları
        </Link>
        <span aria-hidden className="h-4 w-px bg-line" />
        <h1 className="min-w-0 flex-1 truncate text-base font-semibold text-ink">{video.title}</h1>
        {videos.length > 1 && (
          <label className="flex items-center gap-2 text-sm text-graphite">
            <span className="hidden sm:inline">Başka video</span>
            <select
              value={video.id}
              onChange={(event) => navigate(`/student/courses/${courseId}/watch/${event.target.value}`)}
              className="h-8 max-w-56 rounded-control border border-line bg-surface px-2 text-sm text-ink"
            >
              {videos.map((doc) => (
                <option key={doc.id} value={doc.id}>
                  {doc.title}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {/* Telefonda tek sütun: video, zaman çizgisi, sohbet, transkript (sol sütun `contents`
          olduğundan öğeleri sıraya girer). Geniş ekranda solda video+transkript, sağda sohbet. */}
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 p-4 sm:px-6 lg:min-h-0 lg:flex-1 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="contents lg:flex lg:min-h-0 lg:flex-col lg:gap-3">
          <div
            className={cx(
              "order-1 shrink-0 overflow-hidden rounded-panel bg-black lg:order-none",
              transcriptOpen ? "[&>*]:max-h-[50vh]" : "[&>*]:max-h-[50vh] lg:[&>*]:max-h-[68vh]",
            )}
          >
            <LecturePlayer
              ref={playerRef}
              mediaUrl={video.media_url!}
              title={video.title}
              captionsUrl={video.file_url}
              captionsLang={language}
            />
          </div>
          <div className="order-2 flex min-w-0 shrink-0 flex-col gap-3 lg:order-none">
            <Timeline duration={video.duration_s} time={time} moment={moment} onSeek={seek} />
            <SlideStrip frames={frames} time={time} onSeek={seek} />
          </div>
          <Transcript
            chunks={chunks}
            time={time}
            cited={cited}
            moment={moment}
            open={transcriptOpen}
            onToggle={() => setTranscriptOpen((value) => !value)}
            onSeek={seek}
          />
        </div>

        <aside
          aria-label="Videoya soru sor"
          className="order-3 flex min-h-[28rem] flex-col rounded-panel border border-line bg-surface lg:order-none lg:min-h-0"
        >
          <div className="flex shrink-0 items-center gap-2 border-b border-line px-4 py-2.5">
            <p className="flex-1 text-sm font-semibold text-ink">Bu videoya soru sor</p>
            {turns.length > 0 && (
              <Button size="sm" variant="ghost" icon={SquarePen} onClick={conversation.reset}>
                Yeni sohbet
              </Button>
            )}
          </div>
          <div ref={chatRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
            {turns.length === 0 ? (
              <p className="text-sm text-graphite">
                Anlamadığın yerde videoyu durdur ve sor ("burayı anlamadım" yeterli). Cevap önce videonun o
                kısmından gelir; dayandığı yer transkriptte ve zaman çizgisinde işaretlenir.
              </p>
            ) : (
              <div className="flex flex-col gap-6">
                {turns.map((turn, index) => (
                  <StudyTurn
                    key={turn.id}
                    turn={turn}
                    askedAt={turn.askedAt?.documentId === video.id ? turn.askedAt.seconds : undefined}
                    frames={frames}
                    video={video}
                    isLatest={index === turns.length - 1}
                    onQuickAction={quickAction}
                    onRetry={() => conversation.retry(turn, { document_id: video.id, time_s: Math.floor(time) })}
                    onAsk={(text) => void ask(text)}
                    onSelectSource={selectSource}
                    onSeek={seek}
                    onResume={() => playerRef.current?.play()}
                  />
                ))}
              </div>
            )}
          </div>
          {/* Yazmaya başlayınca video durur: soru o ana göre sorulur. */}
          <div className="shrink-0 border-t border-line p-3" onFocusCapture={() => playerRef.current?.pause()}>
            <Composer
              value={question}
              onChange={setQuestion}
              onSubmit={() => void ask(question)}
              busy={busy}
              onStop={conversation.stop}
              placeholder={turns.length > 0 ? "Takip sorusu sor" : "Videoyu durdurup sor"}
              hint={`Sorun videonun ${formatTime(time)} anıyla gider.`}
            />
          </div>
        </aside>
      </div>
      {drawerSource && <SourceDrawer sourceId={drawerSource} onClose={() => setDrawerSource(null)} />}
    </div>
  );
}

function isThisVideo(citation: Citation, video: DocumentOut): boolean {
  return citation.page == null && citation.t_start != null && citation.document_title === video.title;
}

function findCitation(turns: TutorTurn[], sourceId: string): Citation | undefined {
  for (const turn of turns) {
    const found = answerOf(turn)?.response?.citations.find((c) => c.source_id === sourceId);
    if (found) return found;
  }
  return undefined;
}

function useChunks(documentId: number): ChunkPreview[] | null {
  const [chunks, setChunks] = useState<ChunkPreview[] | null>(null);
  useEffect(() => {
    let alive = true;
    courseService
      .chunks(documentId)
      .then((list) => {
        if (alive) setChunks(list.filter((chunk) => chunk.t_start != null));
      })
      .catch(() => {
        if (alive) setChunks([]);
      });
    return () => {
      alive = false;
    };
  }, [documentId]);
  return chunks;
}

/** Videonun zaman çizgisi: şu anki konum ve cevabın dayandığı kısım; tıklayınca oraya gider. */
function Timeline({
  duration,
  time,
  moment,
  onSeek,
}: {
  duration: number | null;
  time: number;
  moment: VideoMoment | null;
  onSeek: (seconds: number) => void;
}) {
  if (!duration) return null;
  const percent = (seconds: number) => `${Math.min(100, Math.max(0, (seconds / duration) * 100))}%`;
  return (
    <div>
      <div
        role="slider"
        tabIndex={0}
        aria-label="Video zaman çizgisi"
        aria-valuemin={0}
        aria-valuemax={Math.round(duration)}
        aria-valuenow={Math.round(time)}
        aria-valuetext={formatTime(time)}
        onClick={(event) => {
          const box = event.currentTarget.getBoundingClientRect();
          onSeek(((event.clientX - box.left) / box.width) * duration);
        }}
        onKeyDown={(event) => {
          // Ok tuşları 10 sn, Home/End baş ve son; sayfa kaymasın diye varsayılan davranış durur.
          const target: Record<string, number> = {
            ArrowRight: Math.min(duration, time + 10),
            ArrowUp: Math.min(duration, time + 10),
            ArrowLeft: Math.max(0, time - 10),
            ArrowDown: Math.max(0, time - 10),
            Home: 0,
            End: Math.max(0, duration - 1),
          };
          if (!(event.key in target)) return;
          event.preventDefault();
          onSeek(target[event.key]);
        }}
        className="relative h-2 cursor-pointer rounded-full bg-line"
      >
        {moment && (
          <span
            className="absolute inset-y-0 rounded-full bg-marker"
            style={{ left: percent(moment.t_start), width: `calc(${percent(moment.t_end)} - ${percent(moment.t_start)})` }}
          />
        )}
        <span className="absolute inset-y-0 left-0 rounded-full bg-accent/60" style={{ width: percent(time) }} />
      </div>
      <p className="mt-1.5 flex flex-wrap justify-between gap-x-4 gap-y-0.5 font-mono text-xs text-graphite">
        <span>
          {formatTime(time)} / {formatTime(duration)}
        </span>
        {moment && <span>işaretli: cevabın dayandığı kısım ({formatTimeRange(moment.t_start, moment.t_end)})</span>}
      </p>
    </div>
  );
}

/**
 * Videoyla birlikte akan transkript; açılıp kapanır. Cevabın dayandığı kısım sarıyla (marker),
 * şu an konuşulan satır soldaki çizgiyle gösterilir; ikisi karışmasın diye renkleri ayrıdır.
 */
function Transcript({
  chunks,
  time,
  cited,
  moment,
  open,
  onToggle,
  onSeek,
}: {
  chunks: ChunkPreview[] | null;
  time: number;
  cited: Set<string>;
  moment: VideoMoment | null;
  open: boolean;
  onToggle: () => void;
  onSeek: (seconds: number) => void;
}) {
  const lines = useMemo(() => (chunks ? transcriptLines(chunks) : null), [chunks]);
  const current = useMemo(() => {
    if (!lines) return null;
    let found: TranscriptLine | null = null;
    for (const line of lines) if (line.t_start <= time) found = line;
    return found;
  }, [lines, time]);
  // Açılınca önce cevabın dayandığı kısma, yoksa şu an konuşulan satıra gidilir.
  const anchor = useMemo(() => {
    const marked = lines?.find((line) => isMarked(line, cited, moment));
    return marked ?? current;
  }, [lines, cited, moment, current]);
  const listRef = useRef<HTMLOListElement>(null);
  const followId = moment || cited.size > 0 ? anchor?.id : current?.id;

  useEffect(() => {
    if (!open || followId == null) return;
    // Yalnızca transkript kutusu kayar (scrollIntoView bütün sayfayı da kaydırırdı).
    const list = listRef.current;
    const item = list?.querySelector<HTMLElement>(`[data-chunk="${followId}"]`);
    if (list && item) list.scrollTo({ top: item.offsetTop - list.offsetTop - 8, behavior: "smooth" });
  }, [open, followId]);

  return (
    <section
      aria-label="Transkript"
      className={cx(
        "order-4 flex flex-col rounded-panel border border-line bg-surface lg:order-none",
        open && "max-h-80 min-h-[12rem] lg:max-h-none lg:min-h-0 lg:flex-1",
      )}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className={cx(
          "flex shrink-0 items-center gap-2 px-4 py-2 text-left text-sm font-semibold text-ink hover:bg-subtle",
          open ? "rounded-t-panel border-b border-line" : "rounded-panel",
        )}
      >
        <FileText size={14} aria-hidden className="text-graphite" />
        Transkript
        <span className="min-w-0 flex-1 truncate font-normal text-graphite">
          <span className="hidden sm:inline">· videoyla birlikte akar</span>
        </span>
        <span className="font-normal text-graphite">{open ? "Gizle" : "Göster"}</span>
        <ChevronDown size={14} aria-hidden className={cx("text-graphite transition-transform", open && "rotate-180")} />
      </button>
      {!open ? null : lines === null ? (
        <div className="p-4">
          <SkeletonRows rows={3} />
        </div>
      ) : lines.length === 0 ? (
        <p className="p-4 text-sm text-graphite">Bu videonun transkripti yok.</p>
      ) : (
        <ol ref={listRef} className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
          {lines.map((line) => {
            const isCurrent = line.id === current?.id;
            const isCited = isMarked(line, cited, moment);
            return (
              <li key={line.id} data-chunk={line.id}>
                <button
                  type="button"
                  onClick={() => onSeek(line.t_start)}
                  aria-current={isCurrent ? "true" : undefined}
                  className={cx(
                    "flex w-full gap-3 rounded-control border-l-2 px-2 py-1.5 text-left text-sm leading-relaxed",
                    isCurrent ? "border-accent" : "border-transparent",
                    isCited ? "bg-marker/40 text-ink" : isCurrent ? "text-ink" : "text-ink-2 hover:bg-subtle",
                  )}
                >
                  <span className="w-12 shrink-0 font-mono text-xs text-graphite tabular-nums">
                    {formatTime(line.t_start)}
                  </span>
                  <span className={cx(isCurrent && "font-medium")}>{line.text}</span>
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

interface TranscriptLine {
  id: number;
  t_start: number;
  t_end: number;
  text: string;
}

function isMarked(line: TranscriptLine, cited: Set<string>, moment: VideoMoment | null): boolean {
  return cited.has(String(line.id)) || (moment != null && line.t_start < moment.t_end && line.t_end > moment.t_start);
}

/**
 * Arama için video parçaları birbirinin üstüne biner: bir parçanın son cümleleri sonrakinin
 * başında tekrar eder. Transkriptte her cümle bir kez görünsün diye tekrar eden baş kesilir.
 */
function transcriptLines(chunks: ChunkPreview[]): TranscriptLine[] {
  const lines: TranscriptLine[] = [];
  let previous: string[] = [];
  for (const chunk of chunks) {
    const words = chunk.text.split(/\s+/).filter(Boolean);
    const repeated = overlapLength(previous, words);
    previous = words;
    const text = words.slice(repeated).join(" ");
    if (!text) continue;
    lines.push({ id: chunk.id, t_start: chunk.t_start ?? 0, t_end: chunk.t_end ?? chunk.t_start ?? 0, text });
  }
  return lines;
}

/** `before`'ın sonu ile `after`'ın başı en fazla kaç kelime aynı. */
function overlapLength(before: string[], after: string[]): number {
  for (let size = Math.min(before.length, after.length); size > 0; size--) {
    let same = true;
    for (let index = 0; index < size && same; index++) {
      same = before[before.length - size + index] === after[index];
    }
    if (same) return size;
  }
  return 0;
}

/** Sohbette bir soru ve cevabı: cevabın kaynağı önce yazılır (videodan / dokümandan). */
function StudyTurn({
  turn,
  askedAt,
  frames,
  video,
  isLatest,
  onQuickAction,
  onRetry,
  onAsk,
  onSelectSource,
  onSeek,
  onResume,
}: {
  turn: TutorTurn;
  askedAt: number | undefined;
  frames: FrameRef[] | null;
  video: DocumentOut;
  isLatest: boolean;
  onQuickAction: (action: QuickAction) => void;
  onRetry: () => void;
  onAsk: (text: string) => void;
  onSelectSource: (sourceId: string) => void;
  onSeek: (seconds: number) => void;
  onResume: () => void;
}) {
  const answer = answerOf(turn);
  const response = answer?.response;
  const moment = response?.video_moment;
  const fromVideo = (response?.citations ?? []).filter((c) => isThisVideo(c, video)).length;
  const fromDocs = (response?.citations ?? []).length - fromVideo;
  return (
    <article className="flex flex-col gap-3" aria-label={turn.question}>
      <p className="self-end rounded-panel bg-subtle px-3 py-2 text-sm text-ink">
        {turn.question}
        {askedAt != null && <span className="ml-2 font-mono text-xs text-graphite">· {formatTime(askedAt)}</span>}
      </p>
      {askedAt != null && (
        <FrameAtMoment
          frames={frames}
          seconds={askedAt}
          heading="Durdurduğun anda ekranda"
          onSeek={onSeek}
          cited={citedFrameIds(response?.citations)}
        />
      )}
      {response && (moment || fromVideo > 0 || fromDocs > 0) && (
        <p className="flex flex-wrap items-center gap-2 text-xs">
          {moment && (
            <button
              type="button"
              onClick={() => onSeek(moment.t_start)}
              className="inline-flex items-center gap-1 rounded-full bg-accent-soft px-2.5 py-1 font-medium text-accent"
            >
              <PlayCircle size={12} aria-hidden />
              Videodan · {formatTimeRange(moment.t_start, moment.t_end)}
            </button>
          )}
          {fromDocs > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full border border-line px-2.5 py-1 text-graphite">
              <FileText size={12} aria-hidden />
              {fromDocs} doküman kaynağı
            </span>
          )}
        </p>
      )}
      {answer && (
        <AnswerBlock
          turn={answer}
          isLatest={isLatest}
          onQuickAction={onQuickAction}
          onRetry={onRetry}
          selectedSourceId={null}
          onSelectSource={onSelectSource}
        />
      )}
      <TurnExtras
        turn={turn}
        isLatest={isLatest}
        hasAnswer={answer !== null}
        onQuickAction={onQuickAction}
        onRetry={onRetry}
        onAsk={onAsk}
        selectedSourceId={null}
        onSelectSource={onSelectSource}
      />
      {isLatest && turn.done && (
        <Button size="sm" icon={PlayCircle} className="self-start" onClick={onResume}>
          Videoya devam et
        </Button>
      )}
    </article>
  );
}
