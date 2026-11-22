import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../../api/client";
import type {
  AnswerFeedback,
  AnswerSubmission,
  Difficulty,
  PracticeItem,
  PracticeRequest,
  PracticeType,
} from "../../api/types";
import { practiceService } from "../../services/practiceService";
import { studyCacheKey } from "../../auth/studyCache";
import { useAuth } from "../../auth/useAuth";

export interface PracticeSettings {
  type: PracticeType;
  difficulty: Difficulty;
  topic: string;
}

/** Oturumdaki bir soru ve (verildiyse) cevabın geri bildirimi. */
export interface PracticeEntry {
  item: PracticeItem;
  feedback: AnswerFeedback | null;
  /** Öğrencinin cevabı: geri bildirimde seçilen şık / yazılan metin gösterilsin diye. */
  answer: AnswerSubmission | null;
}

export interface PracticeFailure {
  /** no_item: kontrolden geçen soru yok (konu); unavailable: yapay zekâ/ağ; rejected: istek reddedildi. */
  kind: "no_item" | "unavailable" | "rejected";
  detail: string;
}

export type SessionView = "setup" | "session" | "summary";

interface Stored {
  settings: PracticeSettings | null;
  entries: PracticeEntry[];
  view: SessionView;
}

function load(userId: number | null | undefined, courseId: number): Stored | null {
  const storageKey = studyCacheKey("la.practice.", userId, `${courseId}`);
  if (!storageKey) return null;
  try {
    const raw = sessionStorage.getItem(storageKey);
    if (!raw) return null;
    const stored = JSON.parse(raw) as Stored;
    return Array.isArray(stored.entries) ? stored : null;
  } catch {
    return null;
  }
}

function save(userId: number | null | undefined, courseId: number, stored: Stored) {
  const storageKey = studyCacheKey("la.practice.", userId, `${courseId}`);
  if (!storageKey) return;
  try {
    if (stored.entries.length === 0 && stored.view === "setup") {
      sessionStorage.removeItem(storageKey);
    } else {
      sessionStorage.setItem(storageKey, JSON.stringify(stored));
    }
  } catch {
    // Saklanamazsa oturum yalnızca bu sayfada yaşar; sorun değil.
  }
}

/** Üretim hatasını öğrenciye söylenecek cümleye çevirir. */
export function describeFailure(reason: unknown): PracticeFailure {
  if (reason instanceof ApiError && reason.kind === "http") {
    if (reason.code === "no_valid_item") return { kind: "no_item", detail: reason.message };
    if (reason.code === "ai_unavailable") return { kind: "unavailable", detail: reason.message };
    if ((reason.status ?? 0) < 500) return { kind: "rejected", detail: reason.message };
  }
  return { kind: "unavailable", detail: "Soru şu an hazırlanamadı. Bağlantını kontrol edip tekrar dene." };
}

/**
 * Pratik oturumu: kurulum → sorular (biri odakta) → özet. Sorular gerçek API'den gelir; oturum
 * sekme kapanana kadar `sessionStorage`'da kalır (sayfa yenilenince kaybolmaz). Cevap anahtarı
 * yalnızca cevaptan sonra gelen geri bildirimdedir.
 */
export function usePracticeSession(courseId: number) {
  // Kayıt kullanıcıya bağlı (#134): aynı tarayıcıda başka öğrencinin oturumu açılmaz.
  const userId = useAuth().user?.id;
  const [initial] = useState(() => load(userId, courseId));
  const [settings, setSettings] = useState<PracticeSettings | null>(initial?.settings ?? null);
  const [entries, setEntries] = useState<PracticeEntry[]>(initial?.entries ?? []);
  const [view, setView] = useState<SessionView>(initial?.view ?? "setup");
  const [generating, setGenerating] = useState(false);
  const [failure, setFailure] = useState<PracticeFailure | null>(null);
  const [lastRequest, setLastRequest] = useState<PracticeRequest | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => save(userId, courseId, { settings, entries, view }), [userId, courseId, settings, entries, view]);
  // Sayfadan çıkınca süren istek iptal edilir.
  useEffect(() => () => controllerRef.current?.abort(), []);

  const request = useCallback(async (body: PracticeRequest) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setGenerating(true);
    setFailure(null);
    setLastRequest(body);
    setView("session");
    try {
      const item = await practiceService.generate(body, controller.signal);
      if (!controller.signal.aborted) setEntries((list) => [...list, { item, feedback: null, answer: null }]);
    } catch (reason) {
      if (!controller.signal.aborted) setFailure(describeFailure(reason));
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        setGenerating(false);
      }
    }
  }, []);

  /** Ayarlarla yeni soru (oturumu başlatır ya da sürdürür). */
  const start = useCallback(
    (next: PracticeSettings) => {
      setSettings(next);
      void request({ course_id: courseId, type: next.type, difficulty: next.difficulty, topic: next.topic });
    },
    [courseId, request],
  );

  /** Aynı ayarlarla sıradaki soru. */
  const nextQuestion = useCallback(() => {
    if (settings) start(settings);
  }, [settings, start]);

  /** Son denemenin eksik kavramlarına yönelik soru. */
  const followUp = useCallback(
    (entry: PracticeEntry) => {
      if (!entry.feedback) return;
      void request({
        course_id: courseId,
        type: entry.item.type,
        difficulty: entry.item.difficulty,
        follow_up_of_attempt_id: entry.feedback.attempt_id,
      });
    },
    [courseId, request],
  );

  const retry = useCallback(() => {
    if (lastRequest) void request(lastRequest);
  }, [lastRequest, request]);

  const cancel = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setGenerating(false);
    setFailure(null);
    setView((current) => (entries.length === 0 && current === "session" ? "setup" : current));
  }, [entries.length]);

  const answer = useCallback(async (itemId: number, body: AnswerSubmission) => {
    const feedback = await practiceService.answer(itemId, body);
    setEntries((list) =>
      list.map((entry) => (entry.item.id === itemId ? { ...entry, feedback, answer: body } : entry)),
    );
    return feedback;
  }, []);

  const openSetup = useCallback(() => {
    controllerRef.current?.abort();
    setGenerating(false);
    setFailure(null);
    setView("setup");
  }, []);

  const finish = useCallback(() => {
    controllerRef.current?.abort();
    setGenerating(false);
    setFailure(null);
    setView("summary");
  }, []);

  /** Oturumu kapatır: sorular silinir, ayarlar kalır. */
  const reset = useCallback(() => {
    controllerRef.current?.abort();
    setGenerating(false);
    setFailure(null);
    setEntries([]);
    setView("setup");
  }, []);

  return {
    settings,
    entries,
    view,
    generating,
    failure,
    start,
    nextQuestion,
    followUp,
    retry,
    cancel,
    answer,
    openSetup,
    finish,
    reset,
    backToSession: () => setView("session"),
  };
}

export type PracticeSession = ReturnType<typeof usePracticeSession>;
