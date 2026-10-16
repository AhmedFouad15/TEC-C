from fastapi.testclient import TestClient

from tecc_brain import __version__
from tecc_brain.app import app


def test_health_reports_ok_and_version():
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}
