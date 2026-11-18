"""Ders videosundan slayt karelerini çıkarma (#24, ADR-10).

Video düzenli aralıkla örneklenir (`sample_interval_s`). Her örnekten küçük, gri bir parmak izi
alınır ve sahnenin başladığı örneğin parmak iziyle karşılaştırılır. Görüntü `min_stable_s`
boyunca sabit kalırsa (slayt, duraklatılmış ekran) o sahneden bir kare alınır; kare, sahnenin
ekranda kaldığı aralıkla (`t_start`–`t_end`) saklanır. Kısa bir kesintiden sonra aynı slayta
dönülürse (konuşmacı önden geçti, kamera kısa süre değişti) yeni kare alınmaz, önceki karenin
aralığı uzar.

Son örneklerde sürekli değişen pikseller (köşedeki konuşmacı kamerası, imleç) karşılaştırmaya
katılmaz: kamera kutusu oynarken slayt yine sabit sayılır, bir kez değişen pikseller (yeni slayt,
eklenen satır) ise sayılır. Ekranın büyük kısmı hareketliyse (kamera görüntüsü, canlı kod
yazımı) sahne slayt sayılmaz ve kare alınmaz.

Sahne takibi (`SceneTracker`) saf mantıktır ve video çözmeden test edilir. Video çözme (`av`) ve
görüntü kaydetme (`PIL`) yalnızca `extract_frames` çağrılınca içe aktarılır: bu paketler Docker
imajındadır, CI'da (`.[dev]`) yoktur.
"""

import logging
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.jobs.queue import JobCancelled

logger = logging.getLogger(__name__)


class FrameExtractionError(Exception):
    """Video çözülemedi; kareler çıkarılamadı (transkript bundan etkilenmez)."""


@dataclass(frozen=True)
class FrameParams:
    """Kare seçim ayarları. Varsayılanlar slayt ağırlıklı ders videosu içindir; gerçek derslerde
    kalibre edilmelidir (ADR-10)."""

    # Örnekleme aralığı; kare zamanlarının hassasiyeti bu kadardır.
    sample_interval_s: float = 0.5
    # Parmak izinin boyutu (genişlik, yükseklik); küçük boyut sıkıştırma gürültüsünü siler.
    signature_size: tuple[int, int] = (128, 72)
    # Gri ton farkı bunun üstündeki parmak izi pikseli "değişti" sayılır (0–255).
    pixel_threshold: int = 16
    # Sahnenin ilk örneğine göre değişen (hareketli bölge dışındaki) piksel oranı bunun
    # altındaysa sahne sürer (128x72'de ~28 piksel). Ölçüm (720p, H.264): slayta eklenen tek
    # satır 44–56 piksel değiştirir, sıkıştırma gürültüsü 0.
    stable_ratio: float = 0.003
    # Son `motion_window` örnekte en az `motion_hits` kez değişen piksel hareketli bölgedir.
    motion_window: int = 8
    motion_hits: int = 3
    # Hareketli bölge her yönde bu kadar parmak izi pikseli genişletilir (720p'de ~40 piksel):
    # kamera kutusundaki konuşmacı kutunun yeni bir köşesine kayınca sahne bölünmesin.
    motion_margin: int = 4
    # Hareketli bölge ekranın bu payından büyükse sahne slayt sayılmaz (kamera görüntüsü).
    max_motion_share: float = 0.25
    # Görüntü bu kadar süre sabit kalınca sahne slayt sayılır ve kare alınır.
    min_stable_s: float = 2.0
    # Önceki kareden bu süreden kısa bir kesintiyle aynı görüntüye dönülürse aynı kare sayılır.
    merge_gap_s: float = 10.0
    # Video başına en çok kare (disk ve OCR süresi sınırı); aşılırsa sonraki sahneler atlanır.
    max_frames: int = 300
    # Kaydedilen görüntünün en büyük genişliği (daha büyük video küçültülür; OCR için yeterli).
    max_image_width: int = 1920


@dataclass
class Scene:
    """Sabit kalan bir sahne: ekranda kaldığı aralık ve karenin alındığı an."""

    index: int
    t_start: float
    t_end: float
    t_frame: float
    signature: bytes


def changed_pixels(a: bytes, b: bytes, pixel_threshold: int) -> int:
    """İki parmak izi (aynı boyutta gri piksel baytları) arasında `pixel_threshold`tan çok
    değişen pikseller, bit kümesi olarak (i. bit = i. piksel)."""
    if len(a) != len(b) or not a:
        raise ValueError("Parmak izleri aynı boyutta ve boş olmamalı")
    bits = "".join("1" if abs(x - y) > pixel_threshold else "0" for x, y in zip(a, b, strict=True))
    return int(bits[::-1], 2)


