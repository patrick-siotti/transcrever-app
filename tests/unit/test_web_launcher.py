import socket

from transcrever_app.cli.main import _find_available_port


def test_find_available_port_skips_occupied_preference() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        occupied_port = occupied.getsockname()[1]

        selected = _find_available_port("127.0.0.1", occupied_port)

    assert selected > occupied_port
    assert selected <= occupied_port + 19
