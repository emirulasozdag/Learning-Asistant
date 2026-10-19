import { createContext, useContext } from "react";

export type ToastTone = "success" | "danger" | "neutral";

export interface ToastInput {
  title: string;
  description?: string;
  tone?: ToastTone;
}

export interface ToastContextValue {
  show: (toast: ToastInput) => void;
}

export const ToastContext = createContext<ToastContextValue | null>(null);

/** Kısa süreli bildirim: bir işlemin sonucunu (yüklendi, silindi, hata) söyler. */
export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast, ToastProvider içinde kullanılmalı");
  return context;
}
