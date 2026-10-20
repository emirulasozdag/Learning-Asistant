"""Bilinen modellerin fiyatı ve düşünme (thinking) seviyeleri.

Fiyatlar Gemini Developer API'nin ücretli (Standard) katmanı, USD / 1M token; kaynak:
https://ai.google.dev/gemini-api/docs/pricing ve model sayfaları (2026-10-20'de okundu).
Fiyatlar değişir: gemini-3.8-flash / 3.6-flash için ikiye katlanma, gemini-4-argon için
1 Aralık 2026'dan itibaren artış duyurulmuş. Maliyet kaydı tahmindir; fatura esastır.

Ücretsiz katmanda gönderilen içerik Google ürünlerini geliştirmek için kullanılabilir ve insan
incelemesine açıktır; kişisel veri gönderilmemeli (ADR-5, ADR-7). Pilot ücretli katmanla yapılır.
"""

from dataclasses import dataclass

THINKING_LEVELS = ("minimal", "low", "medium", "high")


@dataclass(frozen=True)
class ModelInfo:
    input_per_m: float
    output_per_m: float  # düşünme token'ları dahil
    cached_input_per_m: float
    thinking_levels: tuple[str, ...]


MODELS: dict[str, ModelInfo] = {
    "gemini-3.8-flash": ModelInfo(0.75, 3.75, 0.075, ("low", "medium", "high")),
    "gemini-3.6-flash": ModelInfo(0.75, 3.75, 0.075, THINKING_LEVELS),
    "gemini-3.5-flash-lite": ModelInfo(0.30, 2.50, 0.03, THINKING_LEVELS),
    "gemini-3.1-flash-lite": ModelInfo(0.25, 1.50, 0.025, THINKING_LEVELS),
    "gemini-3.1-pro-preview": ModelInfo(2.00, 12.00, 0.20, ("low", "medium", "high")),
    "gemini-4-argon": ModelInfo(2.00, 10.00, 0.10, ("low", "medium", "high")),
}


def thinking_level_for(model: str, requested: str) -> str:
    """İstenen seviye model tarafından desteklenmiyorsa en yakın desteklenen seviye.

    Örn. gemini-3.8-flash "minimal" kabul etmez (istek hata verir); "low" kullanılır.
    Bilinmeyen modelde istenen seviye olduğu gibi gönderilir.
    """
    info = MODELS.get(model)
    if info is None or requested in info.thinking_levels or requested not in THINKING_LEVELS:
        return requested
    order = THINKING_LEVELS.index(requested)
    return min(info.thinking_levels, key=lambda level: abs(THINKING_LEVELS.index(level) - order))


def estimate_cost_usd(
    model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0
) -> float | None:
    """Tahmini maliyet; fiyatı bilinmeyen modelde None. `input_tokens` önbellektekileri içerir."""
    info = MODELS.get(model)
    if info is None:
        return None
    fresh = max(input_tokens - cached_tokens, 0)
    return (
        fresh * info.input_per_m
        + cached_tokens * info.cached_input_per_m
        + output_tokens * info.output_per_m
    ) / 1_000_000
