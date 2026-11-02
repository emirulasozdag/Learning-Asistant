import { mediaUrlError } from "../../services/courseService";
import Button from "../../ui/Button";
import Field from "../../ui/Field";
import FileBadge from "../../ui/FileBadge";

/** Yüklenmeyi bekleyen video dosyası ve girilen oynatma adresi. */
export interface StagedVideo {
  key: string;
  file: File;
  url: string;
  error?: string | null;
}

interface VideoUrlStepProps {
  items: StagedVideo[];
  onChange: (items: StagedVideo[]) => void;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Video/altyazı dosyaları yüklenmeden önce isteğe bağlı oynatma adresi sorulur; PDF/PPTX bu adımı görmez. */
export default function VideoUrlStep({ items, onChange, onConfirm, onCancel }: VideoUrlStepProps) {
  function setUrl(key: string, url: string) {
    onChange(items.map((item) => (item.key === key ? { ...item, url, error: undefined } : item)));
  }

  function confirm() {
    const checked = items.map((item) => ({ ...item, error: mediaUrlError(item.url) }));
    onChange(checked);
    if (checked.every((item) => !item.error)) onConfirm();
  }

  return (
    <section aria-label="Video adresi" className="flex flex-col gap-4 rounded-panel border border-line bg-surface px-4 py-4">
      <p className="text-sm text-graphite">
        Öğrenciler cevaptaki zaman damgasından videoyu bu adreste açabilir. Boş bırakırsan dosya yine yüklenir.
      </p>
      {items.map((item) => (
        <div key={item.key} className="flex flex-col gap-2 sm:flex-row sm:items-start sm:gap-4">
          <div className="flex min-w-0 items-center gap-3 sm:w-1/3 sm:pt-7">
            <FileBadge filename={item.file.name} />
            <p className="truncate font-medium text-ink">{item.file.name}</p>
          </div>
          <Field
            className="flex-1"
            label="Video adresi (https)"
            type="url"
            inputMode="url"
            placeholder="https://"
            value={item.url}
            error={item.error}
            onChange={(event) => setUrl(item.key, event.target.value)}
          />
        </div>
      ))}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onCancel}>
          Vazgeç
        </Button>
        <Button onClick={confirm}>Yükle</Button>
      </div>
    </section>
  );
}
