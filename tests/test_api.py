import pytest
from fastapi.testclient import TestClient

from waterjet_lab import api


@pytest.fixture
def client():
    api.sessions.clear()
    with TestClient(api.app) as item:
        yield item
    api.sessions.clear()


def session(client):
    result = client.post("/api/sessions")
    assert result.status_code == 201
    return result.json()["session_id"]


def test_home_assets_health_and_security_headers(client):
    page = client.get("/")
    assert page.status_code == 200 and "Vessel control console" in page.text
    preview = client.head("/")
    assert preview.status_code == 200 and not preview.content
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/healthz").json()["simulation_only"] is True
    reference = client.get("/api/docs")
    assert reference.status_code == 200 and "Simulation API" in reference.text
    assert "<script" not in reference.text  # reference works under the same self-only CSP
    assert client.get("/openapi.json").json()["info"]["title"] == "Waterjet Control Lab"


def test_sessions_are_isolated_and_actions_are_explicit(client):
    first, second = session(client), session(client)
    result = client.post(f"/api/sessions/{first}/scenario", json={"name": "pressure"}).json()
    assert result["mode"] == "FAULT"
    assert client.get(f"/api/sessions/{second}").json()["mode"] == "DISARMED"
    assert client.post(f"/api/sessions/{second}/action", json={"action": "run"}).json()["accepted"] is False


def test_tick_and_csv_export(client):
    sid = session(client)
    for action in ["arm", "run"]:
        assert client.post(f"/api/sessions/{sid}/action", json={"action": action}).json()["accepted"]
    result = client.post(f"/api/sessions/{sid}/tick", json={"command": {"surge": 0.5}, "scans": 2})
    assert result.json()["time_s"] == 0.1
    csv = client.get(f"/api/sessions/{sid}/export.csv")
    assert csv.status_code == 200 and "heading_deg" in csv.text
    assert "attachment" in csv.headers["content-disposition"]
    assert len(client.get(f"/api/sessions/{sid}/history").json()) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"command": {"surge": 2}},
        {"command": {}, "scans": 1000},
        {"command": {}, "scans": True},
        {"command": {"hardware": "on"}},
        {"command": {"control": "invalid"}},
    ],
)
def test_untrusted_api_commands_are_validated(client, payload):
    sid = session(client)
    assert client.post(f"/api/sessions/{sid}/tick", json=payload).status_code == 422


def test_nonfinite_json_is_rejected_without_response_serialization_crash(client):
    sid = session(client)
    response = client.post(
        f"/api/sessions/{sid}/tick",
        content='{"command":{"surge":NaN}}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_invalid_faults_actions_and_wind_rejected(client):
    sid = session(client)
    assert (
        client.post(f"/api/sessions/{sid}/fault", json={"fault": "hardware", "enabled": True}).status_code
        == 422
    )
    assert client.post(f"/api/sessions/{sid}/action", json={"action": "restart"}).status_code == 422
    assert client.post(f"/api/sessions/{sid}/wind", json={"east_n": 1001, "north_n": 0}).status_code == 422


def test_fault_endpoint_drives_controller_and_clear_does_not_restart(client):
    sid = session(client)
    client.post(f"/api/sessions/{sid}/scenario", json={"name": "harbor"})
    client.post(f"/api/sessions/{sid}/fault", json={"fault": "overheat", "enabled": True})
    response = client.post(f"/api/sessions/{sid}/tick", json={"command": {"surge": 0.5}}).json()
    assert response["mode"] == "FAULT" and response["port_output"] == 0
    response = client.post(f"/api/sessions/{sid}/fault", json={"fault": "overheat", "enabled": False}).json()
    assert response["mode"] == "FAULT"


def test_expiry_capacity_and_deletion(client, monkeypatch):
    monkeypatch.setattr(api, "MAX_SESSIONS", 1)
    sid = session(client)
    assert client.post("/api/sessions").status_code == 503
    api.sessions[sid].touched -= api.SESSION_TTL_S + 1
    assert client.get(f"/api/sessions/{sid}").status_code == 404
    sid = session(client)
    assert client.delete(f"/api/sessions/{sid}").status_code == 204
    assert client.get(f"/api/sessions/{sid}").status_code == 404
