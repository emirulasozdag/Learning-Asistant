"""PostgreSQL full-text arama ayarları; ingestion ve retrieval aynı yapılandırmayı kullanır."""

_CONFIGS = {"tr": "turkish", "en": "english"}


def ts_config(language: str) -> str:
    """Dersin dili → PostgreSQL text search configuration adı."""
    return _CONFIGS.get(language, "simple")
