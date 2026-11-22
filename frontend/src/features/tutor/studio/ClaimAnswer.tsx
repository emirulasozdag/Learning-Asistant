import { ClipboardCheck, FlaskConical, PlayCircle, SearchX, WandSparkles } from "lucide-react";

import type { AskResponse, Citation } from "../../../api/types";
import { citationLabel } from "../../../labels";
import type { QuickAction } from "../../../services/tutorService";
import Button from "../../../ui/Button";
import Card from "../../../ui/Card";
import { cx } from "../../../ui/cx";
import { CitationMark, FootnoteMark } from "../CitedText";
import { distinctDocuments, type Claim, type StructuredAnswer } from "../claims";
import RichText from "../RichText";
import VerificationStrip from "./VerificationStrip";

/** Bundan uzun ilk cümle bir alt basamakta (text-xl) gösterilir. */
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
      <Card variant="inset" padding="sm" className="max-w-[46rem] self-start">
        <p className="text-base text-ink-2">{question}</p>
      </Card>

      {answer.lead && (
        // Cevabın tezi: okuma yazısıyla (serif) başlık; uzun ilk cümle bir basamak küçük.
        <h2
          className={cx(
            "font-serif font-semibold text-balance text-ink",
            answer.lead.text.length > LONG_LEAD ? "max-w-[40ch] text-xl" : "max-w-[28ch] text-2xl",
          )}
        >
          <RichText text={answer.lead.text} inline />
          <LeadCitations claim={answer.lead} resolve={resolve} onSelectSource={onSelectSource} />
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
                  {/* Okuma metni: serif, rahat satır aralığı; sonunda dayandığı kaynakların dipnot işaretleri. */}
                  <span className="font-serif text-lg leading-relaxed text-ink">
                    <span className={selected ? "rounded-sm bg-marker-soft box-decoration-clone px-0.5" : undefined}>
                      <RichText text={claim.text} inline />
                    </span>
                    {claim.citations.map((number) =>
                      resolve(number) ? <FootnoteMark key={number} number={number} className="ml-1" /> : null,
                    )}
                  </span>
                  {selected && sources.length > 0 && (
                    <span className="flex flex-wrap gap-x-3 gap-y-1 text-sm text-graphite">
                      {claim.citations.map((number) => {
                        const source = resolve(number);
                        if (!source) return null;
                        return (
                          <span key={number} className="inline-flex items-center gap-1.5">
                            <FootnoteMark number={number} />
                            {citationLabel(source)}
                          </span>
                        );
                      })}
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ol>

      {response.coverage_gap && (
        <Card variant="inset" padding="sm" className="flex max-w-[46rem] items-start gap-2 text-sm text-graphite">
          <SearchX size={15} aria-hidden className="mt-0.5 shrink-0" />
          <p>
            <span className="font-medium text-ink-2">Materyalde olmayan kısım: </span>
            {response.coverage_gap}
          </p>
        </Card>
      )}

      <div className="flex flex-col gap-3 border-t border-line pt-4">
        <VerificationStrip
          claims={all.length}
          removed={response.unsupported_removed}
          check={response.claim_check}
          // Video alıntısı (zamanlı, sayfasız) "video" olarak ayrı sayılır (#102).
          videos={distinctDocuments(
            response.citations.filter((c) => c.page == null && c.t_start != null).map((c) => c.document_title),
          )}
          documents={distinctDocuments(
            response.citations.filter((c) => !(c.page == null && c.t_start != null)).map((c) => c.document_title),
          )}
          elapsedMs={elapsedMs}
        />
        {isLatest && (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" icon={ClipboardCheck} onClick={() => onQuickAction("quiz")}>
              Beni bu konuda test et
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

/** Başlık cümlesinin kaynakları: tıklanabilir dipnot işaretleri (cevaptaki numarayla aynı). */
function LeadCitations({
  claim,
  resolve,
  onSelectSource,
}: {
  claim: Claim;
  resolve: (number: number) => Citation | undefined;
  onSelectSource: (sourceId: string) => void;
}) {
  return (
    // Başlığın büyük puntosunda işaret metin boyutunda kalsın.
    <span className="ml-1 inline-block align-baseline text-base font-normal">
      {claim.citations.map((number) => {
        const citation = resolve(number);
        if (!citation) return null;
        return (
          <CitationMark key={number} number={number} citation={citation} active={false} onSelect={onSelectSource} />
        );
      })}
    </span>
  );
}
