const YOUTUBE_HOSTS = new Set(["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtube-nocookie.com"]);
export const YOUTUBE_ORIGIN = "https://www.youtube-nocookie.com";

/** Eğitmenin girdiği oynatma adresi YouTube ise video kimliği; değilse null. */
export function youTubeId(url: string): string | null {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  if (!YOUTUBE_HOSTS.has(parsed.hostname)) return null;
  if (parsed.hostname === "youtu.be") return parsed.pathname.slice(1) || null;
  const fromQuery = parsed.searchParams.get("v");
  if (fromQuery) return fromQuery;
  const match = parsed.pathname.match(/^\/(?:embed|shorts|live)\/([\w-]{6,})/);
  return match ? match[1] : null;
}
