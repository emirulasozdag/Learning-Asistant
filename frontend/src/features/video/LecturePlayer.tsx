import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";

import { YOUTUBE_ORIGIN, youTubeId } from "./youtube";

/** Oynatıcının dışarıya açtığı denetim: durdurulan an ve belirli bir saniyeye atlama. */
export interface PlayerHandle {
  /** Videonun başından itibaren saniye (bilinmiyorsa 0). */
  currentTime(): number;
  seek(seconds: number): void;
}

/**
 * Ders videosu oynatıcısı (#22). Video sistemde saklanmaz; eğitmenin verdiği adresten oynar:
 * YouTube adresi gömülü oynatıcıyla, doğrudan dosya adresi (mp4, webm) tarayıcının oynatıcısıyla.
 * Yüklenen altyazı (VTT) doğrudan dosyada alt yazı olarak da gösterilir.
 */
const LecturePlayer = forwardRef<
  PlayerHandle,
  {
    mediaUrl: string;
    title: string;
    /** İlk açılışta başlanacak saniye. */
    start?: number;
    /** Yüklenen altyazının adresi (`text/vtt`). */
    captionsUrl?: string;
    captionsLang?: string;
  }
>(function LecturePlayer({ mediaUrl, title, start = 0, captionsUrl, captionsLang = "en" }, ref) {
  const id = youTubeId(mediaUrl);
  return id ? (
    <YouTubePlayer ref={ref} videoId={id} title={title} start={start} />
  ) : (
    <FilePlayer ref={ref} src={mediaUrl} title={title} start={start} captionsUrl={captionsUrl} captionsLang={captionsLang} />
  );
});

export default LecturePlayer;

const FilePlayer = forwardRef<
  PlayerHandle,
  { src: string; title: string; start: number; captionsUrl?: string; captionsLang: string }
>(function FilePlayer({ src, title, start, captionsUrl, captionsLang }, ref) {
  const videoRef = useRef<HTMLVideoElement>(null);
  // Video henüz yüklenmediyse (ağ yavaş, adres erişilemez) istenen an burada tutulur.
  const pending = useRef(start);
  useImperativeHandle(ref, () => ({
    currentTime() {
      const video = videoRef.current;
      return video && video.readyState > 0 ? video.currentTime : pending.current;
    },
    seek(seconds) {
      pending.current = seconds;
      const video = videoRef.current;
      if (!video || video.readyState === 0) return;
      video.currentTime = seconds;
      void video.play().catch(() => undefined);
    },
  }));
  return (
    <video
      ref={videoRef}
      src={start > 0 ? `${src}#t=${Math.floor(start)}` : src}
      controls
      preload="metadata"
      onLoadedMetadata={(event) => {
        // Yüklenmeden önce istenen ana (alıntıdan atlama) geç.
        if (pending.current > 0) event.currentTarget.currentTime = pending.current;
      }}
      aria-label={title}
      className="aspect-video w-full rounded-panel bg-black"
    >
      {captionsUrl && <track kind="captions" src={captionsUrl} srcLang={captionsLang} label="Altyazı" default />}
    </video>
  );
});

/**
 * YouTube gömülü oynatıcısı; konum ve atlama YouTube'un iframe mesajlarıyla (dış betik yüklenmez).
 * Çerezsiz alan adı kullanılır.
 */
const YouTubePlayer = forwardRef<PlayerHandle, { videoId: string; title: string; start: number }>(
  function YouTubePlayer({ videoId, title, start }, ref) {
    const frameRef = useRef<HTMLIFrameElement>(null);
    const time = useRef(start);

    useImperativeHandle(ref, () => ({
      currentTime: () => time.current,
      seek(seconds) {
        time.current = seconds;
        post(frameRef.current, "seekTo", [seconds, true]);
        post(frameRef.current, "playVideo", []);
      },
    }));

    useEffect(() => {
      function onMessage(event: MessageEvent) {
        if (event.origin !== YOUTUBE_ORIGIN || event.source !== frameRef.current?.contentWindow) return;
        try {
          const data = typeof event.data === "string" ? JSON.parse(event.data) : event.data;
          const current = data?.info?.currentTime;
          if (typeof current === "number") time.current = current;
        } catch {
          // YouTube'un başka biçimdeki mesajları
        }
      }
      window.addEventListener("message", onMessage);
      return () => window.removeEventListener("message", onMessage);
    }, []);

    const params = new URLSearchParams({
      enablejsapi: "1",
      rel: "0",
      origin: window.location.origin,
      start: String(Math.floor(start)),
    });
    return (
      <iframe
        ref={frameRef}
        src={`${YOUTUBE_ORIGIN}/embed/${encodeURIComponent(videoId)}?${params}`}
        title={title}
        allow="encrypted-media; picture-in-picture; fullscreen"
        allowFullScreen
        // YouTube konumu bildirmeye ancak "listening" mesajından sonra başlar.
        onLoad={() => frameRef.current?.contentWindow?.postMessage(JSON.stringify({ event: "listening", id: videoId }), YOUTUBE_ORIGIN)}
        className="aspect-video w-full rounded-panel border-0 bg-black"
      />
    );
  },
);

function post(frame: HTMLIFrameElement | null, func: string, args: unknown[]) {
  frame?.contentWindow?.postMessage(JSON.stringify({ event: "command", func, args }), YOUTUBE_ORIGIN);
}
