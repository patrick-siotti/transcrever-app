"""Desktop window lifecycle for the local application."""

from __future__ import annotations

import time
from collections.abc import Callable
from threading import Thread
from typing import Any, Protocol, cast

from transcrever_app.server.config import AppSettings


class ServerController(Protocol):
    """Small subset of the Uvicorn server used by the desktop lifecycle."""

    should_exit: bool
    force_exit: bool

    def run(self) -> None:
        """Serve until shutdown is requested."""


ServerFactory = Callable[[object, AppSettings], ServerController]
WindowRunner = Callable[[str], None]
HealthProbe = Callable[[str], bool]


def run_desktop_app(
    application: object,
    settings: AppSettings,
    health_probe: HealthProbe,
    *,
    server_factory: ServerFactory | None = None,
    window_runner: WindowRunner | None = None,
) -> None:
    """Run the server while the dedicated desktop window remains open."""
    resolved_server_factory = server_factory or _build_server
    resolved_window_runner = window_runner or _open_window
    server = resolved_server_factory(application, settings)
    server_thread = Thread(target=server.run, name="transcrever-server")
    server_thread.start()
    url = f"http://{settings.host}:{settings.port}"

    try:
        _wait_until_ready(url, health_probe, server_thread)
        resolved_window_runner(url)
    finally:
        server.should_exit = True
        server_thread.join(timeout=15)
        if server_thread.is_alive():
            server.force_exit = True
            server_thread.join(timeout=5)
        if server_thread.is_alive():
            msg = "O servidor local não encerrou dentro do tempo esperado."
            raise RuntimeError(msg)


def _wait_until_ready(url: str, health_probe: HealthProbe, server_thread: Thread) -> None:
    for _attempt in range(150):
        if health_probe(url):
            return
        if not server_thread.is_alive():
            msg = "O servidor local encerrou antes de ficar pronto."
            raise RuntimeError(msg)
        time.sleep(0.1)
    msg = "O servidor local não ficou pronto em 15 segundos."
    raise RuntimeError(msg)


def _build_server(application: object, settings: AppSettings) -> ServerController:
    import uvicorn

    config = uvicorn.Config(
        cast("Any", application),
        host=settings.host,
        port=settings.port,
        log_level="info",
        workers=1,
    )
    return uvicorn.Server(config)


def _open_window(url: str) -> None:
    import webview

    webview.create_window(
        "Transcrever",
        url,
        width=1280,
        height=820,
        min_size=(900, 640),
        text_select=True,
    )
    # O modo privado do WebView2 tenta apagar o perfil temporario durante o
    # fechamento e pode manter threads CLR vivas mesmo depois de a janela e o
    # Uvicorn encerrarem. O aplicativo ja e local e nao depende desse descarte.
    webview.start(private_mode=False)
