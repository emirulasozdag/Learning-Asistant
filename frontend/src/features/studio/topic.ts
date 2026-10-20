/** Konum yolunda gösterilecek kısa konu: aktif sorudan ilk birkaç kelime. */
export function topicOf(question: string | null, words = 6): string | null {
  if (!question) return null;
  const parts = question.replace(/[?.!]+$/, "").split(/\s+/).filter(Boolean);
  if (parts.length === 0) return null;
  return parts.length > words ? `${parts.slice(0, words).join(" ")}…` : parts.join(" ");
}
