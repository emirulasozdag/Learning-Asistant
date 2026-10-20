"""Şifre özeti: argon2id (ADR-1). Şifre hiçbir yerde düz metin tutulmaz ya da loglanmaz."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()

# Kayıtta istenen uzunluk. Üst sınır, çok uzun girdiyle özet hesabını pahalılaştırmayı önler.
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 256

# Bilinmeyen e-postayla girişte de bir özet doğrulanır: yanıt süresinden hesabın varlığı
# anlaşılmasın.
_DUMMY_HASH = _hasher.hash("hesap-yok")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    if len(password) > MAX_PASSWORD_LENGTH:
        return False
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)
