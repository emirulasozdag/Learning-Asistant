import { useEffect, useRef, type KeyboardEvent } from "react";

import type { FrameRef } from "../../api/types";
import { formatTime } from "../../text";
import { cx } from "../../ui/cx";
import Skeleton from "../../ui/Skeleton";
import FrameImage from "./FrameImage";
import { frameAt } from "./frames";

/**
 * Videonun slaytları yan yana (zaman çizgisinin altında): şu an ekrandaki işaretli; tıklayınca
 * ya da Enter'la video o slaytın başına gider, ok tuşları slaytlar arasında gezer. Tek satırdır,
 * yalnızca şeridin kendisi yana kayar (sayfa taşmaz). Kare yoksa çizilmez; kareler yüklenirken
 * (videonun karesi olduğu biliniyorsa) yerleri iskeletle tutulur.
 */
export default function SlideStrip({
  frames,
  expected = 0,
  time,
  onSeek,
}: {
  frames: FrameRef[] | null;
  /** Videonun kaç karesi olduğu (`DocumentOut.frame_count`); yüklenirken iskelet sayısı. */
  expected?: number;
  time: number;
  onSeek: (seconds: number) => void;
}) {
  const listRef = useRef<HTMLOListElement>(null);
  const current = frames ? frameAt(frames, time) : null;
  const currentId = current?.frame_id ?? null;

  // Şu anki slayt görünür kalsın: yalnızca şerit kayar (scrollIntoView sayfayı da kaydırırdı).
  useEffect(() => {
    const list = listRef.current;
    const item = list?.querySelector<HTMLElement>(`[data-frame="${currentId}"]`);
    if (!list || !item) return;
    const left = item.offsetLeft - list.offsetLeft;
    if (left < list.scrollLeft || left + item.offsetWidth > list.scrollLeft + list.clientWidth) {
      list.scrollTo({ left: left - 8, behavior: "smooth" });
    }
  }, [currentId]);

  if (frames === null && expected > 0) {
    return (
      <div role="status" aria-label="Slaytlar yükleniyor" className="flex gap-2 overflow-hidden p-1 pb-2">
        {Array.from({ length: Math.min(expected, 8) }, (_, index) => (
          <div key={index} className="flex w-24 shrink-0 flex-col gap-1 p-1 sm:w-28">
            <Skeleton className="aspect-video w-full rounded-control" />
            <Skeleton className="h-3 w-8" />
          </div>
        ))}
      </div>
    );
  }
  if (!frames || frames.length === 0) return null;
  // Klavye odağı tek düğmede durur (şu anki slayt, yoksa ilki); oklarla diğerlerine geçilir.
  const focusId = currentId ?? frames[0].frame_id;

  function onKeyDown(event: KeyboardEvent<HTMLOListElement>) {
    const keys: Record<string, number> = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
    if (!(event.key in keys) && event.key !== "Home" && event.key !== "End") return;
    const buttons = [...(listRef.current?.querySelectorAll<HTMLButtonElement>("button") ?? [])];
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
    if (index < 0) return;
    event.preventDefault();
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? buttons.length - 1
          : Math.min(buttons.length - 1, Math.max(0, index + keys[event.key]));
    buttons[next].focus();
  }

  return (
    <nav aria-label="Slaytlar" className="min-w-0">
      <ol
        ref={listRef}
        onKeyDown={onKeyDown}
        // İç boşluk: şu anki slaytın çerçevesi kayan kutunun kenarında kesilmesin.
        className="flex min-w-0 snap-x scroll-px-1 gap-2 overflow-x-auto p-1 pb-2 [scrollbar-width:thin]"
      >
        {frames.map((frame, index) => {
          const isCurrent = frame.frame_id === currentId;
          return (
            <li key={frame.frame_id} data-frame={frame.frame_id} className="w-24 shrink-0 snap-start sm:w-28">
              <button
                type="button"
                tabIndex={frame.frame_id === focusId ? 0 : -1}
                aria-current={isCurrent ? "true" : undefined}
                aria-label={`Slayt ${index + 1}, ${formatTime(frame.t_start)}`}
                onClick={() => onSeek(frame.t_start)}
                className={cx(
                  "flex w-full flex-col gap-1 rounded-control p-1 text-left focus-visible:outline-2 focus-visible:outline-accent",
                  isCurrent ? "bg-accent-soft ring-2 ring-accent" : "hover:bg-subtle",
                )}
              >
                <FrameImage frame={frame} compact />
                <span
                  className={cx(
                    "text-xs tabular-nums",
                    isCurrent ? "font-medium text-accent" : "text-graphite",
                  )}
                >
                  {formatTime(frame.t_start)}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
