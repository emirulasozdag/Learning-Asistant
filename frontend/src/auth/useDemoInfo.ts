import { useEffect, useState } from "react";

import type { DemoInfo } from "../api/types";
import { authService } from "../services/authService";

/** Sunum modu (DEMO_LOGIN) açıksa demo hesapları ve katılım kodları; kapalıysa ya da yüklenirken `null`. */
export function useDemoInfo(): DemoInfo | null {
  const [info, setInfo] = useState<DemoInfo | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void authService.demoInfo(controller.signal).then((data) => {
      if (!controller.signal.aborted) setInfo(data);
    });
    return () => controller.abort();
  }, []);
  return info;
}
