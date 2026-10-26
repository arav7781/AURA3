"""Office documents (PPTX/DOCX/ODP/ODT) to PDF with LibreOffice, inside the sandbox.

TitanOCR reads PDFs and images only, so uploaded decks in office formats are converted first. Hidden
slides are exported too, so PDF page numbers match slide numbers and citations stay correct. Office files
are zip archives: they are checked for zip bombs before anything opens them.
"""

import shutil
import zipfile
from pathlib import Path

from aura.sandbox.runner import RunSpec, runner

IMPRESS = {".pptx", ".ppt", ".odp", ".key"}
WRITER = {".docx", ".doc", ".odt", ".rtf"}
OFFICE_SUFFIXES = IMPRESS | WRITER

MAX_UNCOMPRESSED = 300 << 20
MAX_ENTRIES = 5000
MAX_RATIO = 200


class ConversionError(RuntimeError):
    pass


def check_zip_bomb(path: Path) -> None:
    if not zipfile.is_zipfile(path):
        return  # legacy .ppt/.doc are not zips
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        total = sum(info.file_size for info in entries)
        packed = max(1, sum(info.compress_size for info in entries))
    if len(entries) > MAX_ENTRIES or total > MAX_UNCOMPRESSED or total / packed > MAX_RATIO:
        raise ConversionError("The document expands to an unsafe size and was rejected")


async def convert_to_pdf(src: Path, *, workdir: Path, timeout_s: float = 180) -> Path:
    suffix = src.suffix.lower()
    if suffix not in OFFICE_SUFFIXES:
        raise ConversionError(f"Unsupported office format: {suffix}")
    check_zip_bomb(src)
    inbox = workdir / "in"
    inbox.mkdir(parents=True, exist_ok=True)
    # Fixed file name inside the container: user-supplied names never reach a command line.
    shutil.copyfile(src, inbox / f"input{suffix}")
    target = (
        'pdf:impress_pdf_Export:{"ExportHiddenSlides":{"type":"boolean","value":"true"}}'
        if suffix in IMPRESS
        else "pdf"
    )
    result = await runner.run(
        RunSpec(
            argv=[
                "soffice", "-env:UserInstallation=file:///tmp/lo-profile", "--headless", "--norestore",
                "--nolockcheck", "--convert-to", target, "--outdir", "/work/out", f"/work/in/input{suffix}",
            ],
            workspace=workdir,
            timeout_s=timeout_s,
            mem="1g",
            cpus=1.5,
            kind="office",
        )
    )
    pdf = workdir / "out" / "input.pdf"
    if result.status != "ok" or not pdf.exists() or pdf.stat().st_size == 0:
        detail = " | ".join((result.stderr or result.stdout)[-3:])
        raise ConversionError(f"Could not convert the document to PDF ({result.status}): {detail}"[:500])
    return pdf
