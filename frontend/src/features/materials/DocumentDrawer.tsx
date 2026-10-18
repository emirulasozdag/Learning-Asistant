import { ExternalLink, FileText } from "lucide-react";
import { useEffect, useState } from "react";

import type { ChunkPreview, DocumentOut, IngestionReport as Report } from "../../api/types";
import Sheet from "../../components/Sheet";
import { materialLabel } from "../../labels";
import { courseService } from "../../services/courseService";
import { formatRelative, reflow } from "../../text";
import { StatusBadge } from "../../ui/Badge";
import { buttonClasses } from "../../ui/buttonStyles";
import { Drawer } from "../../ui/Dialog";
import EmptyState from "../../ui/EmptyState";
import { SkeletonRows } from "../../ui/Skeleton";
import IngestionReport from "./IngestionReport";

interface DocumentDrawerProps {
  document: DocumentOut | null;
  report?: Report;
  onClose: () => void;
}

/** Doküman ayrıntısı: yükleme raporu ve sistemin çıkardığı sayfa sayfa parçalar. */
export default function DocumentDrawer({ document, report, onClose }: DocumentDrawerProps) {
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
      {document && <DocumentDetail key={document.id} document={document} report={report} />}
    </Drawer>
  );
}

function DocumentDetail({ document, report }: { document: DocumentOut; report?: Report }) {
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
          <StatusBadge status="indexed" />
        </Meta>
        <Meta label="Tür">{materialLabel(document.material_type)}</Meta>
        <Meta label="İçerik">
          {document.page_count} sayfa, {document.chunk_count} parça
        </Meta>
        <Meta label="Yüklendi">{formatRelative(document.created_at)}</Meta>
      </dl>

      {report && <IngestionReport report={report} />}

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
                  <p className="text-md leading-relaxed whitespace-pre-wrap">{reflow(chunk.text)}</p>
                </Sheet>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
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
