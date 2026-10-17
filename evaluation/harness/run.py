"""Tek komutla tam değerlendirme koşusu.

Kullanım (uygulandığında): python -m harness.run --condition full --out runs/
"""

from pathlib import Path

from harness.conditions import Condition


def run_evaluation(conditions: list[Condition], gold_dir: Path, out_dir: Path) -> Path:
    """Gold set'i verilen koşullarda koştur, tüm metrikleri hesapla, run log'u yaz."""
    raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit("Değerlendirme harness'i henüz uygulanmadı (WP13).")
