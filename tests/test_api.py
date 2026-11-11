from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_dashboard_and_workflow_state_are_exposed() -> None:
    client = TestClient(app)
    dashboard = client.get("/dashboard")
    state = client.get("/workflow/state")
    assert dashboard.status_code == 200
    assert state.status_code == 200
    assert dashboard.json()["status"] == state.json()["status"]
    assert "browser_connected" in dashboard.json()
