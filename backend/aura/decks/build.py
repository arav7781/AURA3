"""Build every deck from its spec: the PDF that gets ingested (scanned when the spec says so), a PPTX with
the same slides, and the slide map evals use as ground truth.

    uv run python -m aura.decks.build seed/specs data/decks
"""

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from aura.decks.render_pdf import render_pdf
from aura.decks.render_pptx import render_pptx
from aura.decks.scan import scan_pdf
from aura.decks.slides import build_slides, slide_map
from aura.decks.spec import Scan, StartupSpec, load_specs


@dataclass(frozen=True)
class DeckFiles:
    pdf: bytes  # what the seeder uploads; image-only for scanned decks
    pptx: bytes
    slide_map: dict

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.pdf).hexdigest()


def build_deck(spec: StartupSpec) -> DeckFiles:
    slides = build_slides(spec)
    pdf = render_pdf(spec, slides)
    if spec.deck.render == "scanned":
        pdf = scan_pdf(pdf, spec.deck.scan or Scan())
    return DeckFiles(pdf=pdf, pptx=render_pptx(spec, slides),
                     slide_map=slide_map(spec, slides) | {"scanned": spec.deck.render == "scanned"})


def deck_filename(spec: StartupSpec, suffix: str) -> str:
    return f"{spec.name.replace(' ', '_')}_Pitch_Deck{suffix}"


def main(specs: str, out: str) -> int:
    target = Path(out)
    target.mkdir(parents=True, exist_ok=True)
    for spec in load_specs(Path(specs)):
        files = build_deck(spec)
        (target / deck_filename(spec, ".pdf")).write_bytes(files.pdf)
        (target / deck_filename(spec, ".pptx")).write_bytes(files.pptx)
        (target / f"{spec.slug}.slides.json").write_text(json.dumps(files.slide_map, indent=1))
        print(f"{spec.slug:24} {len(files.pdf) // 1024:5d} KB  sha256 {files.sha256[:16]}"
              + ("  (scanned)" if spec.deck.render == "scanned" else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:3] if len(sys.argv) > 2 else ("seed/specs", "data/decks"))))
