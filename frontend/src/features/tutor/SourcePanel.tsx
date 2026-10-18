import { ExternalLink, FileText, X } from "lucide-react";
import { useEffect, useState } from "react";

import type { Highlight, SourceDetail } from "../../api/types";
import Sheet from "../../components/Sheet";
import { materialLabel } from "../../labels";
import { tutorService } from "../../services/tutorService";
import { reflow } from "../../text";
import { buttonClasses } from "../../ui/buttonStyles";
import EmptyState from "../../ui/EmptyState";
import IconButton from "../../ui/IconButton";
import Skeleton from "../../ui/Skeleton";

/** Seçilen alıntının ders materyalindeki yeri: gerçek PDF sayfası + işaretli satırlar. */
export default function SourcePanel({ sourceId, onClose }: { sourceId: string; onClose: () => void }) {
  const [source, setSource] = useState<SourceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    tutorService
      .source(sourceId)
      .then((detail) => {
        if (!cancelled) {
          setSource(detail);
          setError(null);
        }
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [sourceId]);

  const current = source?.source_id === sourceId ? source : null;
  const isPdf = Boolean(current?.page_image_url);

  return (
    <aside aria-label="Kaynak" className="flex h-full min-h-0 flex-col bg-canvas">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-surface px-4">
        <FileText size={16} aria-hidden className="shrink-0 text-graphite" />
        <div className="min-w-0 flex-1">
          {current ? (
            <>
              <p className="truncate text-base font-medium text-ink">{current.document_title}</p>
              <p className="truncate text-sm text-graphite">
                {materialLabel(current.material_type)}
                {current.page ? `, sayfa ${current.page}` : ""}
              </p>
            </>
          ) : (
            <div className="flex flex-col gap-1.5">
              <Skeleton className="h-3 w-40" />
              <Skeleton className="h-2.5 w-24" />
            </div>
          )}
        </div>
        {current?.media_url && (
          <a
            href={current.media_url}
            target="_blank"
            rel="noreferrer"
            className={buttonClasses("ghost", "sm")}
          >
            <ExternalLink size={14} aria-hidden />
            {isPdf ? "PDF'te aç" : "İndir"}
          </a>
        )}
        <IconButton icon={X} label="Kaynağı kapat" size="sm" onClick={onClose} />
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto p-5">
        {error ? (
          <EmptyState icon={FileText} tone="danger" title="Kaynak açılamadı" description={error} />
        ) : !current ? (
          <Skeleton className="aspect-[1/1.3] w-full" />
        ) : isPdf ? (
          <>
            <PageImage
              key={current.source_id}
              src={current.page_image_url!}
              alt={`${current.document_title}, sayfa ${current.page}`}
              highlights={current.highlights}
            />
            <p className="mt-3 text-sm text-graphite">
              {current.highlights.length > 0
                ? "İşaretli satırlar cevabın dayandığı bölümdür."
                : "Cevabın dayandığı bölüm bu sayfada."}
            </p>
            <details className="mt-4">
              <summary className="cursor-pointer text-sm text-graphite hover:text-ink">
                Alıntılanan bölümü metin olarak göster
              </summary>
              <div className="mt-3">
                <Sheet page={current.page}>
                  <p className="text-md leading-relaxed whitespace-pre-wrap">{reflow(current.text)}</p>
                </Sheet>
              </div>
            </details>
          </>
        ) : (
          <Sheet page={current.page}>
            <p className="text-md leading-relaxed whitespace-pre-wrap">
              <span key={current.source_id} className="marker-sweep">
                {reflow(current.text)}
              </span>
            </p>
          </Sheet>
        )}
      </div>
    </aside>
  );
}

function PageImage({ src, alt, highlights }: { src: string; alt: string; highlights: Highlight[] }) {
  const [loaded, setLoaded] = useState(false);
  return (
    <figure className="relative overflow-hidden rounded-sm bg-surface shadow-page">
      <img
        src={src}
        alt={alt}
        onLoad={() => setLoaded(true)}
        className={`block w-full transition-opacity duration-300 ${loaded ? "opacity-100" : "opacity-0"}`}
      />
      {!loaded && <Skeleton className="absolute inset-0 rounded-none" />}
      {loaded &&
        highlights.map((box, index) => (
          <span
            key={index}
            aria-hidden
            className="marker-box"
            style={{
              left: `${box.x * 100}%`,
              top: `${box.y * 100}%`,
              width: `${box.width * 100}%`,
              height: `${box.height * 100}%`,
              animationDelay: `${index * 45}ms`,
            }}
          />
        ))}
    </figure>
  );
}
