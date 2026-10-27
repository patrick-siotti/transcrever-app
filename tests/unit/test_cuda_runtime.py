import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from transcrever_app.runtime import cuda


def test_prepare_cuda_dll_search_path_uses_configured_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dll_dir = tmp_path / "torch" / "lib"
    dll_dir.mkdir(parents=True)
    for dll_name in ("cublas64_12.dll", "cudnn64_9.dll"):
        (dll_dir / dll_name).write_text("", encoding="utf-8")

    handles: list[str] = []

    def add_dll_directory(path: str) -> int:
        handles.append(path)
        return len(handles)

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(cuda, "_torch_candidates", lambda: ())
    monkeypatch.setattr(cuda, "_common_python_candidates", lambda: ())
    monkeypatch.setenv(cuda.CUDA_DLL_DIRS_ENV, str(dll_dir))
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(os, "add_dll_directory", add_dll_directory)

    result = cuda.prepare_cuda_dll_search_path()

    assert result == (dll_dir.resolve(),)
    assert str(dll_dir.resolve()) in os.environ["PATH"]
    assert handles == [str(dll_dir.resolve())]


def test_prepare_cuda_dll_search_path_ignores_incomplete_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dll_dir = tmp_path / "torch" / "lib"
    dll_dir.mkdir(parents=True)
    (dll_dir / "cublas64_12.dll").write_text("", encoding="utf-8")

    def add_dll_directory(path: str) -> SimpleNamespace:
        return SimpleNamespace(path=path)

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(cuda, "_torch_candidates", lambda: ())
    monkeypatch.setattr(cuda, "_common_python_candidates", lambda: ())
    monkeypatch.setenv(cuda.CUDA_DLL_DIRS_ENV, str(dll_dir))
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(os, "add_dll_directory", add_dll_directory)

    assert cuda.prepare_cuda_dll_search_path() == ()
    assert os.environ["PATH"] == ""
