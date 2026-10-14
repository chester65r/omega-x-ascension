from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

import omega.main as main


def test_http_responses_include_request_id_and_security_headers():
    response = TestClient(main.app).get("/version")
    assert response.status_code == 200
    assert response.headers.get("x-request-id")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_metrics_are_hidden_in_production_when_no_scraper_token(monkeypatch):
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: SimpleNamespace(env="production", metrics_token=None),
    )
    response = TestClient(main.app).get("/metrics")
    assert response.status_code == 404


def test_metrics_require_matching_bearer_token_when_configured(monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: SimpleNamespace(env="production", metrics_token=SecretStr("metrics-test-token")),
    )
    client = TestClient(main.app)
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
    authorized = client.get("/metrics", headers={"Authorization": "Bearer metrics-test-token"})
    assert authorized.status_code == 200
    assert "omega_http_requests_total" in authorized.text
