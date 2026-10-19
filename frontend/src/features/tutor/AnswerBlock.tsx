import {
  CircleAlert,
  FlaskConical,
  RotateCcw,
  SearchX,
  ServerOff,
  Target,
  WandSparkles,
} from "lucide-react";

import type { QuickAction } from "../../services/tutorService";
import { reflow } from "../../text";
import Button from "../../ui/Button";
import { LogoMark } from "../../ui/Logo";
import CitedText from "./CitedText";
import { classifyResponse } from "./outcome";
import RetrievalDetails from "./RetrievalDetails";
import SourceCards from "./SourceCards";
import type { SelectSourceProps, Turn, TutorFailure } from "./types";

interface AnswerBlockProps extends SelectSourceProps {
  turn: Turn;
  /** Yalnızca son cevapta hızlı eylemler ve "Tekrar sor" gösterilir. */
  isLatest: boolean;
  onQuickAction: (action: QuickAction) => void;
  onPractice: () => void;
  onRetry: () => void;
}

const FAILURE_COPY: Record<TutorFailure["kind"], { title: string; description: string }> = {
  unavailable: {
    title: "Ders servisine ulaşılamıyor",
    description: "Bağlantını kontrol edip birkaç saniye sonra tekrar dene. Sorun sürerse eğitmenine haber ver.",
  },
  temporary: {
    title: "Geçici bir sorun oluştu",
    description: "Cevap hazırlanırken bir sorun çıktı. Tekrar sorarak yeniden deneyebilirsin.",
  },
  rejected: {
    title: "Soru gönderilemedi",
    description: "",
  },
};

/** Bir sorunun cevabı: arıyor → yazıyor → doğrulanmış cevap / ret / hata. */
export default function AnswerBlock({
  turn,
  isLatest,
  onQuickAction,
  onPractice,
  onRetry,
  selectedSourceId,
  onSelectSource,
}: AnswerBlockProps) {
  const select = { selectedSourceId, onSelectSource };
  return (
    <div className="flex gap-3">
      <LogoMark className="mt-0.5 size-5 shrink-0 text-ink" />
      <div className="min-w-0 flex-1">
        <Body
          turn={turn}
          isLatest={isLatest}
          onQuickAction={onQuickAction}
          onPractice={onPractice}
          onRetry={onRetry}
          {...select}
        />
      </div>
    </div>
  );
}

function RetryButton({ onRetry }: { onRetry: () => void }) {
  return (
    <Button size="sm" icon={RotateCcw} onClick={onRetry}>
      Tekrar sor
    </Button>
  );
}

