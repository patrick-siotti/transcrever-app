import json
import os
from pathlib import Path

import pytest

from transcrever_app.server.instance_lock import InstanceAlreadyRunningError, InstanceLock


def test_instance_lock_rejects_second_live_owner(tmp_path: Path) -> None:
    first = InstanceLock(tmp_path)
    second = InstanceLock(tmp_path)
    first.acquire()

    with pytest.raises(InstanceAlreadyRunningError):
        second.acquire()

    first.release()
    assert not (tmp_path / "instance.lock").exists()


def test_instance_lock_recovers_stale_owner(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "instance.lock"
    lock_path.write_text(json.dumps({"pid": 2**30, "token": "stale"}), encoding="utf-8")
    lock = InstanceLock(tmp_path)

    lock.acquire()

    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert payload["pid"] == os.getpid()
    lock.release()
