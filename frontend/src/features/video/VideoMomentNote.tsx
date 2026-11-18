import { PlayCircle } from "lucide-react";

import type { VideoMoment } from "../../api/types";
import { formatTimeRange } from "../../text";

/**
 * Cevabın, öğrencinin durdurduğu andaki video bölümüne dayandığını söyler (#102); tıklayınca
 * oynatıcı o bölümün başına gider.
 */
export default function VideoMomentNote({
  moment,
  onPlay,
}: {
  moment: VideoMoment;
  onPlay?: (documentId: number, seconds: number) => void;
}) {
  const span = formatTimeRange(moment.t_start, moment.t_end);
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 self-start rounded-panel border border-line bg-surface px-3 py-2 text-sm text-ink-2">
      <PlayCircle size={14} aria-hidden className="shrink-0 text-accent" />
      <span>
        {moment.deictic ? "Sorunu videonun " : "Videonun "}
        <strong className="font-semibold text-ink tabular-nums">{span}</strong>
        {moment.deictic ? " kısmına göre anladım" : " kısmı da kaynaklara eklendi"}
        <span className="text-graphite"> · {moment.document_title}</span>
      </span>
      {onPlay && (
        <button
          type="button"
          className="link"
          onClick={() => onPlay(moment.document_id, moment.t_start)}
          aria-label={`Videoda ${span} kısmına git`}
        >
          Videoda göster
        </button>
      )}
    </p>
  );
}
