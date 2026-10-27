from pathlib import Path

from fastapi.testclient import TestClient

from transcrever_app.server.app import create_app
from transcrever_app.server.config import AppSettings


def _client_settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        data_dir=tmp_path / "data",
        runs_dir=tmp_path / "runs",
        worker_enabled=False,
    )


def test_folder_hierarchy_breadcrumbs_and_transcription_move(tmp_path: Path) -> None:
    app = create_app(_client_settings(tmp_path))
    with TestClient(app) as client:
        root = client.post("/api/v1/folders", json={"name": "Cliente A"})
        root_id = root.json()["id"]
        child = client.post(
            "/api/v1/folders",
            json={"name": "Reuniões", "parent_id": root_id},
        )
        child_id = child.json()["id"]
        upload = client.post(
            "/api/v1/transcriptions",
            files={"file": ("meeting.wav", b"media", "audio/wav")},
            data={"title": "Reunião", "diarization_mode": "off"},
        )
        item_id = upload.json()["id"]
        moved = client.patch(
            f"/api/v1/transcriptions/{item_id}",
            json={"folder_id": child_id},
        )
        library = client.get("/api/v1/library", params={"folder_id": child_id})

    created_status = 201
    success_status = 200
    assert root.status_code == created_status
    assert child.status_code == created_status
    assert moved.status_code == success_status
    payload = library.json()
    assert [entry["name"] for entry in payload["breadcrumbs"]] == ["Cliente A", "Reuniões"]
    assert payload["transcriptions"][0]["id"] == item_id


def test_duplicate_sibling_and_descendant_cycle_are_rejected(tmp_path: Path) -> None:
    app = create_app(_client_settings(tmp_path))
    with TestClient(app) as client:
        parent = client.post("/api/v1/folders", json={"name": "Projetos"}).json()
        duplicate = client.post("/api/v1/folders", json={"name": "  PROJETOS  "})
        child = client.post(
            "/api/v1/folders",
            json={"name": "2026", "parent_id": parent["id"]},
        ).json()
        cycle = client.post(
            f"/api/v1/folders/{parent['id']}/move",
            json={"parent_id": child["id"]},
        )

    conflict_status = 409
    assert duplicate.status_code == conflict_status
    assert cycle.status_code == conflict_status


def test_folder_tree_returns_unambiguous_paths(tmp_path: Path) -> None:
    app = create_app(_client_settings(tmp_path))
    with TestClient(app) as client:
        parent = client.post("/api/v1/folders", json={"name": "Clientes"}).json()
        child = client.post(
            "/api/v1/folders",
            json={"name": "Acme", "parent_id": parent["id"]},
        ).json()
        response = client.get("/api/v1/folders/tree")

    success_status = 200
    assert response.status_code == success_status
    paths = {item["id"]: item["path"] for item in response.json()}
    assert paths[parent["id"]] == "Clientes"
    assert paths[child["id"]] == "Clientes / Acme"


def test_sibling_positions_are_created_and_reordered_deterministically(tmp_path: Path) -> None:
    app = create_app(_client_settings(tmp_path))
    with TestClient(app) as client:
        first = client.post("/api/v1/folders", json={"name": "First"}).json()
        second = client.post("/api/v1/folders", json={"name": "Second"}).json()
        client.patch(f"/api/v1/folders/{first['id']}", json={"position": 1})
        client.patch(f"/api/v1/folders/{second['id']}", json={"position": 0})
        library = client.get("/api/v1/library").json()

    assert first["position"] == 0
    assert second["position"] == 1
    assert [folder["name"] for folder in library["folders"]] == ["Second", "First"]


def test_deleting_folder_hides_its_subtree(tmp_path: Path) -> None:
    app = create_app(_client_settings(tmp_path))
    with TestClient(app) as client:
        parent = client.post("/api/v1/folders", json={"name": "Projetos"}).json()
        child = client.post(
            "/api/v1/folders",
            json={"name": "2026", "parent_id": parent["id"]},
        ).json()
        deleted = client.delete(f"/api/v1/folders/{parent['id']}")
        root_library = client.get("/api/v1/library")
        hidden_child = client.get(f"/api/v1/folders/{child['id']}")

    no_content_status = 204
    not_found_status = 404
    assert deleted.status_code == no_content_status
    assert root_library.json()["folders"] == []
    assert hidden_child.status_code == not_found_status


def test_deleting_folder_moves_contained_transcription_to_trash(tmp_path: Path) -> None:
    app = create_app(_client_settings(tmp_path))
    with TestClient(app) as client:
        folder = client.post("/api/v1/folders", json={"name": "Archive"}).json()
        upload = client.post(
            "/api/v1/transcriptions",
            files={"file": ("meeting.wav", b"content", "audio/wav")},
            data={"title": "Meeting", "diarization_mode": "off"},
        ).json()
        client.patch(
            f"/api/v1/transcriptions/{upload['id']}",
            json={"folder_id": folder["id"]},
        )
        client.post(f"/api/v1/transcriptions/{upload['id']}/cancel")

        deleted = client.delete(f"/api/v1/folders/{folder['id']}")
        hidden = client.get(f"/api/v1/transcriptions/{upload['id']}")
        restored = client.post(f"/api/v1/transcriptions/{upload['id']}/restore")

    no_content_status = 204
    not_found_status = 404
    success_status = 200
    assert deleted.status_code == no_content_status
    assert hidden.status_code == not_found_status
    assert restored.status_code == success_status
