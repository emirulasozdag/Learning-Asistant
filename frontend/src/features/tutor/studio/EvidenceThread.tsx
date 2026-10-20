import { useEffect, useState, type RefObject } from "react";

import { measureThread, sameThread, type Thread } from "./geometry";

/**
 * Kanıt izi: seçilen iddiadan kaynak sayfasındaki işaretli satıra çizilen kesik çizgi.
 * Konumlar her karede ölçülür (kaydırma, yeniden boyutlanma, görüntünün geç yüklenmesi);
 * yalnızca değişince yeniden çizilir. Ekran okuyucudan gizlidir: aynı bağ metinde de yazılıdır.
 */
export default function EvidenceThread({
  containerRef,
  source,
  target,
  drawKey,
}: {
  containerRef: RefObject<HTMLElement | null>;
  source: HTMLElement | null;
  target: HTMLElement | null;
  /** Değişince iz baştan çizilir (yeni iddia ya da yeni kaynak seçildiğinde). */
  drawKey: string;
}) {
  const [thread, setThread] = useState<Thread | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !source || !target) return;
    let frame = 0;
    let last: Thread | null = null;
    const tick = () => {
      const next = measureThread(
        container.getBoundingClientRect(),
        source.getBoundingClientRect(),
        target.getBoundingClientRect(),
      );
      if (!sameThread(next, last)) {
        last = next;
        setThread(next);
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [containerRef, source, target]);

  if (!thread || !source || !target) return null;
  return (
    <svg aria-hidden className="pointer-events-none absolute inset-0 z-10 h-full w-full overflow-visible">
      <path key={drawKey} d={thread.path} className="evidence-thread evidence-thread-draw" />
      <circle cx={thread.from.x} cy={thread.from.y} r={3.5} fill="var(--color-thread)" />
      <circle cx={thread.to.x} cy={thread.to.y} r={3.5} fill="var(--color-thread)" />
    </svg>
  );
}
