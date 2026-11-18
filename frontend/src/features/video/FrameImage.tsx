import { ImageOff } from "lucide-react";
import { useState } from "react";

import type { FrameRef } from "../../api/types";
import { formatTime } from "../../text";
import { cx } from "../../ui/cx";
import Skeleton from "../../ui/Skeleton";
import { retryUrl } from "./frames";

/**
 * Videodan alınan karenin görüntüsü (`loading="lazy"`). Yüklenene kadar iskelet; açılamazsa
 * "Kare açılamadı" ve "Tekrar dene". `onOpen` verilirse görüntü büyütme düğmesidir.
 * `compact`: başka bir düğmenin içindeki küçük kare (şerit); hata yalnızca simgeyle gösterilir,
 * düğme içinde düğme olmasın diye "Tekrar dene" yoktur.
 */
export default function FrameImage({
  frame,
  compact = false,
  onOpen,
  openLabel,
  className,
}: {
  frame: FrameRef;
  compact?: boolean;
  onOpen?: () => void;
  openLabel?: string;
  className?: string;
}) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<"loading" | "loaded" | "failed">("loading");
  const box = "relative flex aspect-video w-full overflow-hidden rounded-control border border-line bg-subtle";

  if (state === "failed") {
    return (
      <div
        role={compact ? "img" : undefined}
        aria-label={compact ? "Kare açılamadı" : undefined}
        className={cx(box, "flex-col items-center justify-center gap-1 border-dashed p-2 text-center text-xs text-graphite", className)}
      >
        <ImageOff size={compact ? 14 : 16} aria-hidden />
        {!compact && (
          <>
            <span>Kare açılamadı</span>
            <button
              type="button"
              className="link text-xs"
              onClick={() => {
                setState("loading");
                setAttempt((value) => value + 1);
              }}
            >
              Tekrar dene
            </button>
          </>
        )}
      </div>
    );
  }

  const image = (
    <>
      <img
        key={attempt}
        src={retryUrl(frame.image_url, attempt)}
        alt={`Videonun ${formatTime(frame.t_frame)} anında ekrandaki görüntü`}
        loading="lazy"
        decoding="async"
        onLoad={() => setState("loaded")}
        onError={() => setState("failed")}
        className={cx(
          "block h-full w-full object-contain transition-opacity duration-200",
          state === "loaded" ? "opacity-100" : "opacity-0",
        )}
      />
      {state === "loading" && <Skeleton className="absolute inset-0 rounded-none" />}
    </>
  );

  return onOpen ? (
    <button
      type="button"
      onClick={onOpen}
      aria-label={openLabel}
      className={cx(box, "cursor-zoom-in hover:border-accent focus-visible:outline-2 focus-visible:outline-accent", className)}
    >
      {image}
    </button>
  ) : (
    <div className={cx(box, className)}>{image}</div>
  );
}
