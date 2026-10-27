"""Where copilot code runs keep their files: one folder per conversation under the data directory (Colima
shares only $HOME with its Docker VM, and the data directory lives there), one sub-folder per run."""

from pathlib import Path

from aura.core.config import get_settings

RUN_FILES = {".png", ".csv", ".json", ".txt", ".xlsx", ".pptx", ".pdf", ".md"}


def sandbox_dir(thread_id: str) -> Path:
    return (get_settings().data_dir / "sandbox" / thread_id).resolve()
