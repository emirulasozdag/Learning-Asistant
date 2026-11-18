import { ServerOff } from "lucide-react";

import Button from "./Button";

/**
 * Sayfanın bir bölümü yüklenemediğinde (#106): ne olduğunu söyler ve tekrar denetir. Tam sayfa
 * hatası için `EmptyState` (tone="danger" + "Tekrar dene") kullanılır; ikisi aynı dili konuşur.
 */
export default function InlineError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3">
      <p className="flex items-center gap-2 text-md text-danger">
        <ServerOff size={16} aria-hidden />
        {message}
      </p>
      <Button size="sm" onClick={onRetry}>
        Tekrar dene
      </Button>
    </div>
  );
}
