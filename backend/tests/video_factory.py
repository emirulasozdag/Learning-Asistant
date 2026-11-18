"""Testler için gerçek ders videosu üretimi: PDF slaytları → MP4 (H.264) (#24).

Slaytlar PyMuPDF ile çizilir ve PyAV ile kodlanır; internetten video indirilmez, ders içeriği
repoya girmez. `av` yalnızca Docker imajında vardır; bu yardımcıyı kullanan testler `av`
yoksa atlanır.
"""

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import pymupdf

WIDTH, HEIGHT = 1280, 720
FPS = 10


@dataclass
class Slide:
    """`seconds` boyunca ekranda kalan slayt: başlık, satırlar ve isteğe bağlı kutu-ok diyagramı."""

    seconds: float
    title: str = ""
    lines: list[str] = field(default_factory=list)
    # (kutu metni, kutu metni, ...) soldan sağa oklarla bağlanır.
    diagram: tuple[str, ...] = ()
    # True: kutular koyu renkle dolu, yazı beyaz (PowerPoint'in varsayılan şekil stili gibi).
    filled: bool = False
    # Başlığın punto boyutu (PowerPoint başlık slaytı ~60–80; gerçek derste kaçırılmıştı).
    title_size: int = 44
    # True: içerik yerine her karede değişen desen (kamera görüntüsü gibi; sabit sahne olmaz).
    moving: bool = False
    # Arka plan gri tonu; boş (yazısız) slayt için kullanılır.
    background: float = 1.0
    # True: sağ alt köşede her karede değişen küçük kutu (konuşmacı kamerası gibi).
    webcam: bool = False


def render_slide(slide: Slide, frame_index: int = 0) -> bytes:
    """Slaytın RGB baytları (WIDTH x HEIGHT)."""
    document = pymupdf.open()
    page = document.new_page(width=WIDTH, height=HEIGHT)
    page.draw_rect(page.rect, color=None, fill=(slide.background,) * 3)
    if slide.moving:
        # Her karede yer değiştiren büyük bloklar: kamera hareketi gibi, sahne hiç durmaz.
        for i in range(12):
            x = (frame_index * 37 + i * 101) % (WIDTH - 200)
            y = (frame_index * 53 + i * 67) % (HEIGHT - 150)
            shade = ((frame_index + i) % 5) / 5
            page.draw_rect(pymupdf.Rect(x, y, x + 200, y + 150), color=None, fill=(shade,) * 3)
    if slide.title:
        page.insert_text(
            (80, 60 + slide.title_size), slide.title, fontsize=slide.title_size, fontname="helv"
        )
    first_line = max(200, 150 + slide.title_size)  # büyük başlığın altından başla
    for i, line in enumerate(slide.lines):
        page.insert_text((80, first_line + i * 56), line, fontsize=34, fontname="cour")
    if slide.diagram:
        box_w, gap, top = 260, 120, 360
        for i, label in enumerate(slide.diagram):
            left = 80 + i * (box_w + gap)
            box = pymupdf.Rect(left, top, left + box_w, top + 120)
            fill = (0.12, 0.39, 0.49) if slide.filled else None
            page.draw_rect(box, color=(0, 0, 0), fill=fill, width=3)
            page.insert_text(
                (left + 24, top + 72),
                label,
                fontsize=32,
                fontname="helv",
                color=(1, 1, 1) if slide.filled else (0, 0, 0),
            )
            if i:
                page.draw_line((left - gap + 4, top + 60), (left - 8, top + 60), width=3)
                page.draw_polyline(
                    [(left - 26, top + 46), (left - 8, top + 60), (left - 26, top + 74)], width=3
                )
    if slide.webcam:
        # 240x135 (ekranın ~%3,5'i): içinde her karede yer değiştiren bir "kafa" ve gölgesi.
        camera = pymupdf.Rect(WIDTH - 260, HEIGHT - 155, WIDTH - 20, HEIGHT - 20)
        page.draw_rect(camera, color=None, fill=(0.3, 0.3, 0.3))
        x = camera.x0 + 40 + (frame_index * 23) % 120
        y = camera.y0 + 20 + (frame_index * 17) % 60
        page.draw_oval(pymupdf.Rect(x, y, x + 70, y + 80), color=None, fill=(0.9, 0.8, 0.7))
    pixmap = page.get_pixmap(alpha=False)
    data = bytes(pixmap.samples)
    document.close()
    return data


def make_lecture_video(path: Path, slides: list[Slide], fps: int = FPS) -> Path:
    """Slaytları sırayla gösteren bir MP4 yazar ve yolunu döndürür."""
    import av

    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("libx264", rate=fps)
        stream.width, stream.height, stream.pix_fmt = WIDTH, HEIGHT, "yuv420p"
        stream.codec_context.time_base = Fraction(1, fps)
        index = 0
        for slide in slides:
            static = None if slide.moving or slide.webcam else render_slide(slide)
            for _ in range(round(slide.seconds * fps)):
                rgb = static if static is not None else render_slide(slide, index)
                frame = av.VideoFrame(WIDTH, HEIGHT, "rgb24")
                frame.planes[0].update(rgb)
                frame.pts = index
                frame.time_base = Fraction(1, fps)
                for packet in stream.encode(frame.reformat(format="yuv420p")):
                    container.mux(packet)
                index += 1
        for packet in stream.encode():
            container.mux(packet)
    return path
