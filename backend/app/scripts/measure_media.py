"""Bir ders videosunun işlenmesini ölçer: süre, bellek ve disk (#31).

Gerçek işlem hattının adımlarını sırayla çalıştırır: süre okuma, transkripsiyon (faster-whisper,
`TRANSCRIPTION_MODEL`), transkript vektörleri, kare çıkarma, OCR (Tesseract) ve kare vektörleri.
Veritabanına yazmaz, dosyayı bir yere göndermez; kareler geçici klasöre yazılır ve silinir.

Kullanım (worker konteynerinde, medya dosyası bağlanarak):

    docker compose run --rm --no-deps -v "<klasör>:/media:ro" worker \
        python -m app.scripts.measure_media /media/ders.mp4 --language tr

Çıktı: adım başına süre (sn), gerçek zamana oranı (işlem süresi / medya süresi) ve sürecin en
yüksek bellek kullanımı (RSS, MB; Tesseract alt süreçleri dahil değil). Tesseract yoksa ya da
çalışmazsa OCR adımı `error` sayar: önce imajın güncel olduğunu denetleyin.
"""

import argparse
import json
import os
import resource
import shutil
import sys
import tempfile
import time
from pathlib import Path

from app.core.config import settings
from app.embeddings.provider import get_embedder
from app.ingestion.frames import extract_frames, media_duration
from app.ingestion.ocr import OcrError, read_image, tesseract_languages
from app.ingestion.transcribe import get_transcriber


def peak_mb(who: int = resource.RUSAGE_SELF) -> float:
    # Linux'ta ru_maxrss KB'dir.
    return resource.getrusage(who).ru_maxrss / 1024


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("media", type=Path)
    parser.add_argument("--language", default="tr", help="dersin dili (tr/en)")
    parser.add_argument("--json", action="store_true", help="yalnızca JSON yaz")
    args = parser.parse_args()

    steps: dict[str, dict[str, float]] = {}

    def step(name: str, started: float, **extra: float) -> None:
        steps[name] = {"seconds": round(time.perf_counter() - started, 2), **extra}
        steps[name]["peak_rss_mb"] = round(peak_mb(), 1)

    started = time.perf_counter()
    duration = media_duration(args.media)
    step("duration", started)
    if not duration:
        sys.exit("Medyanın süresi okunamadı.")

    embedder = get_embedder()
    started = time.perf_counter()
    embedder.embed_query("ısınma")  # modeli belleğe al; ilk çağrının süresi ayrı görünsün
    step("embedding_model_load", started)

    transcript: list[str] = []
    if settings.transcription_model:
        started = time.perf_counter()
        segments, _, warnings = get_transcriber().transcribe(args.media, args.language)
        transcript = [segment.text.strip() for segment in segments if segment.text.strip()]
        step("transcription", started, segments=len(segments), warnings=len(warnings))
        started = time.perf_counter()
        embedder.embed_passages(transcript)
        step("transcript_embedding", started, passages=len(transcript))

    work = Path(tempfile.mkdtemp(prefix="measure-frames-"))
    try:
        started = time.perf_counter()
        frames = extract_frames(args.media, work)
        disk = sum(frame.image_path.stat().st_size for frame in frames)
        step("frame_extraction", started, frames=len(frames), frames_disk_mb=round(disk / 1e6, 2))

        languages = tesseract_languages(args.language)
        started = time.perf_counter()
        texts, statuses = [], {}
        for frame in frames:
            try:
                result = read_image(frame.image_path, languages)
            except OcrError:
                statuses["error"] = statuses.get("error", 0) + 1
                continue
            statuses[result.status] = statuses.get(result.status, 0) + 1
            if result.text:
                texts.append(result.text)
        step("ocr", started, **statuses)
        steps["ocr"]["seconds_per_frame"] = round(steps["ocr"]["seconds"] / max(len(frames), 1), 2)

        started = time.perf_counter()
        if texts:
            embedder.embed_passages(texts)
        step("frame_embedding", started, passages=len(texts))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    # Model yükleme ve süre okuma bir kezlik; işin süresine sayılmaz.
    total = sum(
        values["seconds"]
        for name, values in steps.items()
        if name not in {"duration", "embedding_model_load"}
    )
    report = {
        "media": args.media.name,
        "media_mb": round(args.media.stat().st_size / 1e6, 1),
        "duration_s": round(duration, 1),
        "transcription_model": settings.transcription_model or None,
        "embedding_model": settings.embedding_model,
        "cpus": len(os.sched_getaffinity(0)),
        "steps": steps,
        "total_seconds": round(total, 1),
        "realtime_factor": round(total / duration, 3),
        "peak_rss_mb": round(peak_mb(), 1),
    }
    if not args.json:
        print_table(report)
    print(json.dumps(report, ensure_ascii=False))


def print_table(report: dict) -> None:
    print(f"{report['media']}: {report['duration_s']} sn, {report['media_mb']} MB, ", end="")
    print(f"{report['cpus']} CPU")
    for name, values in report["steps"].items():
        extra = ", ".join(
            f"{key}={value}"
            for key, value in values.items()
            if key not in {"seconds", "peak_rss_mb"}
        )
        print(
            f"  {name:22} {values['seconds']:8.2f} sn   "
            f"RSS {values['peak_rss_mb']:7.1f} MB   {extra}"
        )
    print(
        f"  toplam iş: {report['total_seconds']} sn "
        f"(medya süresinin {report['realtime_factor']} katı)"
    )


if __name__ == "__main__":
    main()
