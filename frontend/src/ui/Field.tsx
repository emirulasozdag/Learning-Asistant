import { forwardRef, useId, type InputHTMLAttributes, type ReactNode } from "react";


export const inputClasses =
  "h-10 w-full rounded-control border border-line bg-surface px-3 text-base text-ink placeholder:text-faint transition-colors hover:border-line-strong focus:border-accent focus:outline-none focus:ring-3 focus:ring-accent/12 disabled:bg-subtle disabled:text-faint aria-invalid:border-danger aria-invalid:focus:ring-danger/12";

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  /** Etiketin sağında (ör. "Şifremi unuttum"). */
  aside?: ReactNode;
}

/** Etiketli metin alanı: ipucu ve hata mesajı erişilebilir şekilde bağlanır. */
const Field = forwardRef<HTMLInputElement, FieldProps>(function Field(
  { label, hint, error, aside, className, id, ...props },
  ref,
) {
  const generated = useId();
  const inputId = id ?? generated;
  const describedBy = error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined;
  return (
    <div className={className}>
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <label htmlFor={inputId} className="text-sm font-medium text-ink-2">
          {label}
        </label>
        {aside}
      </div>
      <input
        ref={ref}
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={inputClasses}
        {...props}
      />
      {error ? (
        <p id={`${inputId}-error`} className="mt-1.5 text-sm text-danger">
          {error}
        </p>
      ) : (
        hint && (
          <p id={`${inputId}-hint`} className="mt-1.5 text-sm text-graphite">
            {hint}
          </p>
        )
      )}
    </div>
  );
});

export default Field;
