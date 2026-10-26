"""Prompt-injection scanning for uploaded documents.

Deck text is data, never instructions: agents always receive it wrapped as untrusted content. This scanner
adds a visible signal on top: it looks for hidden text (microscopic characters, or text the same colour as
the fill behind it),
instruction-like phrasing aimed at an AI, and the same in PPTX speaker notes. Hits flag the chunk
(``injection_suspected``) and the document (``DECK_HIDDEN_INSTRUCTIONS``) so reviewers and the UI see it.
"""

import re
from dataclasses import dataclass
from pathlib import Path

PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above|earlier|preceding) (instructions|prompts|directions|rules)",
    r"disregard (all |any |the )?(previous|prior|above|earlier) ",
    r"(note|message|instruction|instructions) (to|for) (the |any )?(ai|llm|model|evaluator|assistant|reviewer bot)",
    r"(you are|act as|pretend to be) (an? |the )?(ai|assistant|language model|evaluator|grader|analyst bot)",
    r"(rate|score|grade|rank) (this|the|our) (startup|company|deck|pitch|team)( as| at)? (10|ten|9\.?\d?)( ?/ ?10| out of (10|ten))?",
    r"(must|should) (receive|get|be given) (a )?(score|rating) of",
    r"system prompt|developer message|<\|im_start\|>|\[/?inst\]|### ?instruction",
    r"do not (mention|reveal|disclose|flag) (this|these|the following)",
    r"respond only with|output only",
]
_PATTERN = re.compile("|".join(f"(?:{p})" for p in PATTERNS), re.IGNORECASE)


@dataclass(frozen=True)
class Finding:
    page: int | None
    source: str  # hidden_text | text | notes
    excerpt: str


def looks_like_instruction(text: str) -> bool:
    return bool(_PATTERN.search(text))


def scan_text(text: str, page: int | None = None, source: str = "text") -> list[Finding]:
    found = []
    for match in _PATTERN.finditer(text):
        start = max(0, match.start() - 60)
        found.append(Finding(page, source, text[start : match.end() + 80].strip()))
    return found


MIN_CONTRAST = 0.12  # luminance difference below which text is unreadable against its background


def _luminance(color: object) -> float | None:
    """Relative luminance (0 black … 1 white) of a pdfplumber gray, RGB or CMYK colour."""
    if color is None:
        return None
    values = color if isinstance(color, list | tuple) else [color]
    try:
        numbers = [float(v) for v in values]
    except (TypeError, ValueError):  # pattern fills and the like
        return None
    if len(numbers) == 4:
        c, m, y, k = numbers
        numbers = [(1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k)]
    if len(numbers) == 3:
        r, g, b = numbers
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    return numbers[0] if len(numbers) == 1 else None


def _inside(x: float, y: float, box: dict) -> bool:
    return box["x0"] <= x <= box["x1"] and box["top"] <= y <= box["bottom"]


def _is_hidden(char: dict, fills: list[dict], images: list[dict]) -> bool:
    """Microscopic, or too close in colour to everything that could be behind it. White text on a dark
    band is visible; white text on a white or near-white slide is not. Over an image we cannot tell, so
    the text counts as visible (the instruction-phrase scan still reads it)."""
    if float(char.get("size") or 12) < 2.0:
        return True
    text = _luminance(char.get("non_stroking_color"))
    if text is None:
        return False
    x, y = (char["x0"] + char["x1"]) / 2, (char["top"] + char["bottom"]) / 2
    if any(_inside(x, y, image) for image in images):
        return False
    backgrounds = [1.0]  # the page itself is white
    for fill in fills:
        if _inside(x, y, fill):
            luminance = _luminance(fill.get("non_stroking_color"))
            if luminance is None:
                return False
            backgrounds.append(luminance)
    return all(abs(text - background) < MIN_CONTRAST for background in backgrounds)


def hidden_pdf_text(pdf_path: Path) -> list[Finding]:
    """Text a human cannot see: microscopic, or the same colour as what is behind it."""
    import pdfplumber

    findings: list[Finding] = []
    with pdfplumber.open(pdf_path) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            fills = [shape for shape in [*page.rects, *page.curves] if shape.get("fill")]
            hidden = [ch["text"] for ch in page.chars if _is_hidden(ch, fills, page.images)]
            text = "".join(hidden).strip()
            if len(text) >= 12:
                findings.append(Finding(index, "hidden_text", text[:400]))
    return findings


def pptx_notes(pptx_path: Path) -> list[Finding]:
    from pptx import Presentation

    findings: list[Finding] = []
    deck = Presentation(str(pptx_path))
    for index, slide in enumerate(deck.slides, start=1):
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text if slide.notes_slide.notes_text_frame else ""
            findings += scan_text(notes, index, "notes")
    return findings


def scan_document(pdf_path: Path | None, *, original: Path | None = None) -> list[Finding]:
    findings: list[Finding] = []
    if pdf_path is not None and pdf_path.suffix.lower() == ".pdf":
        findings += hidden_pdf_text(pdf_path)
    if original is not None and original.suffix.lower() == ".pptx":
        findings += pptx_notes(original)
    return findings
