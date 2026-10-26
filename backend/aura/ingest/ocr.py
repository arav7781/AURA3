"""TitanOCR as an in-process service.

``titanocr.Engine`` runs OCR in a helper process with its own worker pool. It is started once (in the
background at app startup, ~10 s), reused for every document, and its blocking ``ocr`` call runs in a
thread. ``ocr_max_docs`` documents are processed at a time; each worker needs ~1–1.5 GB of RAM.
"""

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aura.core.config import get_settings

logger = logging.getLogger("aura.ocr")


class OcrError(RuntimeError):
    def __init__(self, message: str, *, status: str = "failed") -> None:
        super().__init__(message)
        self.status = status


@dataclass
class OcrOutcome:
    ir: dict[str, Any]
    status: str  # done | partial
    pages: list[dict[str, Any]]
    review_required: bool
    degraded: bool
    markdown: str
    spatial_markdown: str
    versions: dict[str, str]
    ms: int


class OcrService:
    def __init__(self) -> None:
        self._engine: Any = None
        self._lock = threading.Lock()
        self._semaphore: asyncio.Semaphore | None = None
        self.status = "stopped"
        self.info: dict[str, Any] = {}

    def _start_blocking(self) -> Any:
        with self._lock:
            if self._engine is not None and self._engine.running:
                return self._engine
            from titanocr import Engine

            settings = get_settings()
            self.status = "starting"
            started = time.monotonic()
            engine = Engine(
                workers=settings.ocr_workers,
                download=False,
                models_dir=settings.ocr_models_dir,
                timeout=600.0,
            )
            try:
                engine.start()
            except Exception as exc:
                self.status = "failed"
                raise OcrError(f"TitanOCR could not start: {exc}") from exc
            self._engine = engine
            self.info = dict(engine.info)
            self.status = "ready"
            logger.info("TitanOCR ready in %.1fs (%s)", time.monotonic() - started, self.info)
            return engine

    async def start(self) -> None:
        await asyncio.to_thread(self._start_blocking)

    def versions(self) -> dict[str, str]:
        import titanocr

        return {
            "titanocr": titanocr.__version__,
            "pipeline": str(self.info.get("pipeline", "default")),
            "engine": str(self.info.get("version", "")),
        }

    async def ocr(self, path: Path, *, filename: str) -> OcrOutcome:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(get_settings().ocr_max_docs)
        async with self._semaphore:
            engine = await asyncio.to_thread(self._start_blocking)
            started = time.monotonic()
            try:
                result = await asyncio.to_thread(engine.ocr, path, filename=filename)
            except Exception as exc:  # DocumentError carries .status (refused/rejected/failed/timeout)
                status = getattr(exc, "status", "failed")
                raise OcrError(str(exc) or f"TitanOCR {status}", status=status) from exc
            ms = int((time.monotonic() - started) * 1000)
        ir = result.ir.model_dump(mode="json")
        versions = self.versions() | {"ir": str(ir.get("ir_version", ""))}
        return OcrOutcome(
            ir=ir,
            status=result.status,
            pages=[dict(p) for p in result.pages],
            review_required=result.review_required,
            degraded=result.degraded,
            markdown=result.markdown,
            spatial_markdown=result.spatial_markdown,
            versions=versions,
            ms=ms,
        )

    def close(self) -> None:
        with self._lock:
            if self._engine is not None:
                try:
                    self._engine.close()
                finally:
                    self._engine = None
                    self.status = "stopped"


ocr_service = OcrService()