def dilate(mask: int, width: int, height: int, margin: int) -> int:
    """Bit kümesindeki her pikseli `margin` kadar yatay ve dikey genişletir (kare komşuluk).
    Yatay kaydırmada satır sonundan sonrakine taşan bitler atılır."""
    if not mask or margin <= 0:
        return mask
    row = (1 << width) - 1
    rows = [(mask >> (y * width)) & row for y in range(height)]
    widened = []
    for bits in rows:
        out = bits
        for shift in range(1, margin + 1):
            out |= (bits << shift) | (bits >> shift)
        widened.append(out & row)
    result = 0
    for y in range(height):
        out = 0
        for other in range(max(0, y - margin), min(height, y + margin + 1)):
            out |= widened[other]
        result |= out << (y * width)
    return result


class SceneTracker:
    """Örnekleri sırayla alır; hangi örneğin kare olarak kaydedileceğini söyler.

    `feed` bir örnek için yeni bir sahnenin kare zamanı geldiyse o sahneyi döndürür (çağıran o
    örneğin tam görüntüsünü kaydeder); aksi hâlde None. `finish` videonun sonunda tüm sahneleri
    aralıklarıyla döndürür.
    """

    def __init__(self, params: FrameParams) -> None:
        self.params = params
        self.scenes: list[Scene] = []
        self.limit_reached = False
        self._anchor: bytes | None = None
        self._previous: bytes | None = None
        # Son örneklerde bir öncekine göre değişen pikseller (bit kümeleri).
        self._recent: deque[int] = deque(maxlen=params.motion_window)
        # Hareketli bölge (bit kümesi); karşılaştırmalara katılmaz.
        self._motion = 0
        self._run_start = 0.0
        self._last_t = 0.0
        # Bu koşu (sabit görüntü) bir sahneye bağlandıysa o sahne.
        self._run_scene: Scene | None = None

    def feed(self, t: float, signature: bytes) -> Scene | None:
        params = self.params
        if self._previous is not None:
            self._recent.append(changed_pixels(self._previous, signature, params.pixel_threshold))
        self._previous = signature
        # Karşılaştırmada son saniyelerin küçük hareketli bölgesi yok sayılır (kamera kutusu bir
        # an durunca sahne bölünmesin). Bölge büyükse (tam ekran kamera az önce bitti) yok
        # sayılmaz: yoksa ardından gelen slayt değişimleri görünmez olurdu. "Şu an hareketli mi"
        # yalnızca son değişikliğe bakar (kamera biter bitmez gelen slaytın başı gecikmesin).
        motion = self._moving_pixels()
        moving_now = motion & (self._recent[-1] if self._recent else 0)
        moving_share = moving_now.bit_count() / len(signature)
        small = motion.bit_count() / len(signature) <= params.max_motion_share
        self._motion = motion if small else 0
        if (
            self._anchor is None
            or moving_share > params.max_motion_share
            or self._changed(self._anchor, signature)
        ):
            if self._run_scene is not None:
                # Sahne, değişikliğin ilk görüldüğü örneğe kadar ekrandaydı.
                self._run_scene.t_end = t
            self._anchor = signature
            self._run_start = t
            self._run_scene = None
            self._last_t = t
            return None
        self._last_t = t
        if self._run_scene is not None:
            self._run_scene.t_end = t
            return None
        if t - self._run_start < params.min_stable_s:
            return None
        previous = self.scenes[-1] if self.scenes else None
        if (
            previous is not None
            and self._run_start - previous.t_end <= params.merge_gap_s
            and not self._changed(previous.signature, signature)
        ):
            self._run_scene = previous
            previous.t_end = t
            return None
        if len(self.scenes) >= params.max_frames:
            self.limit_reached = True
            return None
        scene = Scene(len(self.scenes), self._run_start, t, t, signature)
        self.scenes.append(scene)
        self._run_scene = scene
        return scene

    def finish(self, end_t: float | None = None) -> list[Scene]:
        """Sahneler; açık kalan son sahnenin sonu videonun sonuna (`end_t`) uzatılır."""
        if self._run_scene is not None:
            self._run_scene.t_end = max(self._run_scene.t_end, end_t or self._last_t)
        return self.scenes

    def _moving_pixels(self) -> int:
        """Son örneklerde en az `motion_hits` kez değişen pikseller, `motion_margin` kadar
        genişletilmiş (bit kümesi)."""
        counts = [0] * (self.params.motion_hits + 1)
        for changed in self._recent:
            for hits in range(self.params.motion_hits, 0, -1):
                counts[hits] |= counts[hits - 1] & changed if hits > 1 else changed
        return dilate(
            counts[self.params.motion_hits], *self.params.signature_size, self.params.motion_margin
        )

    def _changed(self, a: bytes, b: bytes) -> bool:
        """Hareketli bölge dışında değişen piksellerin oranı eşiği geçiyor mu."""
        changed = changed_pixels(a, b, self.params.pixel_threshold) & ~self._motion
        return changed.bit_count() / len(a) >= self.params.stable_ratio


