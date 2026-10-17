def load_history(conversation_id: int) -> list[dict[str, str]]:
    """Takip soruları için önceki mesajlar."""
    raise NotImplementedError


def rewrite_follow_up(question: str, history: list[dict[str, str]]) -> str:
    """Takip sorusunu geçmişe göre bağımsız bir arama sorgusuna çevir."""
    raise NotImplementedError
