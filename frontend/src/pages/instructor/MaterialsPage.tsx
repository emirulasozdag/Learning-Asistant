import { CircleAlert, FileStack } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router";

import type { DocumentOut, IngestionReport } from "../../api/types";
import DocumentDrawer from "../../features/materials/DocumentDrawer";
import Dropzone from "../../features/materials/Dropzone";
import MaterialsTable, { type PendingUpload } from "../../features/materials/MaterialsTable";
import { courseService, guessMaterialType } from "../../services/courseService";
import Button from "../../ui/Button";
import Dialog from "../../ui/Dialog";
import EmptyState from "../../ui/EmptyState";
import { SkeletonRows } from "../../ui/Skeleton";

/** Dersin bilgi tabanı: yükle → parçala → vektörleştir; AI Tutor yalnızca buradan cevap verir. */
export default function MaterialsPage() {
  const courseId = Number(useParams().courseId);
  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingUpload[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [reports, setReports] = useState<Record<number, IngestionReport>>({});
  const [openDocument, setOpenDocument] = useState<DocumentOut | null>(null);
  const [toDelete, setToDelete] = useState<DocumentOut | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    courseService
      .materials(courseId)
      .then((list) => {
        if (!cancelled) setDocuments(list);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setLoadError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [courseId]);

  const upload = useCallback(
    async (item: PendingUpload) => {
      setPending((list) =>
        list.map((p) => (p.key === item.key ? { ...p, status: "processing", error: undefined } : p)),
      );
      try {
        const document = await courseService.uploadMaterial(courseId, item.type, item.file);
        setPending((list) => list.filter((p) => p.key !== item.key));
        setDocuments((list) => [document, ...(list ?? [])]);
        if (document.report) {
          const report = document.report;
          setReports((map) => ({ ...map, [document.id]: report }));
        }
      } catch (reason) {
        const message = reason instanceof Error ? reason.message : String(reason);
        setPending((list) =>
          list.map((p) => (p.key === item.key ? { ...p, status: "failed", error: message } : p)),
        );
      }
    },
    [courseId],
  );

  async function addFiles(files: File[]) {
    setNotice(null);
    const items: PendingUpload[] = files.map((file, index) => ({
      key: `${Date.now()}-${index}-${file.name}`,
      file,
      type: guessMaterialType(file.name),
      status: "processing",
    }));
    setPending((list) => [...items, ...list]);
    // Sırayla: embedding modeli aynı anda tek dosyada çalışsın.
    for (const item of items) await upload(item);
  }

  async function confirmDelete() {
    if (!toDelete) return;
    setDeleting(true);
    try {
      await courseService.deleteMaterial(toDelete.id);
      setDocuments((list) => list?.filter((d) => d.id !== toDelete.id) ?? null);
      if (openDocument?.id === toDelete.id) setOpenDocument(null);
      setToDelete(null);
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setDeleting(false);
    }
  }

  const totalPages = documents?.reduce((sum, d) => sum + d.page_count, 0) ?? 0;
  const totalChunks = documents?.reduce((sum, d) => sum + d.chunk_count, 0) ?? 0;
  const busy = pending.some((p) => p.status === "processing");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-ink">Bilgi tabanı</h2>
          <p className="mt-1 max-w-2xl text-base text-graphite">
            Bu dersin AI Tutor'u yalnızca buradaki dokümanlardan cevap verir ve her cevabında
            dayandığı sayfayı gösterir.
          </p>
        </div>
        {documents && documents.length > 0 && (
          <dl className="flex gap-6 text-right">
            <Stat label="doküman" value={documents.length} />
            <Stat label="sayfa" value={totalPages} />
            <Stat label="parça" value={totalChunks} />
          </dl>
        )}
      </div>

      <Dropzone
        onFiles={(files) => void addFiles(files)}
        onReject={setNotice}
        compact={Boolean(documents && documents.length > 0)}
      />

      {notice && (
        <p role="alert" className="flex items-center gap-2 rounded-control bg-danger-soft px-3 py-2 text-base text-danger">
          <CircleAlert size={14} aria-hidden />
          {notice}
        </p>
      )}

      {loadError ? (
        <EmptyState
          icon={FileStack}
          tone="danger"
          title="Materyaller yüklenemedi"
          description={`API'ye ulaşılamıyor olabilir. (${loadError})`}
        />
      ) : documents === null ? (
        <SkeletonRows rows={3} />
      ) : documents.length === 0 && pending.length === 0 ? (
        <p className="text-center text-base text-graphite">
          Henüz materyal yok. İlk ders notunu yükle; birkaç saniye içinde öğrenciler soru sormaya
          başlayabilir.
        </p>
      ) : (
        <MaterialsTable
          documents={documents}
          pending={pending}
          selectedId={openDocument?.id ?? null}
          onOpen={setOpenDocument}
          onDelete={setToDelete}
          onRetry={(item) => void upload(item)}
          onDismiss={(item) => setPending((list) => list.filter((p) => p.key !== item.key))}
        />
      )}
      {busy && (
        <p className="sr-only" role="status">
          Dosyalar işleniyor
        </p>
      )}

      <DocumentDrawer
        document={openDocument}
        report={openDocument ? reports[openDocument.id] : undefined}
        onClose={() => setOpenDocument(null)}
      />

      <Dialog
        open={toDelete !== null}
        onClose={() => setToDelete(null)}
        title="Doküman silinsin mi?"
        description={
          toDelete
            ? `“${toDelete.title}” ve ${toDelete.chunk_count} parçası bilgi tabanından kaldırılacak. AI Tutor bu dokümandan artık cevap veremez.`
            : undefined
        }
        footer={
          <>
            <Button variant="ghost" onClick={() => setToDelete(null)}>
              Vazgeç
            </Button>
            <Button variant="danger" loading={deleting} onClick={() => void confirmDelete()} data-autofocus>
              Sil
            </Button>
          </>
        }
      >
        <p className="text-base text-graphite">Bu işlem geri alınamaz.</p>
      </Dialog>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col-reverse">
      <dt className="text-sm text-graphite">{label}</dt>
      <dd className="text-lg font-semibold text-ink tabular-nums">{value}</dd>
    </div>
  );
}
