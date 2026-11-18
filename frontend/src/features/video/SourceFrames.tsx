import { useState } from "react";

import type { FrameRef } from "../../api/types";
import { formatTime } from "../../text";
import Dialog from "../../ui/Dialog";
import { FRAME_LABEL } from "./FrameAtMoment";
import FrameImage from "./FrameImage";

/**
 * Video alıntısının aralığında ekranda olan kareler (`SourceDetail.frames`). `onPlayAt` varsa
 * kareye tıklamak videoyu o slaytın başına götürür; yoksa kare büyütülerek açılır.
 * Liste boşsa hiçbir şey çizilmez.
 */
export default function SourceFrames({
  frames,
  onPlayAt,
  className = "mt-4",
}: {
  frames: FrameRef[];
  onPlayAt?: (documentId: number, seconds: number) => void;
  className?: string;
}) {
  const [enlarged, setEnlarged] = useState<FrameRef | null>(null);
  if (frames.length === 0) return null;
  return (
    <section aria-labelledby="source-frames" className={className}>
      <h3 id="source-frames" className="text-sm font-medium text-ink">
        Bu kısımda ekranda
      </h3>
      <ul className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
        {frames.map((frame) => (
          <li key={frame.frame_id}>
            {onPlayAt ? (
              <button
                type="button"
                onClick={() => onPlayAt(frame.document_id, frame.t_start)}
                aria-label={`Videoda ${formatTime(frame.t_start)} anına git`}
                className="flex w-full flex-col gap-1 rounded-control p-1 text-left hover:bg-subtle focus-visible:outline-2 focus-visible:outline-accent"
              >
                <FrameImage frame={frame} compact />
                <span className="font-mono text-xs text-graphite tabular-nums">{formatTime(frame.t_start)}</span>
              </button>
            ) : (
              <div className="flex flex-col gap-1 p-1">
                <FrameImage
                  frame={frame}
                  onOpen={() => setEnlarged(frame)}
                  openLabel={`${formatTime(frame.t_start)} karesini büyüt`}
                />
                <span className="font-mono text-xs text-graphite tabular-nums">{formatTime(frame.t_start)}</span>
              </div>
            )}
          </li>
        ))}
      </ul>
      <p className="mt-1.5 text-xs text-graphite">{FRAME_LABEL}</p>
      <Dialog
        open={enlarged !== null}
        onClose={() => setEnlarged(null)}
        size="lg"
        title={enlarged ? `Videonun ${formatTime(enlarged.t_frame)} anında ekranda` : ""}
        description={FRAME_LABEL}
      >
        {enlarged && <FrameImage key={enlarged.frame_id} frame={enlarged} />}
      </Dialog>
    </section>
  );
}
