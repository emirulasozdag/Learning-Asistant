import { cx } from "./cx";

function initials(name: string): string {
  return name
    .replace(/^(Dr\.|Prof\.|Doç\.)\s*/i, "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toLocaleUpperCase("tr"))
    .join("");
}

export default function Avatar({
  name,
  size = "md",
  className,
}: {
  name: string;
  size?: "sm" | "md";
  className?: string;
}) {
  return (
    <span
      aria-hidden
      className={cx(
        "inline-flex shrink-0 items-center justify-center rounded-full font-medium text-white",
        size === "sm" ? "size-6 text-[10px]" : "size-8 text-xs",
        // Zemin rengi verilmezse mürekkep rengi.
        className ?? "bg-ink",
      )}
    >
      {initials(name)}
    </span>
  );
}
