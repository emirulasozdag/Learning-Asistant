import emblem from "../assets/brand/ankara-bilim-amblem.png";
import wordmark from "../assets/brand/ankara-bilim-logo.png";
import { cx } from "./cx";

export const UNIVERSITY_NAME = "Ankara Bilim Üniversitesi";

/**
 * Ankara Bilim Üniversitesi logosu. Lacivert logo koyu zeminde okunmadığı için her temada açık
 * bir plaka üzerinde durur. `compact`: dar yerlerde (daraltılmış kenar çubuğu) yalnızca amblem.
 */
export default function UniversityLogo({
  compact = false,
  className,
}: {
  compact?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-control bg-white px-2 py-1.5 ring-1 ring-black/5",
        className,
      )}
    >
      <img
        src={compact ? emblem : wordmark}
        alt={UNIVERSITY_NAME}
        className={compact ? "h-7 w-7 object-contain" : "h-7 w-auto max-w-full object-contain"}
        draggable={false}
      />
    </span>
  );
}
