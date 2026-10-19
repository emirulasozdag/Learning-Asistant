import { useSyncExternalStore } from "react";

/** Tailwind `lg` eşiği: kaynak paneli bundan geniş ekranda yanda, dar ekranda tam ekran açılır. */
const DESKTOP_QUERY = "(min-width: 1024px)";

export function isDesktopNow(): boolean {
  return window.matchMedia(DESKTOP_QUERY).matches;
}

function subscribe(onChange: () => void) {
  const media = window.matchMedia(DESKTOP_QUERY);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

export function useIsDesktop(): boolean {
  return useSyncExternalStore(subscribe, isDesktopNow, () => true);
}
