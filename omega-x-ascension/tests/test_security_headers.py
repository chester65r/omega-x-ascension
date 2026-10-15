from fastapi.testclient import TestClient

from omega.main import app


def test_every_response_gets_baseline_security_headers():
    response = TestClient(app).get("/health/live")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "SAMEORIGIN"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "camera=()" in response.headers["permissions-policy"]
