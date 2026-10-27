from pathlib import Path

from fastapi.testclient import TestClient

from transcrever_app.server.app import create_app
from transcrever_app.server.config import AppSettings


def test_compiled_frontend_is_served_for_spa_routes(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path / "data",
        runs_dir=tmp_path / "runs",
        worker_enabled=False,
    )

    with TestClient(create_app(settings)) as client:
        root = client.get("/")
        nested = client.get("/transcriptions/example")
        missing_api = client.get("/api/v1/does-not-exist")

    success_status = 200
    not_found_status = 404
    assert root.status_code == success_status
    assert '<div id="root"></div>' in root.text
    assert nested.status_code == success_status
    assert missing_api.status_code == not_found_status
