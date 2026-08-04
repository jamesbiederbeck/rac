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


def _minimal_pdf_bytes(lines: list[str]) -> bytes:
    """Build a small, valid single-page PDF with a correct xref table, so this test doesn't
    depend on any PDF-writing library (weasyprint is only installed with the optional "pdf"
    extra) or on a real resume PDF existing on disk."""
    content = "BT /F1 12 Tf 10 700 Td 14 TL\n" + "\n".join(f"({line}) Tj T*" for line in lines) + "\nET"
    content_bytes = content.encode("latin-1")

    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/Resources<</Font<</F1 4 0 R>>>>/MediaBox[0 0 612 792]/Contents 5 0 R>>",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
        b"<</Length " + str(len(content_bytes)).encode() + b">>\nstream\n" + content_bytes + b"\nendstream",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_offset = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<</Size {len(objects) + 1}/Root 1 0 R>>\nstartxref\n{xref_offset}\n%%EOF".encode()
    return bytes(out)


def test_real_extraction_against_generated_pdf(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(
        _minimal_pdf_bytes(
            [
                "Jamie Rivera",
                "Senior Site Reliability Engineer",
                "Reduced mean time to recovery by 45 percent.",
            ]
        )
    )

    text = extract_text(pdf_path)

    assert "Jamie Rivera" in text
    assert "Senior Site Reliability Engineer" in text
    assert len(text.strip()) > 50
