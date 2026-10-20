import { FileUp } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import { MEDIA_EXTENSIONS } from "../../services/courseService";
import { cx } from "../../ui/cx";

const ACCEPTED_EXTENSIONS = [".pdf", ".pptx", ".vtt", ...MEDIA_EXTENSIONS];

interface DropzoneProps {
  onFiles: (files: File[]) => void;
  onReject: (message: string) => void;
  disabled?: boolean;
  compact?: boolean;
}

/** Sürükle-bırak yükleme alanı. Birden fazla dosya kabul eder; desteklenmeyenleri bildirir. */
export default function Dropzone({ onFiles, onReject, disabled, compact }: DropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function accept(list: FileList | null) {
    const files = [...(list ?? [])];
    const valid = files.filter((file) =>
      ACCEPTED_EXTENSIONS.some((ext) => file.name.toLowerCase().endsWith(ext)),
    );
    const rejected = files.filter((file) => !valid.includes(file));
    if (rejected.length > 0) {
      onReject(
        `${rejected.map((file) => file.name).join(", ")} yüklenemez: yalnızca PDF, PPTX, altyazı (VTT) ve ders videosu/sesi destekleniyor.`,
      );
    }
    if (valid.length > 0) onFiles(valid);
  }

  function drop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    if (!disabled) accept(event.dataTransfer.files);
  }

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled}
      aria-label="Materyal yükle: dosyaları buraya bırak ya da seç"
      onClick={() => !disabled && inputRef.current?.click()}
      onKeyDown={(event) => {
        if ((event.key === "Enter" || event.key === " ") && !disabled) {
          event.preventDefault();
          inputRef.current?.click();
        }
      }}
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={drop}
      className={cx(
        "group flex cursor-pointer items-center gap-4 rounded-panel border border-dashed transition-colors",
        compact ? "px-4 py-3" : "flex-col justify-center px-6 py-10 text-center",
        dragging
          ? "border-accent bg-accent-soft"
          : "border-line-strong bg-surface hover:border-graphite hover:bg-canvas",
        disabled && "cursor-not-allowed opacity-60",
      )}
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPTED_EXTENSIONS.join(",")}
        className="sr-only"
        tabIndex={-1}
        onChange={(event) => {
          accept(event.target.files);
          event.target.value = "";
        }}
      />
      <span
        className={cx(
          "flex size-10 shrink-0 items-center justify-center rounded-panel border transition-colors",
          dragging ? "border-accent-line bg-surface text-accent" : "border-line bg-canvas text-graphite group-hover:text-ink",
        )}
      >
        <FileUp size={18} aria-hidden />
      </span>
      <span className={compact ? "text-left" : ""}>
        <span className="block text-md font-medium text-ink">
          {dragging ? "Bırak, yüklemeye başlayalım" : "Dosyaları buraya sürükle ya da bilgisayarından seç"}
        </span>
        <span className="mt-1 block text-sm text-graphite">
          Ders notu, slayt, ders kitabı bölümü, geçmiş sınav, video altyazısı. PDF, PPTX, VTT ya da ders videosu/sesi (transkripsiyon açıksa); video ve ses dışında dosya başına en fazla 50 MB.
        </span>
      </span>
    </div>
  );
}
