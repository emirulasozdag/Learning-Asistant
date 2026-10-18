/** Koşullu sınıf birleştirme: cx("a", ok && "b") → "a b". */
export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}
