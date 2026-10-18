import { ExternalLink, RotateCcw, Trash2, X } from "lucide-react";

import type { DocumentOut, MaterialType } from "../../api/types";
import { materialLabel } from "../../labels";
import { formatRelative } from "../../text";
import { StatusBadge } from "../../ui/Badge";
import FileBadge from "../../ui/FileBadge";
import IconButton from "../../ui/IconButton";
import { Table, TD, TH, THead, TR } from "../../ui/Table";

/** Yüklenmekte olan ya da yüklenemeyen dosya (henüz veritabanında yok). */
export interface PendingUpload {
  key: string;
  file: File;
  type: MaterialType;
  status: "processing" | "failed";
  error?: string;
}

interface MaterialsTableProps {
  documents: DocumentOut[];
  pending: PendingUpload[];
  selectedId: number | null;
  onOpen: (document: DocumentOut) => void;
  onDelete: (document: DocumentOut) => void;
  onRetry: (upload: PendingUpload) => void;
  onDismiss: (upload: PendingUpload) => void;
}

export default function MaterialsTable({
  documents,
  pending,
  selectedId,
  onOpen,
  onDelete,
  onRetry,
  onDismiss,
}: MaterialsTableProps) {
  return (
    <Table label="Ders materyalleri">
      <THead>
        <tr>
          <TH>Dosya</TH>
          <TH className="hidden md:table-cell">Tür</TH>
          <TH className="hidden lg:table-cell">Yüklendi</TH>
          <TH className="hidden sm:table-cell">İçerik</TH>
          <TH>Durum</TH>
          <TH className="w-20">
            <span className="sr-only">İşlemler</span>
          </TH>
        </tr>
      </THead>
      <tbody>
        {pending.map((upload) => (
          <TR key={upload.key}>
            <TD>
              <div className="flex items-center gap-3">
                <FileBadge filename={upload.file.name} />
                <div className="min-w-0">
                  <p className="truncate font-medium text-ink">{upload.file.name}</p>
                  <p className="truncate text-sm text-graphite">
                    {upload.status === "failed"
                      ? upload.error
                      : `${(upload.file.size / 1024 / 1024).toFixed(1)} MB, parçalara ayrılıyor ve vektörleştiriliyor`}
                  </p>
                </div>
              </div>
            </TD>
            <TD className="hidden text-graphite md:table-cell">{materialLabel(upload.type)}</TD>
            <TD className="hidden text-graphite lg:table-cell">şimdi</TD>
            <TD className="hidden text-graphite sm:table-cell">—</TD>
            <TD>
              <StatusBadge status={upload.status} />
            </TD>
            <TD>
              {upload.status === "failed" && (
                <div className="flex justify-end gap-0.5">
                  <IconButton icon={RotateCcw} label="Tekrar dene" size="sm" onClick={() => onRetry(upload)} />
                  <IconButton icon={X} label="Listeden kaldır" size="sm" onClick={() => onDismiss(upload)} />
                </div>
              )}
            </TD>
          </TR>
        ))}

        {documents.map((document) => (
          <TR
            key={document.id}
            interactive
            selected={document.id === selectedId}
            onClick={() => onOpen(document)}
          >
            <TD>
              <div className="flex items-center gap-3">
                <FileBadge filename={document.filename} />
                <div className="min-w-0">
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      onOpen(document);
                    }}
                    className="block max-w-full truncate text-left font-medium text-ink hover:text-accent"
                  >
                    {document.title}
                  </button>
                  <p className="truncate text-sm text-graphite">{document.filename}</p>
                </div>
              </div>
            </TD>
            <TD className="hidden text-ink-2 md:table-cell">{materialLabel(document.material_type)}</TD>
            <TD className="hidden whitespace-nowrap text-graphite lg:table-cell">
              {formatRelative(document.created_at)}
            </TD>
            <TD className="hidden whitespace-nowrap text-graphite tabular-nums sm:table-cell">
              {document.page_count} sayfa, {document.chunk_count} parça
            </TD>
            <TD>
              <StatusBadge status="indexed" />
            </TD>
            <TD>
              <div className="flex justify-end gap-0.5" onClick={(event) => event.stopPropagation()}>
                <a
                  href={document.file_url}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={`${document.title} dosyasını aç`}
                  title="Dosyayı aç"
                  className="inline-flex size-7 items-center justify-center rounded-control text-graphite hover:bg-subtle hover:text-ink"
                >
                  <ExternalLink size={14} aria-hidden />
                </a>
                <IconButton
                  icon={Trash2}
                  label={`${document.title} dokümanını sil`}
                  size="sm"
                  onClick={() => onDelete(document)}
                />
              </div>
            </TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}
