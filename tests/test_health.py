from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_cors_allows_any_origin():
    r = client.get("/health", headers={"Origin": "http://evil.example"})
    assert r.headers["access-control-allow-origin"] == "http://evil.example"
