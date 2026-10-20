"""İçerik parmak izleri: dokümanlar ve koşu girdileri yeniden indekslemeden bağımsız tanınır."""

import hashlib
from pathlib import Path

_CHUNK = 1 << 20


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while block := file.read(_CHUNK):
            digest.update(block)
    return digest.hexdigest()


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