@dataclass(frozen=True)
class ExtractedFrame:
    """Diske kaydedilmiş kare görüntüsü ve sahnesinin zamanları."""

    ordinal: int
    t_start: float
    t_end: float
    t_frame: float
    image_path: Path


def extract_frames(
    media_path: Path,
    out_dir: Path,
    should_stop: Callable[[], bool] = lambda: False,
    params: FrameParams | None = None,
) -> list[ExtractedFrame]:
    """Videonun slayt karelerini `out_dir`e PNG olarak kaydeder; zamana göre sıralı döner.

    Videosu olmayan medyada (ses dosyası, yalnızca kapak resmi olan ses) boş liste. Video
    çözülemezse `FrameExtractionError`; iptalde `JobCancelled`. Hata ya da iptalde `out_dir`
    çağıran tarafından silinir.
    """
    import av

    params = params or FrameParams()
    out_dir.mkdir(parents=True, exist_ok=True)
    tracker = SceneTracker(params)
    width, height = params.signature_size
    saved: dict[int, Path] = {}
    duration: float | None = None
    try:
        with av.open(str(media_path)) as container:
            stream = _video_stream(container)
            if stream is None:
                return []
            if container.duration:
                duration = container.duration / av.time_base
            # Bazı dosyalarda zaman 0'dan değil biraz sonra başlar (ör. 0,067 sn); transkript
            # zamanları medyanın başından ölçüldüğü için kare zamanları da oradan ölçülür.
            start = container.start_time / av.time_base if container.start_time else 0.0
            for t, frame in _samples(container, stream, params.sample_interval_s, start):
                if should_stop():
                    raise JobCancelled(media_path.name)
                signature = _gray_signature(frame, width, height)
                scene = tracker.feed(t, signature)
                if scene is not None:
                    saved[scene.index] = _save_png(frame, out_dir, scene.index, params)
    except JobCancelled:
        raise
    except Exception as exc:
        logger.exception("Video kareleri çıkarılamadı: %s", media_path.name)
        raise FrameExtractionError("Video kareleri çıkarılamadı.") from exc
    if tracker.limit_reached:
        logger.warning(
            "%s: kare sınırına (%d) ulaşıldı; sonraki sahneler atlandı",
            media_path.name,
            params.max_frames,
        )
    scenes = tracker.finish(duration)
    return [
        ExtractedFrame(
            ordinal=scene.index,
            t_start=round(scene.t_start, 3),
            t_end=round(scene.t_end, 3),
            t_frame=round(scene.t_frame, 3),
            image_path=saved[scene.index],
        )
        for scene in scenes
    ]


def media_duration(media_path: Path) -> float | None:
    """Medya kabının bildirdiği süre (saniye); kap süre bildirmiyorsa None (#25: süre sınırı).
    Dosya açılamazsa `FrameExtractionError`."""
    import av

    try:
        with av.open(str(media_path)) as container:
            if container.duration is None:
                return None
            return container.duration / av.time_base
    except Exception as exc:
        logger.exception("Medya süresi okunamadı: %s", media_path.name)
        raise FrameExtractionError("Video dosyası açılamadı.") from exc


def _video_stream(container: Any) -> Any:
    """Gerçek video akışı; ses dosyalarındaki kapak resmi (attached picture) sayılmaz."""
    import av

    for stream in container.streams.video:
        if not stream.disposition & av.stream.Disposition.attached_pic:
            stream.thread_type = "AUTO"
            return stream
    return None


def _samples(
    container: Any, stream: Any, interval: float, start: float = 0.0
) -> Iterator[tuple[float, Any]]:
    """Her `interval` saniyede bir çözülmüş kare (medyanın başından zamanı, kendisi); arada
    kalan kareler atlanır."""
    next_t = 0.0
    for frame in container.decode(stream):
        if frame.time is None:
            continue
        t = max(0.0, float(frame.time) - start)
        if t + 1e-6 < next_t:
            continue
        yield t, frame
        while next_t <= t + 1e-6:
            next_t += interval


def _gray_signature(frame: Any, width: int, height: int) -> bytes:
    """Karenin küçültülmüş gri baytları (satır sonu dolguları atılır)."""
    plane = frame.reformat(width=width, height=height, format="gray").planes[0]
    data = bytes(plane)
    if plane.line_size == width:
        return data
    stride = plane.line_size
    return b"".join(data[row * stride : row * stride + width] for row in range(height))


def _save_png(frame: Any, out_dir: Path, index: int, params: FrameParams) -> Path:
    image = frame.to_image()
    if image.width > params.max_image_width:
        height = round(image.height * params.max_image_width / image.width)
        image = image.resize((params.max_image_width, height))
    path = out_dir / f"{index}.png"
    image.save(path, format="PNG", optimize=True)
    return path
