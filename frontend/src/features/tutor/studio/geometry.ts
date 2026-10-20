export interface Point {
  x: number;
  y: number;
}

export interface Thread {
  from: Point;
  to: Point;
  path: string;
}

/** Yatay teğetli yumuşak eğri: iddiadan sağa çıkar, kaynak satırına soldan girer. */
export function threadPath(from: Point, to: Point): string {
  const bend = Math.max(Math.abs(to.x - from.x) * 0.5, 24);
  return `M ${from.x} ${from.y} C ${from.x + bend} ${from.y}, ${to.x - bend} ${to.y}, ${to.x} ${to.y}`;
}

/**
 * İki öğe arasındaki iz, kapsayıcıya göre koordinatlarla. Öğeler yan yana değilse (dar ekranda
 * alt alta) ya da biri görünür alanın dışındaysa iz çizilmez.
 */
export function measureThread(container: DOMRect, source: DOMRect, target: DOMRect): Thread | null {
  const gap = 6;
  if (target.left <= source.right) return null;
  const visible = (rect: DOMRect) => rect.bottom > container.top && rect.top < container.bottom && rect.height > 0;
  if (!visible(source) || !visible(target)) return null;

  const from = { x: source.right - container.left + gap, y: source.top + source.height / 2 - container.top };
  const to = {
    x: target.left - container.left - gap,
    y: target.top + Math.min(target.height / 2, 12) - container.top,
  };
  return { from, to, path: threadPath(from, to) };
}

export function sameThread(a: Thread | null, b: Thread | null): boolean {
  if (!a || !b) return a === b;
  const close = (p: Point, q: Point) => Math.abs(p.x - q.x) < 0.5 && Math.abs(p.y - q.y) < 0.5;
  return close(a.from, b.from) && close(a.to, b.to);
}
