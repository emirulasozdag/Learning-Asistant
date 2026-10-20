import { useState } from "react";

import type { Highlight } from "../../api/types";
import Skeleton from "../../ui/Skeleton";

/**
 * Gerçek PDF sayfası ve üzerinde alıntılanan satırlar. `anchorRef`: ilk işaretli satır (kanıt
 * izi buraya bağlanır; işaret yoksa sayfanın kendisi).
 */
export default function PageImage({
  src,
  alt,
  highlights,
  anchorRef,
}: {
  src: string;
  alt: string;
  highlights: Highlight[];
  anchorRef?: (element: HTMLElement | null) => void;
}) {
  const [loaded, setLoaded] = useState(false);
  return (
    <figure
      ref={highlights.length === 0 && loaded ? anchorRef : undefined}
      className="relative overflow-hidden rounded-sm bg-surface shadow-page"
    >
      <img
        src={src}
        alt={alt}
        onLoad={() => setLoaded(true)}
        className={`page-image block w-full transition-opacity duration-300 ${loaded ? "opacity-100" : "opacity-0"}`}
      />
      {!loaded && <Skeleton className="absolute inset-0 rounded-none" />}
      {loaded &&
        highlights.map((box, index) => (
          <span
            key={index}
            ref={index === 0 ? anchorRef : undefined}
            aria-hidden
            className="marker-box"
            style={{
              left: `${box.x * 100}%`,
              top: `${box.y * 100}%`,
              width: `${box.width * 100}%`,
              height: `${box.height * 100}%`,
              animationDelay: `${index * 45}ms`,
            }}
          />
        ))}
    </figure>
  );
}
