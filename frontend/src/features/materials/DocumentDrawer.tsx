import { ExternalLink, FileText, Images, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { ChunkPreview, DocumentOut, IngestionReport as Report } from "../../api/types";
import Sheet from "../../components/Sheet";
import { documentExtent, documentIndexStatus, materialLabel } from "../../labels";
import { courseService } from "../../services/courseService";
import { formatRelative } from "../../text";
import { StatusBadge } from "../../ui/Badge";
import Button from "../../ui/Button";
import { buttonClasses } from "../../ui/buttonStyles";
import { Drawer } from "../../ui/Dialog";
import EmptyState from "../../ui/EmptyState";
import { SkeletonRows } from "../../ui/Skeleton";
import IngestionReport from "./IngestionReport";

interface DocumentDrawerProps {
  document: DocumentOut | null;
  report?: Report;
  onClose: () => void;
  /** Kare için video eklenince güncel doküman (#27). */
  onChanged?: (document: DocumentOut) => void;
  /** Süren kare işini iptal (onay diyaloğu sayfada). */
  onCancel?: (document: DocumentOut) => void;
}

/** Doküman ayrıntısı: yükleme raporu, videoda slayt kareleri ve sistemin çıkardığı parçalar. */
export default function DocumentDrawer({ document, report, onClose, onChanged, onCancel }: DocumentDrawerProps) {
  return (
    <Drawer
      open={document !== null}
      onClose={onClose}
      title={document?.title ?? ""}
      description={document ? document.filename : undefined}
      width="max-w-2xl"
      footer={
        document && (
          <a href={document.file_url} target="_blank" rel="noreferrer" className={buttonClasses("secondary")}>
            <ExternalLink size={14} aria-hidden />
            Orijinal dosyayı aç
          </a>
        )
      }
    >
      {document && (
        <DocumentDetail
          key={document.id}
          document={document}
          report={report}
          onChanged={onChanged}
          onCancel={onCancel}
        />
      )}
    </Drawer>
  );
}

function DocumentDetail({
  document,
  report,
  onChanged,
  onCancel,
}: {
  document: DocumentOut;
  report?: Report;
  onChanged?: (document: DocumentOut) => void;
  onCancel?: (document: DocumentOut) => void;
}) {
  const [chunks, setChunks] = useState<ChunkPreview[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    courseService
      .chunks(document.id)
      .then(setChunks)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, [document.id]);

  return (
    <div className="flex flex-col gap-8">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-base sm:grid-cols-4">
        <Meta label="Durum">
          <StatusBadge status={documentIndexStatus(document)} />
        </Meta>
        <Meta label="Tür">{materialLabel(document.material_type)}</Meta>
        <Meta label="İçerik">
          {documentExtent(document)}, {document.chunk_count} parça
        </Meta>
        <Meta label="Yüklendi">{formatRelative(document.created_at)}</Meta>
        {document.media_url && (
          <Meta label="Video adresi">
            <a
              href={document.media_url}
              target="_blank"
              rel="noopener noreferrer"
              className="break-all text-accent hover:underline"
            >
              {document.media_url}
            </a>
          </Meta>
        )}
      </dl>

      {report && <IngestionReport report={report} />}

      {document.material_type === "video" && document.status === "ready" && onChanged && (
        <FrameVideoSection document={document} onChanged={onChanged} onCancel={onCancel} />
      )}

      <section>
        <h3 className="mb-1 text-base font-medium text-ink">Sistemin çıkardığı parçalar</h3>
        <p className="mb-4 text-sm text-graphite">
          AI Tutor öğrenci sorularını bu parçalarda arar ve cevabında sayfa numarasıyla gösterir.
        </p>
        {error ? (
          <EmptyState icon={FileText} tone="danger" title="Parçalar yüklenemedi" description={error} />
        ) : chunks === null ? (
          <SkeletonRows rows={3} />
        ) : (
          <ol className="flex flex-col gap-3">
            {chunks.map((chunk) => (
              <li key={chunk.id}>
                <Sheet page={chunk.page}>
                  <p className="font-mono text-sm leading-relaxed whitespace-pre-wrap">{chunk.text}</p>
                </Sheet>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

/**
 * Slayt kareleri (#27): altyazısıyla yüklenen videoda kare yoktur. Eğitmen video dosyasını
 * ekleyince sistem transkripti değiştirmeden slayt karelerini çıkarır; öğrenci durdurduğu anda
 * ekranda ne olduğunu görür. Kareler cevapta kanıt değildir (ADR-10).
 */
function FrameVideoSection({
  document,
  onChanged,
  onCancel,
}: {
  document: DocumentOut;
  onChanged: (document: DocumentOut) => void;
  onCancel?: (document: DocumentOut) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const frames = document.frame_count ?? 0;

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    try {
      onChanged(await courseService.addFrameVideo(document.id, file));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setUploading(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <section aria-labelledby="frame-video-title">
      <h3 id="frame-video-title" className="mb-1 flex items-center gap-2 text-base font-medium text-ink">
        <Images size={16} aria-hidden className="text-graphite" />
        Slayt kareleri
      </h3>
      <p className="mb-3 text-sm text-graphite">
        Öğrenci videoyu durdurduğunda o anda ekranda olan slaytı görür. Bunun için videonun dosyasını
        ekle; transkript değişmez, yalnızca kareler çıkarılır. Kareler cevapta kanıt olarak kullanılmaz.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        {document.frames_processing ? (
          <>
            <p role="status" className="text-base text-ink-2">
              Kareler hazırlanıyor… Liste kendiliğinden güncellenir.
            </p>
            {onCancel && (
              <Button size="sm" variant="ghost" icon={Square} onClick={() => onCancel(document)}>
                İptal et
              </Button>
            )}
          </>
        ) : (
          <>
            <p className="text-base text-ink-2">{frames > 0 ? `${frames} kare` : "Henüz kare yok"}</p>
            <input
              ref={input}
              type="file"
              accept=".mp4,.webm,.mkv,.mov,video/*"
              className="sr-only"
              aria-label="Video dosyası seç"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void upload(file);
              }}
            />
            <Button size="sm" loading={uploading} onClick={() => input.current?.click()}>
              {frames > 0 ? "Video dosyasını yeniden ekle" : "Video dosyası ekle"}
            </Button>
          </>
        )}
      </div>
      {error && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {error}
        </p>
      )}
    </section>
  );
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-sm text-graphite">{label}</dt>
      <dd className="mt-1 text-ink">{children}</dd>
    </div>
  );
}
