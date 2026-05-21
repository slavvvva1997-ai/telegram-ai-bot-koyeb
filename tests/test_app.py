from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_webhook_rejects_bad_secret() -> None:
    with TestClient(app) as client:
        response = client.post("/webhook/bad", json={})
    assert response.status_code == 403
