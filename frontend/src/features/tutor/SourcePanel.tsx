import { ExternalLink, FileText, X } from "lucide-react";
import { useEffect, useState } from "react";

import { ApiError } from "../../api/client";
import type { Highlight, SourceDetail } from "../../api/types";
import Sheet from "../../components/Sheet";
import { materialLabel } from "../../labels";
import { tutorService } from "../../services/tutorService";
import { formatTimeRange } from "../../text";
import Button from "../../ui/Button";
import { buttonClasses } from "../../ui/buttonStyles";
import EmptyState from "../../ui/EmptyState";
import IconButton from "../../ui/IconButton";
import Skeleton from "../../ui/Skeleton";

/**
 * Seçilen alıntının ders materyalindeki yeri: gerçek PDF sayfası + işaretli satırlar.
 * Kaynak değişince dışarıdan `key` ile yeniden oluşturulur; eski içerik ve hata kalmaz.
 * `modal`: dar ekranda diyalogun içinde açılır (kök eleman `aside` değil `div`).
 */
export default function SourcePanel({
  sourceId,
  onClose,
  modal = false,
}: {
  sourceId: string;
  onClose: () => void;
  modal?: boolean;
}) {
  const [source, setSource] = useState<SourceDetail | null>(null);
  /** "missing": kaynak yok (404), tekrar denemek işe yaramaz. "failed": ulaşılamadı. */
  const [failure, setFailure] = useState<"missing" | "failed" | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    tutorService
      .source(sourceId, controller.signal)
      .then((detail) => {
        if (!cancelled) setSource(detail);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setFailure(reason instanceof ApiError && reason.status === 404 ? "missing" : "failed");
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [sourceId, attempt]);

  function retry() {
    setFailure(null);
    setAttempt((count) => count + 1);
  }

  const current = source?.source_id === sourceId ? source : null;
  const isPdf = Boolean(current?.page_image_url);
  const isVideo = current?.material_type === "video";
  const Root = modal ? "div" : "aside";

  return (
    <Root
      aria-label={modal ? undefined : "Kaynak"}
      onKeyDown={modal ? undefined : (event) => event.key === "Escape" && onClose()}
      className="flex h-full min-h-0 flex-col bg-canvas"
    >
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-surface px-4">
        <FileText size={16} aria-hidden className="shrink-0 text-graphite" />
        <div className="min-w-0 flex-1">
          {current ? (
            <>
              <p className="truncate text-base font-medium text-ink">{current.document_title}</p>
              <p className="truncate text-sm text-graphite">
                {materialLabel(current.material_type)}
                {current.page ? `, sayfa ${current.page}` : ""}
                {current.page == null && current.t_start != null
                  ? `, ${formatTimeRange(current.t_start, current.t_end)}`
                  : ""}
              </p>
            </>
          ) : failure ? null : (
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
            {isPdf ? "PDF'te aç" : isVideo ? "Videoda aç" : "İndir"}
          </a>
        )}
        <IconButton icon={X} label="Kaynağı kapat" size="sm" onClick={onClose} />
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto p-5">
        {failure ? (
          <div role="alert">
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
                ? "İşaretli satırlar cevapta kullanılan bölümü gösterir. Cevapla karşılaştırıp kontrol et."
                : "Cevapta kullanılan bölüm bu sayfada. Sayfayı okuyup cevapla karşılaştır."}
            </p>
            <details className="mt-4">
              <summary className="cursor-pointer text-sm text-graphite hover:text-ink">
                Alıntılanan bölümü metin olarak göster
              </summary>
              <div className="mt-3">
                <Sheet page={current.page}>
                  <p className="font-mono text-sm leading-relaxed whitespace-pre-wrap">{current.text}</p>
                </Sheet>
              </div>
            </details>
          </>
        ) : (
          <Sheet page={current.page}>
            <p className="font-mono text-sm leading-relaxed whitespace-pre-wrap">
              <span key={current.source_id} className="marker-sweep">
                {current.text}
              </span>
            </p>
          </Sheet>
        )}
      </div>
    </Root>
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
