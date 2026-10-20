import { CircleAlert, ServerOff } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router";

import type { DocumentOut, IngestionReport } from "../../api/types";
import DocumentDrawer from "../../features/materials/DocumentDrawer";
import Dropzone from "../../features/materials/Dropzone";
import MaterialsTable, { type PendingUpload } from "../../features/materials/MaterialsTable";
import { useCourseOutlet } from "../../features/courses/courseOutlet";
import { courseService, guessMaterialType } from "../../services/courseService";
import { documentExtent, materialTotals } from "../../labels";
import { formatTime } from "../../text";
import Button from "../../ui/Button";
import Dialog from "../../ui/Dialog";
import EmptyState from "../../ui/EmptyState";
import PageTitle from "../../ui/PageTitle";
import { SkeletonRows } from "../../ui/Skeleton";
import { useToast } from "../../ui/toast/context";

/** Dersin bilgi tabanı: yükle → parçala → vektörleştir; AI Tutor yalnızca buradan cevap verir. */
export default function MaterialsPage() {
  const courseId = Number(useParams().courseId);
  const toast = useToast();
  const { reloadDocuments } = useCourseOutlet();
  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [pending, setPending] = useState<PendingUpload[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [reports, setReports] = useState<Record<number, IngestionReport>>({});
  const [openDocument, setOpenDocument] = useState<DocumentOut | null>(null);
  const [toDelete, setToDelete] = useState<DocumentOut | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    courseService
      .materials(courseId, controller.signal)
      .then((list) => {
        if (!controller.signal.aborted) setDocuments(list);
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoadFailed(true);
      });
    return () => controller.abort();
  }, [courseId, attempt]);

  function reload() {
    setLoadFailed(false);
    setDocuments(null);
    setAttempt((value) => value + 1);
  }

  const upload = useCallback(
    async (item: PendingUpload) => {
      setPending((list) =>
        list.map((p) => (p.key === item.key ? { ...p, status: "processing", error: undefined } : p)),
      );
      try {
        const document = await courseService.uploadMaterial(courseId, item.type, item.file);
        setPending((list) => list.filter((p) => p.key !== item.key));
        setDocuments((list) => [document, ...(list ?? [])]);
        reloadDocuments();
        toast.show({
          tone: "success",
          title: `${document.title} yüklendi`,
          description: `${documentExtent(document)}, ${document.chunk_count} parça; öğrenciler artık bu dokümandan soru sorabilir.`,
        });
        if (document.report) {
          const report = document.report;
          setReports((map) => ({ ...map, [document.id]: report }));
        }
      } catch (reason) {
        const message = reason instanceof Error ? reason.message : String(reason);
        setPending((list) =>
          list.map((p) => (p.key === item.key ? { ...p, status: "failed", error: message } : p)),
        );
        toast.show({ tone: "danger", title: `${item.file.name} yüklenemedi`, description: message });
      }
    },
    [courseId, toast, reloadDocuments],
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
      toast.show({ tone: "success", title: `${toDelete.title} silindi` });
      reloadDocuments();
      setToDelete(null);
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setDeleting(false);
    }
  }

  const totals = materialTotals(documents ?? []);
  const totalChunks = documents?.reduce((sum, d) => sum + d.chunk_count, 0) ?? 0;
  const busy = pending.some((p) => p.status === "processing");

  return (
    <div className="flex flex-col gap-6">
      <PageTitle
        title="Materyaller"
        description="Bu dersin AI Tutor'u yalnızca buradaki dokümanlardan cevap verir ve her cevabında dayandığı sayfayı gösterir."
        actions={
          documents &&
          documents.length > 0 && (
            <dl className="flex gap-8">
              <Stat label="doküman" value={documents.length} />
              {totals.hasPages && <Stat label="sayfa" value={totals.pages} />}
              {totals.hasVideo && <Stat label="video süresi" value={formatTime(totals.videoSeconds)} />}
              <Stat label="parça" value={totalChunks} />
            </dl>
          )
        }
      />

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

      {loadFailed ? (
        <EmptyState
          icon={ServerOff}
          tone="danger"
          title="Materyaller yüklenemedi"
          description="Ders materyaline şu an ulaşılamıyor. Bağlantını kontrol edip tekrar dene."
          action={<Button onClick={reload}>Tekrar dene</Button>}
        />
      ) : documents === null ? (
        <SkeletonRows rows={3} />
      ) : documents.length === 0 && pending.length === 0 ? (
        <p className="py-4 text-center text-base text-graphite">
          Henüz materyal yok. İlk ders notunu yükle; işlendikten sonra öğrenciler bu dersten soru
          sorabilir.
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

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="flex flex-col-reverse">
      <dt className="text-sm text-graphite">{label}</dt>
      <dd className="text-xl leading-tight font-bold text-ink tabular-nums">{value}</dd>
    </div>
  );
}
