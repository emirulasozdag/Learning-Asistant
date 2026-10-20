import type { ConversationEntry } from "../studio/context";
import { classifyResponse } from "./outcome";
import type { Segment, TutorTurn, Turn } from "./types";

/** Kaynaklı cevap bölümü mü (blok geldiyse türünden, gelmediyse çalışan araçtan). */
export function isCourseSegment(segment: Segment): boolean {
  return segment.block ? segment.block.type === "course_answer" : segment.tool === "answer_from_course";
}

/**
 * Turun ilk kaynaklı cevabı, mevcut cevap bileşenlerinin (iddia görünümü, AnswerBlock, "Nasıl
 * bulundu") beklediği biçimde. Tur hiçbir blok üretmeden hata verdiyse ya da durdurulduysa o
 * durumu taşır. Kaynaklı cevap yoksa (yalnızca pratik, bilgilendirme…) null.
 */
export function answerOf(turn: TutorTurn): Turn | null {
  const index = turn.segments.findIndex(isCourseSegment);
  if (index === -1) {
    const nothing = turn.segments.every((segment) => segment.block?.type === "follow_ups");
    return nothing && (turn.failure || turn.stopped)
      ? { id: turn.id, question: turn.question, streamText: "", failure: turn.failure, stopped: turn.stopped }
      : null;
  }
  const segment = turn.segments[index];
  return {
    id: `${turn.id}-${index}`,
    question: turn.question,
    hits: segment.hits,
    streamText: segment.streamText,
    response: segment.block?.type === "course_answer" ? segment.block.response : undefined,
    // Tur yarıda kaldıysa henüz doğrulanmamış cevap taslak olarak bırakılmaz.
    failure: segment.block ? undefined : turn.failure,
    stopped: segment.block ? undefined : turn.stopped,
    startedAt: turn.startedAt,
    finishedAt: turn.finishedAt,
  };
}

/** İlk kaynaklı cevap dışındaki bloklar (pratik, genel bilgi, netleştirme, ikinci cevap…). */
export function extraSegments(turn: TutorTurn): Segment[] {
  const first = turn.segments.findIndex(isCourseSegment);
  return turn.segments.filter((segment, index) => index !== first && segment.block?.type !== "follow_ups");
}

/** Kenar çubuğundaki "Bu sohbet" listesi için kısa durum. */
export function entryState(turn: TutorTurn): ConversationEntry["state"] {
  if (turn.failure || turn.stopped) return "failed";
  if (!turn.done) return "pending";
  const answer = answerOf(turn)?.response;
  if (answer) {
    const outcome = classifyResponse(answer);
    if (outcome === "out_of_scope") return "declined";
    if (outcome === "not_generated") return "failed";
    return "answered";
  }
  const notice = turn.segments.find((segment) => segment.block?.type === "notice")?.block;
  return notice?.type === "notice" && notice.kind !== "greeting" ? "declined" : "answered";
}
