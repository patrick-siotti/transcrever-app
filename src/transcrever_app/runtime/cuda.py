"""CUDA runtime discovery for Windows."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

CUDA_DLL_DIRS_ENV = "TRANSCRIBER_CUDA_DLL_DIRS"

_REQUIRED_CUDA_DLLS = ("cublas64_12.dll", "cudnn64_9.dll")
_DLL_DIRECTORY_HANDLES: list[Any] = []


def prepare_cuda_dll_search_path() -> tuple[Path, ...]:
    """Add known CUDA DLL directories to the Windows loader search path."""
    if sys.platform != "win32":
        return ()

    added: list[Path] = []
    for candidate in _iter_cuda_dll_candidates():
        if not _has_required_cuda_dlls(candidate):
            continue
        _add_to_process_path(candidate)
        added.append(candidate)
    return tuple(added)


def _iter_cuda_dll_candidates() -> Iterable[Path]:
    seen: set[Path] = set()
    for candidate in (*_env_candidates(), *_torch_candidates(), *_common_python_candidates()):
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        yield resolved


def _env_candidates() -> Iterable[Path]:
    configured = os.environ.get(CUDA_DLL_DIRS_ENV, "")
    for raw_path in configured.split(os.pathsep):
        if raw_path:
            yield Path(raw_path)


def _torch_candidates() -> Iterable[Path]:
    try:
        import torch
    except ImportError:
        return

    yield Path(torch.__file__).resolve().parent / "lib"


def _common_python_candidates() -> Iterable[Path]:
    yield from Path("C:/").glob("Python*/Lib/site-packages/torch/lib")

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        python_root = Path(local_app_data) / "Programs" / "Python"
        yield from python_root.glob("Python*/Lib/site-packages/torch/lib")


def _has_required_cuda_dlls(path: Path) -> bool:
    return path.is_dir() and all((path / dll_name).is_file() for dll_name in _REQUIRED_CUDA_DLLS)


def _add_to_process_path(path: Path) -> None:
    path_text = str(path)
    current_path = os.environ.get("PATH", "")
    current_parts = current_path.split(os.pathsep) if current_path else []
    if path_text not in current_parts:
        os.environ["PATH"] = os.pathsep.join((path_text, *current_parts))

    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is not None:
        handle = add_dll_directory(path_text)
        _DLL_DIRECTORY_HANDLES.append(handle)
