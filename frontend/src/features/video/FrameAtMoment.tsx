import { PlayCircle } from "lucide-react";
import { useState } from "react";

import type { FrameRef } from "../../api/types";
import { formatTime } from "../../text";
import Button from "../../ui/Button";
import { cx } from "../../ui/cx";
import Dialog from "../../ui/Dialog";
import FrameImage from "./FrameImage";
import { frameAt, slideChangeNear } from "./frames";

/** Karenin ne olduğunu söyleyen etiket: cevap bu kareyi kaynak göstermiyorsa konuşmaya dayanır. */
export const FRAME_LABEL = "Ekran görüntüsü · cevap konuşmaya (transkript) dayanır";
/**
 * Cevap bu kareyi kaynak gösterdiğinde (#26, ADR-12): kare judge tarafından görüntüyle kontrol
 * edilmiş bir kanıttır; "cevap transkripte dayanır" demek yanlış olur.
 */
export const FRAME_CITED_LABEL = "Ekran görüntüsü · cevabın bir kısmı bu kareye dayanır";

/**
 * Videonun `seconds` anında ekranda olan kare: küçük görüntü, tıklayınca büyür; "Videoda bu
 * ana git" oynatıcıyı o ana götürür. An bir slayt değişimine 2 saniyeden yakınsa önceki ve
 * sonraki kare birlikte gösterilir. Kare yoksa (ya da o anda kare yoksa) hiçbir şey çizilmez.
 */
export default function FrameAtMoment({
  frames,
  seconds,
  heading,
  onSeek,
  cited,
  className,
}: {
  frames: FrameRef[] | null;
  seconds: number;
  heading?: string;
  onSeek?: (seconds: number) => void;
  /** Cevabın kaynak gösterdiği kareler (`citedFrameIds`); yoksa cevap transkripte dayanır. */
  cited?: ReadonlySet<number>;
  className?: string;
}) {
  const [enlarged, setEnlarged] = useState<FrameRef | null>(null);
  if (!frames || frames.length === 0) return null;
  const change = slideChangeNear(frames, seconds);
  const single = change ? null : frameAt(frames, seconds);
  const shown = change ?? (single ? [single] : []);
  if (shown.length === 0) return null;
  const isCited = (frame: FrameRef) => cited?.has(frame.frame_id) ?? false;
  const label = shown.some(isCited) ? FRAME_CITED_LABEL : FRAME_LABEL;

  return (
    <figure
      aria-label={heading ?? `Videonun ${formatTime(seconds)} anında ekranda`}
      className={cx("flex flex-col gap-2 rounded-panel border border-line bg-surface p-3", className)}
    >
      {heading && (
        <p className="text-xs font-medium text-ink">
          {heading} <span className="font-mono font-normal text-graphite">· {formatTime(seconds)}</span>
        </p>
      )}
      {change && <p className="text-xs font-medium text-accent">Tam bu anda slayt değişiyor</p>}
      <div className={cx("grid gap-2", change ? "grid-cols-2" : "max-w-xs grid-cols-1")}>
        {shown.map((frame, index) => (
          <div key={frame.frame_id} className="flex min-w-0 flex-col gap-1">
            <FrameImage
              frame={frame}
              onOpen={() => setEnlarged(frame)}
              openLabel={`${formatTime(frame.t_frame)} karesini büyüt`}
            />
            {change && (
              <span className="font-mono text-xs text-graphite">
                {index === 0 ? "Önceki slayt" : "Sonraki slayt"} · {formatTime(frame.t_start)}
                {isCited(frame) && <span className="text-accent"> · cevapta kaynak</span>}
              </span>
            )}
          </div>
        ))}
      </div>
      <figcaption className="text-xs text-graphite">{label}</figcaption>
      {onSeek && (
        <Button size="sm" variant="ghost" icon={PlayCircle} className="self-start" onClick={() => onSeek(seconds)}>
          Videoda bu ana git
        </Button>
      )}
      <Dialog
        open={enlarged !== null}
        onClose={() => setEnlarged(null)}
        size="lg"
        title={enlarged ? `Videonun ${formatTime(enlarged.t_frame)} anında ekranda` : ""}
        description={enlarged && isCited(enlarged) ? FRAME_CITED_LABEL : FRAME_LABEL}
        footer={
          enlarged && onSeek ? (
            <Button
              size="sm"
              icon={PlayCircle}
              onClick={() => {
                const target = enlarged.t_start <= seconds && seconds < enlarged.t_end ? seconds : enlarged.t_start;
                setEnlarged(null);
                onSeek(target);
              }}
            >
              Videoda bu ana git
            </Button>
          ) : undefined
        }
      >
        {enlarged && <FrameImage key={enlarged.frame_id} frame={enlarged} />}
      </Dialog>
    </figure>
  );
}
