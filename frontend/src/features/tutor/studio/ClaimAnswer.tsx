import { FlaskConical, HelpCircle, PlayCircle, SearchX, WandSparkles } from "lucide-react";

import type { AskResponse, Citation } from "../../../api/types";
import { citationLabel } from "../../../labels";
import type { QuickAction } from "../../../services/tutorService";
import Button from "../../../ui/Button";
import { cx } from "../../../ui/cx";
import { distinctDocuments, type Claim, type StructuredAnswer } from "../claims";
import RichText from "../RichText";
import VerificationStrip from "./VerificationStrip";

/** Bundan uzun ilk cümle daha küçük puntoyla gösterilir. */
const LONG_LEAD = 80;

interface ClaimAnswerProps {
  question: string;
  response: AskResponse;
  answer: StructuredAnswer;
  selectedClaim: number | null;
  onSelectClaim: (claim: Claim) => void;
  /** Seçili iddia satırı: kanıt izi buradan başlar. */
  claimRef: (element: HTMLElement | null) => void;
  onSelectSource: (sourceId: string) => void;
  isLatest: boolean;
  onQuickAction: (action: QuickAction) => void;
  elapsedMs: number | null;
}

/**
 * Doğrulanmış cevap, iddia iddia: ilk cümle başlık, kalanlar numaralı satırlar. Bir satıra
 * dokununca dayandığı kaynak sağda açılır ve satırla kaynak arasında iz çizilir.
 */
export default function ClaimAnswer({
  question,
  response,
  answer,
  selectedClaim,
  onSelectClaim,
  claimRef,
  onSelectSource,
  isLatest,
  onQuickAction,
  elapsedMs,
}: ClaimAnswerProps) {
  const resolve = (number: number): Citation | undefined => response.citations[number - 1];
  const all = answer.lead ? [answer.lead, ...answer.claims] : answer.claims;
  const video = response.citations.find((citation) => citation.page == null && citation.t_start != null);

  return (
    <article className="flex flex-col gap-6">
      <p className="max-w-[46rem] self-start rounded-panel border border-line bg-surface px-4 py-3 text-base text-ink-2 shadow-card">
        {question}
      </p>

      {answer.lead && (
        <h2
          className={cx(
            "font-semibold tracking-tight text-balance text-ink",
            // Uzun ilk cümle dev bir başlık bloğuna dönüşmesin.
            answer.lead.text.length > LONG_LEAD
              ? "max-w-[36ch] text-[1.625rem] leading-[1.2]"
              : "max-w-[24ch] text-[2.125rem] leading-[1.12]",
          )}
        >
          <RichText text={answer.lead.text} inline />
          <CitationChips claim={answer.lead} resolve={resolve} onSelectSource={onSelectSource} />
        </h2>
      )}

      <ol className="flex flex-col" aria-label="Cevabın iddiaları; ok tuşlarıyla gezilebilir">
        {answer.claims.map((claim) => {
          const selected = claim.number === selectedClaim;
          const sources = claim.citations.map(resolve).filter((item): item is Citation => Boolean(item));
          return (
            <li key={claim.number} className="border-t border-dashed border-line first:border-t-0">
              <button
                type="button"
                ref={selected ? claimRef : undefined}
                data-claim={claim.number}
                onClick={() => onSelectClaim(claim)}
                aria-pressed={selected}
                className="group grid w-full grid-cols-[2rem_minmax(0,1fr)] items-start gap-3 py-3.5 text-left"
              >
                <span
                  aria-hidden
                  className={cx(
                    "flex size-7 items-center justify-center rounded-full border text-xs font-semibold tabular-nums transition-colors",
                    selected
                      ? "border-accent bg-accent text-on-accent"
                      : "border-line-strong text-graphite group-hover:border-accent group-hover:text-accent",
                  )}
                >
                  {claim.number}
                </span>
                <span className="flex min-w-0 flex-col gap-1.5">
                  <span className="text-md leading-7 text-ink">
                    <span className={selected ? "rounded-[2px] bg-marker-soft box-decoration-clone px-0.5 shadow-[inset_0_-2px_0_var(--color-marker)]" : undefined}>
                      <RichText text={claim.text} inline />
                    </span>
                  </span>
                  {selected && sources.length > 0 && (
                    <span className="font-mono text-xs text-graphite">
                      {sources.map((source) => citationLabel(source)).join(" · ")}
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ol>

      {response.coverage_gap && (
        <p className="flex max-w-[46rem] items-start gap-2 rounded-panel border border-line bg-surface px-3 py-2 text-sm text-graphite">
          <SearchX size={14} aria-hidden className="mt-0.5 shrink-0" />
          <span>
            <span className="font-medium text-ink-2">Materyalde olmayan kısım: </span>
            {response.coverage_gap}
          </span>
        </p>
      )}

      <div className="flex flex-col gap-3 border-t border-line pt-4">
        <VerificationStrip
          claims={all.length}
          removed={response.unsupported_removed}
          documents={distinctDocuments(response.citations.map((citation) => citation.document_title))}
          elapsedMs={elapsedMs}
        />
        {isLatest && (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" icon={HelpCircle} onClick={() => onQuickAction("quiz")}>
              Bunu bana soru olarak sor
            </Button>
            {video && (
              <Button size="sm" icon={PlayCircle} onClick={() => onSelectSource(video.source_id)}>
                Videoda göster
              </Button>
            )}
            <Button size="sm" icon={WandSparkles} onClick={() => onQuickAction("simpler")}>
              Daha basit anlat
            </Button>
            <Button size="sm" icon={FlaskConical} onClick={() => onQuickAction("example")}>
              Örnek ver
            </Button>
          </div>
        )}
      </div>
    </article>
  );
}

/** Başlık cümlesinin kaynak işaretleri: küçük, tıklanabilir sayfa etiketleri. */
function CitationChips({
  claim,
  resolve,
  onSelectSource,
}: {
  claim: Claim;
  resolve: (number: number) => Citation | undefined;
  onSelectSource: (sourceId: string) => void;
}) {
  return (
    <>
      {claim.citations.map((number) => {
        const citation = resolve(number);
        if (!citation) return null;
        return (
          <button
            key={number}
            type="button"
            onClick={() => onSelectSource(citation.source_id)}
            aria-label={`Kaynak: ${citationLabel(citation)}`}
            title={citationLabel(citation)}
            className="ml-2 inline-flex h-6 -translate-y-1.5 items-center rounded-[3px] bg-marker-soft px-1.5 align-middle font-mono text-[11px] font-semibold tracking-normal text-ink hover:bg-marker"
          >
            {citation.page != null ? `s.${citation.page}` : number}
          </button>
        );
      })}
    </>
  );
}
