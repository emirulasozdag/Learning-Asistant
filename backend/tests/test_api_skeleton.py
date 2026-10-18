"""İskelet endpoint'lerinin var olduğunu ve henüz 501 döndüğünü doğrular.

Bir özellik uygulandığında ilgili satır buradan kaldırılıp gerçek testine taşınır.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

SKELETON_ENDPOINTS = [
    ("post", "/practice", {"json": {"course_id": 1, "type": "code_tracing"}}),
    ("post", "/practice/1/answer", {"json": {"answer": "mid = (lo + hi) // 2"}}),
    ("get", "/courses/1/learning-record", {}),
    ("get", "/instructor/courses/1/mistakes", {}),
    (
        "post",
        "/instructor/reviews",
        {"json": {"target_type": "message", "target_id": 1, "decision": "approve"}},
    ),
    ("get", "/instructor/courses/1/rubrics", {}),
    (
        "post",
        "/instructor/courses/1/rubrics",
        {
            "json": {
                "concept": "binary search",
                "reference_answer": "Dizi sıralı olduğu için hedef orta elemandan büyükse...",
                "criteria": [{"description": "Sıralılık koşulunu belirtir", "points": 1}],
            }
        },
    ),
]


@pytest.mark.parametrize(("method", "path", "kwargs"), SKELETON_ENDPOINTS)
def test_skeleton_endpoint_returns_501(method: str, path: str, kwargs: dict) -> None:
    response = getattr(client, method)(path, **kwargs)

    assert response.status_code == 501
