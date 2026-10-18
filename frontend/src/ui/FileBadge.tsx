import { cx } from "./cx";

const KINDS: Record<string, { label: string; className: string }> = {
  pdf: { label: "PDF", className: "text-danger" },
  pptx: { label: "PPT", className: "text-warning" },
};

/** Dosya türü işareti (PDF / PPT) — ikon kütüphanesine bağımlı olmadan, tanınabilir. */
export default function FileBadge({ filename, size = "md" }: { filename: string; size?: "sm" | "md" }) {
  const extension = filename.split(".").pop()?.toLowerCase() ?? "";
  const kind = KINDS[extension] ?? { label: extension.slice(0, 3).toUpperCase() || "DOC", className: "text-graphite" };
  return (
    <span
      aria-hidden
      className={cx(
        "flex shrink-0 items-center justify-center rounded bg-surface font-semibold ring-1 ring-line",
        size === "sm" ? "size-6 text-[9px]" : "size-8 text-[10px]",
        kind.className,
      )}
    >
      {kind.label}
    </span>
  );
}
