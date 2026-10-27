"""Safe operating-system folder opening."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def open_transcription_folder(*, job_root: Path, outputs_path: Path) -> None:
    """Open a controlled output location without accepting arbitrary user paths."""
    root = job_root.resolve()
    outputs = outputs_path.resolve()
    if root not in outputs.parents:
        raise ValueError("Diretório de saída fora do job controlado.")
    target_file = outputs / "transcript.txt"
    if sys.platform == "win32":
        command = (
            ["explorer.exe", "/select,", str(target_file)]
            if target_file.exists()
            else [
                "explorer.exe",
                str(outputs),
            ]
        )
    elif sys.platform == "darwin":
        command = ["open", "-R", str(target_file if target_file.exists() else outputs)]
    else:
        command = ["xdg-open", str(outputs)]
    subprocess.Popen(command, shell=False)
