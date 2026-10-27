from __future__ import annotations

import sys
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from transcrever_app.server.config import AppSettings
from transcrever_app.server.desktop import _open_window, run_desktop_app


class FakeServer:
    """Controllable server double for lifecycle tests."""

    def __init__(self) -> None:
        """Initialize observable lifecycle flags."""
        self.should_exit = False
        self.force_exit = False
        self.started = Event()
        self.stopped = Event()

    def run(self) -> None:
        """Wait until the desktop lifecycle requests shutdown."""
        self.started.set()
        while not self.should_exit and not self.force_exit:
            self.stopped.wait(0.01)
        self.stopped.set()


def test_closing_desktop_window_stops_owned_server(tmp_path: Path) -> None:
    server = FakeServer()
    opened_urls: list[str] = []
    settings = AppSettings(data_dir=tmp_path / "data", runs_dir=tmp_path / "runs", port=8871)

    run_desktop_app(
        object(),
        settings,
        lambda _url: server.started.is_set(),
        server_factory=lambda _application, _settings: server,
        window_runner=opened_urls.append,
    )

    assert opened_urls == ["http://127.0.0.1:8871"]
    assert server.should_exit is True
    assert server.stopped.is_set()


def test_window_failure_still_stops_owned_server(tmp_path: Path) -> None:
    server = FakeServer()
    settings = AppSettings(data_dir=tmp_path / "data", runs_dir=tmp_path / "runs", port=8872)

    def fail_window(_url: str) -> None:
        raise RuntimeError("window failed")

    with pytest.raises(RuntimeError, match="window failed"):
        run_desktop_app(
            object(),
            settings,
            lambda _url: server.started.is_set(),
            server_factory=lambda _application, _settings: server,
            window_runner=fail_window,
        )

    assert server.should_exit is True
    assert server.stopped.is_set()


def test_desktop_disables_private_webview_profile_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, object]] = []
    fake_webview = SimpleNamespace(
        create_window=lambda title, url, **options: calls.append(("create", (title, url, options))),
        start=lambda **options: calls.append(("start", options)),
    )
    monkeypatch.setitem(sys.modules, "webview", fake_webview)

    _open_window("http://127.0.0.1:8766")

    assert calls[-1] == ("start", {"private_mode": False})