function Body({ turn, isLatest, onQuickAction, onPractice, onRetry, ...select }: AnswerBlockProps) {
  if (turn.failure) {
    const copy = FAILURE_COPY[turn.failure.kind];
    const description = turn.failure.detail || copy.description;
    return (
      <div role="alert" className="flex flex-col items-start gap-3">
        <div>
          <p className="flex items-center gap-2 text-base font-medium text-danger">
            {turn.failure.kind === "unavailable" ? (
              <ServerOff size={16} aria-hidden />
            ) : (
              <CircleAlert size={16} aria-hidden />
            )}
            {copy.title}
          </p>
          {description && <p className="mt-1 text-base text-graphite">{description}</p>}
        </div>
        {isLatest && <RetryButton onRetry={onRetry} />}
      </div>
    );
  }

  const { response } = turn;
  if (!response) {
    if (turn.streamText && turn.hits) {
      const hits = turn.hits;
      return (
        <div className="text-md leading-7 whitespace-pre-wrap text-ink">
          <CitedText
            text={turn.streamText}
            pattern={/(\[S\d+\])/}
            resolve={(n) => {
              const hit = hits[n - 1];
              return hit && { source_id: hit.source_id, document_title: hit.document_title, page: hit.page };
            }}
            {...select}
          />
          <span aria-hidden className="ml-0.5 inline-block h-4 w-[7px] translate-y-0.5 animate-pulse bg-accent" />
        </div>
      );
    }
    return (
      <p role="status" className="flex h-7 items-center gap-2 text-base text-graphite">
        {turn.hits
          ? `${turn.hits.length} ilgili bölüm bulundu, cevap hazırlanıyor`
          : "Ders materyalinde aranıyor"}
        <span aria-hidden className="flex gap-1">
          <span className="thinking-dot size-1 rounded-full bg-graphite" />
          <span className="thinking-dot size-1 rounded-full bg-graphite" />
          <span className="thinking-dot size-1 rounded-full bg-graphite" />
        </span>
      </p>
    );
  }

  const outcome = classifyResponse(response);

  if (outcome === "not_generated") {
    return (
      <div className="flex flex-col gap-4">
        <div role="alert" className="flex flex-col items-start gap-3">
          <div>
            <p className="flex items-center gap-2 text-base font-medium text-ink">
              <CircleAlert size={16} aria-hidden className="text-warning" />
              Cevap hazırlanamadı
            </p>
            <p className="mt-1 text-base text-graphite">
              Bu soru için ders materyalinden dayanaklı bir cevap yazılamadı. Tekrar sorabilir ya da
              soruyu daha açık yazabilirsin.
            </p>
          </div>
          {isLatest && <RetryButton onRetry={onRetry} />}
        </div>
        {response.suggested_sources.length > 0 && (
          <div>
            <p className="mb-2 text-sm text-graphite">Notlardaki en yakın bölümler</p>
            <SourceCards citations={response.suggested_sources} numbered={false} {...select} />
          </div>
        )}
        <RetrievalDetails response={response} {...select} />
      </div>
    );
  }

  if (outcome === "out_of_scope") {
    return (
      <div className="flex flex-col gap-4">
        <div className="rounded-panel border border-line bg-canvas px-4 py-3">
          <p className="flex items-center gap-2 text-base font-medium text-ink">
            <SearchX size={16} aria-hidden className="text-graphite" />
            Bu soru için ders materyalinde yeterli bilgi bulunamadı
          </p>
          <p className="mt-1 text-base text-graphite">{response.decline_reason}</p>
        </div>
        {response.suggested_sources.length > 0 && (
          <div>
            <p className="mb-2 text-sm text-graphite">Notlardaki en yakın bölümler</p>
            <SourceCards citations={response.suggested_sources} numbered={false} {...select} />
          </div>
        )}
        <RetrievalDetails response={response} {...select} />
      </div>
    );
  }

  const extractive = outcome === "ai_unavailable";
  return (
    <div className="flex flex-col gap-4">
      {extractive && (
        <p className="text-sm text-graphite">
          Yapay zekâ şu an kullanılamıyor; ders materyalindeki ilgili bölüm olduğu gibi gösteriliyor.
        </p>
      )}
      <div
        className={
          extractive
            ? "border-l-2 border-marker pl-4 font-serif text-md leading-7 whitespace-pre-wrap text-ink"
            : "text-md leading-7 whitespace-pre-wrap text-ink"
        }
      >
        <CitedText
          text={extractive ? reflow(stripIntro(response.answer ?? "")) : (response.answer ?? "")}
          pattern={/(\[\d+\])/}
          resolve={(n) => response.citations[n - 1]}
          {...select}
        />
      </div>

      <div>
        <p className="mb-2 text-sm text-graphite">Kaynaklar</p>
        <SourceCards citations={response.citations} {...select} />
      </div>

      {isLatest && !extractive && (
        <div className="flex flex-wrap gap-1.5">
          <Button size="sm" icon={WandSparkles} onClick={() => onQuickAction("simpler")}>
            Daha basit anlat
          </Button>
          <Button size="sm" icon={FlaskConical} onClick={() => onQuickAction("example")}>
            Örnek ver
          </Button>
          <Button size="sm" icon={Target} onClick={onPractice}>
            Bu konuyu çalış
          </Button>
        </div>
      )}
      <RetrievalDetails response={response} {...select} />
    </div>
  );
}

/** LLM'siz cevabın ilk satırı ("…en uygun kısım:") üstteki notla aynı şeyi söyler. */
function stripIntro(answer: string): string {
  const [first, ...rest] = answer.split("\n\n");
  return rest.length > 0 && first.trimEnd().endsWith(":") ? rest.join("\n\n") : answer;
}
