"""İstek gövdesi boyut sınırı (#21): sınır gövde okunurken uygulanır.

Çok parçalı form, uç fonksiyon çalışmadan önce tamamen okunup geçici dosyaya yazılır; boyut
uç fonksiyonda denetlenirse sınırı aşan gövde de diske yazılmış olur. Bu ASGI ara katmanı
`Content-Length`'e bakar ve gelen baytları sayar; sınır aşılınca okumayı keser ve 413 döner.
"""

import json
import re

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

# Çok parçalı formun dosya dışındaki alanları ve sınırlayıcıları için pay.
MULTIPART_OVERHEAD_BYTES = 1024 * 1024
_UPLOAD_PATH = re.compile(r"^/courses/\d+/materials/?$")


class RequestTooLarge(Exception):
    pass


def request_limit(method: str, path: str) -> int:
    """Materyal yüklemesi medya sınırını (en büyük dosya), diğer istekler JSON sınırını alır."""
    if method == "POST" and _UPLOAD_PATH.match(path):
        return settings.max_media_bytes + MULTIPART_OVERHEAD_BYTES
    return settings.max_request_bytes


class RequestSizeLimit:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = request_limit(scope["method"], scope.get("root_path", "") + scope["path"])
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await _too_large(send, limit)
            return

        received = 0
        started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise RequestTooLarge
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except RequestTooLarge:
            if not started:
                await _too_large(send, limit)


async def _too_large(send: Send, limit: int) -> None:
    body = json.dumps(
        {
            "detail": f"İstek {limit // (1024 * 1024)} MB sınırını aşıyor.",
            "code": "file_too_large",
        },
        ensure_ascii=False,
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"connection", b"close"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
