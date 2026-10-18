import { CircleAlert, CircleCheck, LoaderCircle } from "lucide-react";
import type { ReactNode } from "react";

import { cx } from "./cx";

type Tone = "neutral" | "accent" | "success" | "warning" | "danger";

const TONES: Record<Tone, string> = {
  neutral: "bg-subtle text-ink-2",
  accent: "bg-accent-soft text-accent",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
};

export default function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cx(
        "inline-flex h-5 items-center gap-1 rounded px-1.5 text-xs font-medium whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export type IndexStatus = "indexed" | "processing" | "failed";

const STATUS: Record<IndexStatus, { tone: Tone; label: string }> = {
  indexed: { tone: "success", label: "İndekslendi" },
  processing: { tone: "warning", label: "İşleniyor" },
  failed: { tone: "danger", label: "Başarısız" },
};

/** Materyalin bilgi tabanındaki durumu. */
export function StatusBadge({ status }: { status: IndexStatus }) {
  const { tone, label } = STATUS[status];
  const Icon =
    status === "indexed" ? CircleCheck : status === "processing" ? LoaderCircle : CircleAlert;
  return (
    <Badge tone={tone}>
      <Icon size={12} aria-hidden className={status === "processing" ? "animate-spin" : ""} />
      {label}
    </Badge>
  );
}
