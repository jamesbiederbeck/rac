import subprocess
from pathlib import Path

import pytest

from rac.ingest.extract import PdfExtractionError, extract_text


def test_missing_pdftotext_binary_raises_clear_error(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(PdfExtractionError, match="pdftotext"):
        extract_text(Path("whatever.pdf"))


def test_short_text_output_raises_no_text_layer_error(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/pdftotext")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(args=[], returncode=0, stdout="  \n ", stderr=""),
    )
    with pytest.raises(PdfExtractionError, match="OCR"):
        extract_text(Path("scanned.pdf"))


def test_nonzero_exit_raises_clear_error(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/pdftotext")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom"),
    )
    with pytest.raises(PdfExtractionError, match="boom"):
        extract_text(Path("broken.pdf"))


def test_real_extraction_against_archive_pdf():
    archive = Path(__file__).parent.parent.parent / "resume_archive"
    pdf = archive / "Victor Biederbeck Engineering Resume.pdf"
    if not pdf.exists():
        pytest.skip("resume_archive/ not present in this checkout")

    text = extract_text(pdf)

    assert "Victor Biederbeck" in text
    assert len(text.strip()) > 500
