import { Check, Copy, ExternalLink, FileText, PlayCircle, X } from "lucide-react";
import { useState } from "react";

import type { DocumentOut } from "../../../api/types";
import { materialLabel } from "../../../labels";
import type { Course } from "../../../services/courseService";
import { formatTimeRange } from "../../../text";
import Button from "../../../ui/Button";
import EmptyState from "../../../ui/EmptyState";
import IconButton from "../../../ui/IconButton";
import Skeleton from "../../../ui/Skeleton";
import PageImage from "../PageImage";
import { useSourceDetail } from "../useSourceDetail";
import ProvenanceTable from "./ProvenanceTable";

/**
 * Kanıt paneli: seçilen iddianın dayandığı yer. PDF'te gerçek sayfa ve işaretli satırlar,
 * metinde alıntılanan bölüm, videoda zaman aralığı; altında kaynağın künyesi.
 * `anchorRef`: kanıt izinin bağlanacağı öğe (ilk işaretli satır ya da alıntı metni).
 */
export default function EvidencePanel({
  sourceId,
  course,
  documents,
  claimNumber,
  anchorRef,
  onClose,
}: {
  sourceId: string;
  course: Course;
  documents: DocumentOut[] | null;
  /** Kaynağı seçilen iddianın numarası; panelin altında "2 → Slayt 6, s.14" olarak yazılır. */
  claimNumber: number | null;
  anchorRef: (element: HTMLElement | null) => void;
  onClose: () => void;
}) {
  const { source, failure, retry } = useSourceDetail(sourceId);
  const [copied, setCopied] = useState(false);
  const document = source ? documents?.find((item) => item.id === source.document_id) : undefined;
  const isPdf = Boolean(source?.page_image_url);
  const isVideo = source?.material_type === "video";
  const location = source
    ? source.page != null
      ? `s.${source.page}${document?.page_count ? ` / ${document.page_count}` : ""}`
      : source.t_start != null
        ? formatTimeRange(source.t_start, source.t_end)
        : materialLabel(source.material_type)
    : null;

  return (
    <aside
      aria-label="Kaynak"
      onKeyDown={(event) => event.key === "Escape" && onClose()}
      className="flex flex-col gap-3"
    >
      <header className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          {source ? (
            <p className="truncate text-base font-semibold text-ink">{source.document_title}</p>
          ) : failure ? null : (
            <Skeleton className="h-4 w-48" />
          )}
        </div>
        {location && <span className="shrink-0 font-mono text-xs text-graphite">{location}</span>}
        {source && (
          <IconButton
            icon={copied ? Check : Copy}
            label={copied ? "Kaynak kopyalandı" : "Kaynağı kopyala"}
            size="sm"
            onClick={() => {
              const reference = `${source.document_title}${location ? `, ${location}` : ""} (${course.code} ${course.name})`;
              void navigator.clipboard?.writeText(reference).then(() => {
                setCopied(true);
                window.setTimeout(() => setCopied(false), 1600);
              });
            }}
          />
        )}
        <IconButton icon={X} label="Kaynağı kapat" size="sm" onClick={onClose} />
      </header>

      {failure ? (
        <div role="alert" className="rounded-panel border border-line bg-surface p-4">
          <EmptyState
            icon={FileText}
            tone="danger"
            title={failure === "missing" ? "Kaynak bulunamadı" : "Kaynak açılamadı"}
            description={
              failure === "missing"
                ? "Bu bölüm materyalden kaldırılmış olabilir."
                : "Kaynak şu an yüklenemedi. Bağlantını kontrol edip tekrar dene."
            }
            action={failure === "failed" ? <Button onClick={retry}>Tekrar dene</Button> : undefined}
          />
        </div>
      ) : !source ? (
        <Skeleton className="aspect-[1/1.25] w-full rounded-panel" />
      ) : (
        <div className="flex flex-col gap-4 rounded-panel border border-line bg-sheet p-4 shadow-lift">
          {isPdf ? (
            <PageImage
              key={source.source_id}
              src={source.page_image_url!}
              alt={`${source.document_title}, sayfa ${source.page}`}
              highlights={source.highlights}
              anchorRef={anchorRef}
            />
          ) : isVideo ? (
            <div className="flex flex-col gap-3">
              <p className="flex items-center gap-2 font-mono text-sm text-ink">
                <PlayCircle size={16} aria-hidden className="text-accent" />
                {source.t_start != null ? formatTimeRange(source.t_start, source.t_end) : "Ders videosu"}
              </p>
              <blockquote className="border-l-2 border-marker pl-3 font-mono text-sm leading-relaxed whitespace-pre-wrap text-ink">
                <span key={source.source_id} ref={anchorRef} className="marker-sweep">
                  {source.text}
                </span>
              </blockquote>
            </div>
          ) : (
            <p className="font-mono text-sm leading-relaxed whitespace-pre-wrap text-ink">
              <span key={source.source_id} ref={anchorRef} className="marker-sweep">
                {source.text}
              </span>
            </p>
          )}

          {isPdf && (
            <details>
              <summary className="cursor-pointer text-sm text-graphite hover:text-ink">
                Alıntılanan bölümü metin olarak göster
              </summary>
              <p className="mt-2 font-mono text-sm leading-relaxed whitespace-pre-wrap text-ink">
                {source.text}
              </p>
            </details>
          )}

          <ProvenanceTable course={course} source={source} document={document} />
        </div>
      )}

      {source && (
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 font-mono text-xs">
          {claimNumber != null && (
            <span className="text-accent">
              {claimNumber} → {source.document_title}
              {location ? `, ${location}` : ""}
            </span>
          )}
          <span className="text-graphite">
            {isPdf && source.highlights.length > 0
              ? "İşaretli satırlar cevapta kullanılan bölümü gösterir. Cevapla karşılaştırıp kontrol et."
              : "Cevapta kullanılan bölüm burada. Cevapla karşılaştırıp kontrol et."}
          </span>
          {source.media_url && (
            <a href={source.media_url} target="_blank" rel="noreferrer" className="link inline-flex items-center gap-1">
              <ExternalLink size={12} aria-hidden />
              {isPdf ? "Dosyada aç" : isVideo ? "Videoda aç" : "İndir"}
            </a>
          )}
        </div>
      )}
    </aside>
  );
}
