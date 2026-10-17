/** Ders seçimi — her dersin ayrı, izole bir indeksi var. Henüz uygulanmadı. */
export default function CourseSelector() {
  return (
    <select
      disabled
      aria-label="Ders seçimi"
      className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-400"
    >
      <option>Ders seçimi (henüz uygulanmadı)</option>
    </select>
  );
}
