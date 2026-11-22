import { useEffect } from "react";

import { PRODUCT_NAME } from "./Logo";

/**
 * Tarayıcı sekmesindeki başlık: "Takvim – Dipnot". Başlık verilmezse dokunmaz (ör. sayfa içi
 * bölüm başlıkları); böylece sayfanın h1'inin koyduğu başlık ezilmez.
 */
export function usePageTitle(title: string | null | undefined): void {
  useEffect(() => {
    if (title) document.title = `${title} – ${PRODUCT_NAME}`;
  }, [title]);
}
