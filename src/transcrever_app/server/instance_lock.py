"""Single-instance lock scoped to one application data directory."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from uuid import uuid4


class InstanceAlreadyRunningError(RuntimeError):
    """Raised when another process owns the data directory."""


class InstanceLock:
    """Atomic PID lock with stale-owner recovery and ownership-safe release."""

    def __init__(self, data_dir: Path) -> None:
        """Prepare a lock inside the controlled data directory."""
        self.path = data_dir / "instance.lock"
        self._token = uuid4().hex
        self._held = False

    def acquire(self) -> None:
        """Acquire the lock or fail when its live owner is another process."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _attempt in range(2):
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if not self._remove_if_stale():
                    raise InstanceAlreadyRunningError(
                        "Outra instância do Transcrever já está usando esta pasta de dados."
                    ) from None
                continue
            with os.fdopen(descriptor, "w", encoding="utf-8") as lock_file:
                json.dump({"pid": os.getpid(), "token": self._token}, lock_file)
                lock_file.flush()
                os.fsync(lock_file.fileno())
            self._held = True
            return
        raise InstanceAlreadyRunningError("Não foi possível adquirir o lock da aplicação.")

    def release(self) -> None:
        """Remove only a lock still owned by this object."""
        if not self._held:
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("token") == self._token:
                self.path.unlink(missing_ok=True)
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        finally:
            self._held = False

    def _remove_if_stale(self) -> bool:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            pid = int(payload["pid"])
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            self.path.unlink(missing_ok=True)
            return True
        if _process_exists(pid):
            return False
        self.path.unlink(missing_ok=True)
        return True


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _windows_process_exists(pid)
    return _posix_process_exists(pid)  # type: ignore[unreachable]


def _posix_process_exists(pid: int) -> bool:
    """Probe a POSIX PID with signal zero."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _windows_process_exists(pid: int) -> bool:
    """Query a Windows PID without sending it a signal."""
    import ctypes

    process_query_limited_information = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenProcess(process_query_limited_information, 0, pid)
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True
