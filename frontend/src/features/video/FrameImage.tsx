import { ImageOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { FrameRef } from "../../api/types";
import { formatTime } from "../../text";
import { cx } from "../../ui/cx";
import Skeleton from "../../ui/Skeleton";
import { retryUrl } from "./frames";

/** Bu kadar süre içinde gelmeyen görüntü "açılamadı" sayılır (asılı kalan istek iskelette kalmasın). */
const LOAD_TIMEOUT_MS = 20_000;
/** Görünür alana bu kadar yaklaşınca yüklenmeye başlar. */
const PRELOAD_MARGIN = "300px";

/**
 * Videodan alınan karenin görüntüsü. Yüklenene kadar iskelet; açılamazsa "Kare açılamadı" (ve
 * tam boyda "Tekrar dene"). `onOpen` verilirse görüntü büyütme düğmesidir.
 * `compact`: başka bir düğmenin içindeki küçük kare (şerit); düğme içinde düğme olmasın diye
 * "Tekrar dene" yoktur.
 *
 * Görüntü, kutu görünür alana yaklaşınca istenir (IntersectionObserver). Tarayıcının
 * `loading="lazy"`'si kullanılmaz: yana kayan şeritte boyutu henüz belli olmayan görüntüyü hiç
 * istemeyebiliyor ve kare gri kutu olarak kalıyordu. Görüntü kutuyu (16:9) mutlak konumla
 * doldurur; yüklenmeden önce de alanı vardır.
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
  // IntersectionObserver yoksa (eski tarayıcı) görüntü hemen istenir.
  const [near, setNear] = useState(() => typeof IntersectionObserver === "undefined");
  const boxRef = useRef<HTMLElement | null>(null);
  const box = "relative aspect-video w-full overflow-hidden rounded-control border border-line bg-subtle";

  // Kutu görünür alana yaklaşınca görüntü istenir (bir kez).
  useEffect(() => {
    if (near) return;
    const element = boxRef.current;
    if (!element) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setNear(true);
          observer.disconnect();
        }
      },
      { rootMargin: PRELOAD_MARGIN },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [near]);

  // İstek asılı kalırsa iskelet sonsuza dek dönmesin.
  useEffect(() => {
    if (!near || state !== "loading") return;
    const timer = window.setTimeout(() => setState("failed"), LOAD_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [near, state, attempt]);

  if (state === "failed") {
    return (
      <div
        role={compact ? "img" : undefined}
        aria-label={compact ? "Kare açılamadı" : undefined}
        className={cx(
          box,
          "flex flex-col items-center justify-center gap-1 border-dashed p-2 text-center text-xs text-graphite",
          className,
        )}
      >
        <ImageOff size={compact ? 14 : 16} aria-hidden />
        <span className={compact ? "sr-only sm:not-sr-only" : undefined}>Kare açılamadı</span>
        {!compact && (
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
        )}
      </div>
    );
  }

  const image = (
    <>
      <img
        key={attempt}
        // Önbellekten anında gelen görüntüde `load` olayı kaçmasın.
        ref={(element) => {
          if (element?.complete && element.naturalWidth > 0 && element.getAttribute("src")) setState("loaded");
        }}
        src={near ? retryUrl(frame.image_url, attempt) : undefined}
        alt={`Videonun ${formatTime(frame.t_frame)} anında ekrandaki görüntü`}
        decoding="async"
        onLoad={() => setState("loaded")}
        onError={() => setState("failed")}
        className={cx(
          "absolute inset-0 h-full w-full object-contain transition-opacity duration-200",
          state === "loaded" ? "opacity-100" : "opacity-0",
        )}
      />
      {state === "loading" && <Skeleton className="absolute inset-0 rounded-none" />}
    </>
  );

  return onOpen ? (
    <button
      ref={(element) => {
        boxRef.current = element;
      }}
      type="button"
      onClick={onOpen}
      aria-label={openLabel}
      className={cx(box, "block cursor-zoom-in hover:border-accent", className)}
    >
      {image}
    </button>
  ) : (
    <div
      ref={(element) => {
        boxRef.current = element;
      }}
      className={cx(box, "block", className)}
    >
      {image}
    </div>
  );
}
