interface PlaceholderProps {
  title: string;
  requirement: string;
  description: string;
}

/** Henüz uygulanmamış bir özelliğin yerini tutar. */
export default function Placeholder({ title, requirement, description }: PlaceholderProps) {
  return (
    <section className="rounded-lg border border-dashed border-slate-300 p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="font-medium">{title}</h2>
        <span className="text-xs text-slate-400">{requirement}</span>
      </div>
      <p className="mt-1 text-sm text-slate-500">{description}</p>
      <p className="mt-2 text-xs text-slate-400">Henüz uygulanmadı.</p>
    </section>
  );
}
