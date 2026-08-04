"""
PDF text extraction, via the `pdftotext` binary (poppler-utils). Knows
nothing about resumes or the RSM -- just PDF-in, text-out.

Scanned/image-only PDFs (no text layer) are explicitly out of scope: they
fail loudly here rather than silently producing near-empty output for the
structuring step to hallucinate around. OCR/multimodal fallback is a
documented follow-up, not implemented.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_MIN_TEXT_LENGTH = 50


class PdfExtractionError(RuntimeError):
    pass


def extract_text(pdf_path: Path) -> str:
    if shutil.which("pdftotext") is None:
        raise PdfExtractionError(
            "The `pdftotext` binary is required (part of poppler-utils) but was not found on PATH."
        )

    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PdfExtractionError(f"pdftotext failed on {pdf_path}: {result.stderr.strip()}")

    text = result.stdout
    if len(text.strip()) < _MIN_TEXT_LENGTH:
        raise PdfExtractionError(
            f"{pdf_path} has little or no extractable text (found {len(text.strip())} chars) -- "
            "likely a scanned/image PDF with no text layer. OCR is not supported yet."
        )
    return text
