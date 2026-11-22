import { useState } from "react";

import type { DemoInfo } from "../../api/types";
import { userMessage } from "../../api/errors";
import { useAuth } from "../../auth/useAuth";
import { ROLE_LABELS } from "../../layouts/navigation";
import Avatar from "../../ui/Avatar";
import ErrorText from "../../ui/ErrorText";

/**
 * Sunum modu (DEMO_LOGIN): demo hesaplarına tek tıkla giriş ve derslerin katılım kodları.
 * Yalnızca backend bu modu açtıysa görünür; gerçek kullanımda hiç gösterilmez.
 */
export default function DemoAccounts({ info }: { info: DemoInfo }) {
  const { demoLogin } = useAuth();
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function enter(role: "instructor" | "student") {
    setPending(role);
    setError(null);
    try {
      // Yönlendirmeyi AuthLayout yapar.
      await demoLogin(role);
    } catch (reason) {
      setError(userMessage(reason, "Demo hesabıyla girilemedi. Tekrar dene."));
      setPending(null);
    }
  }

  return (
    <section className="mt-10" aria-labelledby="demo-heading">
      <p id="demo-heading" className="text-sm font-semibold text-ink">
        Demo hesapları
      </p>
      <p className="mt-0.5 text-sm text-graphite">Sunum modu: şifre girmeden tek tıkla gir.</p>

      <ul className="mt-3 flex flex-col gap-2">
        {info.accounts.map((account) => (
          <li key={account.role}>
            <button
              type="button"
              onClick={() => void enter(account.role)}
              disabled={pending !== null}
              className="flex w-full items-center gap-3 rounded-panel border border-line bg-surface px-3 py-2.5 text-left transition-colors hover:border-accent-line hover:bg-accent-soft/40 disabled:opacity-60"
            >
              <Avatar name={account.name} className="bg-accent text-on-accent" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-base font-semibold text-ink">{account.name}</span>
                <span className="block truncate text-sm text-graphite">{account.title ?? account.email}</span>
              </span>
              <span className="rounded-full bg-subtle px-2.5 py-0.5 text-xs font-semibold text-ink-2">{ROLE_LABELS[account.role]}</span>
            </button>
          </li>
        ))}
      </ul>
      {error && <ErrorText className="mt-2">{error}</ErrorText>}

      {info.courses.length > 0 && (
        <div className="mt-6">
          <p className="text-sm font-semibold text-ink">Katılım kodları</p>
          <p className="mt-0.5 text-sm text-graphite">Öğrenci, Derslerim sayfasında bu kodla derse katılır.</p>
          <ul className="mt-2 flex flex-col divide-y divide-line rounded-panel border border-line bg-surface">
            {info.courses.map((course) => (
              <li key={course.course_id} className="flex items-center justify-between gap-3 px-3 py-2">
                <span className="flex min-w-0 items-center gap-2 text-sm text-ink">
                  <span className="shrink-0 font-semibold">{course.code}</span>
                  <span className="truncate text-graphite">{course.name}</span>
                </span>
                <code className="shrink-0 font-mono text-sm font-semibold tracking-wider text-ink">
                  {course.join_code}
                </code>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
