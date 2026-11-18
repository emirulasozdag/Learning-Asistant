import { useCallback, useEffect, useRef, useState } from "react";

import type { TutorStreamEvent, VideoRef } from "../../api/types";
import { tutorService } from "../../services/tutorService";
import { classifyFailure } from "./outcome";
import { loadSession, saveSession } from "./sessionTurns";
import type { Segment, TutorTurn } from "./types";

function withSegment(turn: TutorTurn, index: number, change: (segment: Segment) => Segment): TutorTurn {
  const segments = [...turn.segments];
  while (segments.length <= index) segments.push({ tool: turn.tool ?? "", streamText: "" });
  segments[index] = change(segments[index]);
  return { ...turn, segments };
}

/**
 * AI Tutor sohbeti: soru gönderme, akış olaylarını turlara işleme, durdurma ve yeni sohbet.
 * Video çalışma ekranı kullanır (#103). Sohbet ders + anahtar başına sekme oturumunda saklanır.
 */
export function useTutorTurns(courseId: number, sessionKey: string) {
  const [restored] = useState(() => loadSession(courseId, sessionKey));
  const [turns, setTurns] = useState<TutorTurn[]>(restored.turns);
  const [conversationId, setConversationId] = useState<number | null>(restored.conversationId);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);
  useEffect(
    () => saveSession(courseId, turns, conversationId, sessionKey),
    [courseId, turns, conversationId, sessionKey],
  );

  const updateTurn = useCallback((id: string, change: (turn: TutorTurn) => TutorTurn) => {
    setTurns((list) => list.map((turn) => (turn.id === id ? change(turn) : turn)));
  }, []);

  const applyEvent = useCallback(
    (id: string, event: TutorStreamEvent) => {
      if (event.type === "status") {
        updateTurn(id, (t) => ({ ...t, tool: event.tool, status: event.tool === "finish" ? undefined : event.label }));
      } else if (event.type === "retrieval") {
        updateTurn(id, (t) => withSegment(t, event.blockIndex, (s) => ({ ...s, hits: event.hits })));
      } else if (event.type === "delta") {
        updateTurn(id, (t) =>
          withSegment(t, event.blockIndex, (s) => ({ ...s, streamText: s.streamText + event.text })),
        );
      } else if (event.type === "block") {
        updateTurn(id, (t) => ({ ...withSegment(t, event.index, (s) => ({ ...s, block: event.block })), status: undefined }));
      } else if (event.type === "done") {
        const blocks = event.response.blocks;
        updateTurn(id, (t) => ({
          ...t,
          done: true,
          status: undefined,
          finishedAt: performance.now(),
          segments: blocks.map((block, index) => ({ ...(t.segments[index] ?? { tool: "", streamText: "" }), block })),
        }));
        setConversationId(event.response.conversation_id);
      } else {
        updateTurn(id, (t) => ({ ...t, failure: { kind: "temporary" } }));
      }
    },
    [updateTurn],
  );

  async function ask(text: string, video: VideoRef | null, id = `${Date.now()}`): Promise<void> {
    text = text.trim();
    if (!text || busy) return;
    setBusy(true);
    setTurns((list) => [...list, { id, question: text, segments: [], startedAt: performance.now() }]);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await tutorService.turn(courseId, text, conversationId, (event) => applyEvent(id, event), controller.signal, video);
      updateTurn(id, (t) => {
        if (t.done || t.failure) return t;
        return controller.signal.aborted ? { ...t, stopped: true } : { ...t, failure: { kind: "unavailable" } };
      });
    } catch (reason) {
      updateTurn(id, (t) => {
        if (t.done || t.failure) return t;
        return controller.signal.aborted ? { ...t, stopped: true } : { ...t, failure: classifyFailure(reason) };
      });
    } finally {
      if (abortRef.current === controller) setBusy(false);
    }
  }

  function stop() {
    abortRef.current?.abort();
  }

  function reset() {
    abortRef.current?.abort();
    setTurns([]);
    setConversationId(null);
    setBusy(false);
  }

  function retry(turn: TutorTurn, video: VideoRef | null) {
    if (busy) return;
    setTurns((list) => list.filter((item) => item.id !== turn.id));
    void ask(turn.question, video);
  }

  return { turns, busy, ask, stop, reset, retry };
}
