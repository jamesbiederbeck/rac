import os
import shutil

import pytest

from rac.render.browser_pdf import ChromePdfError, html_to_pdf_via_chrome

requires_node = pytest.mark.skipif(shutil.which("node") is None, reason="requires Node.js")


def test_html_to_pdf_via_chrome_raises_when_node_missing(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda cmd: None)

    with pytest.raises(ChromePdfError, match="Node.js"):
        html_to_pdf_via_chrome("<html></html>")


@requires_node
def test_html_to_pdf_via_chrome_raises_for_missing_puppeteer(tmp_path):
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()

    with pytest.raises(ChromePdfError, match="npm install puppeteer"):
        html_to_pdf_via_chrome("<html></html>", node_modules=node_modules)


@requires_node
@pytest.mark.skipif(
    not os.environ.get("RAC_TEST_PUPPETEER_NODE_MODULES"),
    reason="set RAC_TEST_PUPPETEER_NODE_MODULES to a node_modules dir with puppeteer installed to run this "
    "(opt-in: pulls down a Chromium binary, too heavy to run by default)",
)
def test_html_to_pdf_via_chrome_renders_real_pdf():
    from pathlib import Path

    node_modules = Path(os.environ["RAC_TEST_PUPPETEER_NODE_MODULES"])

    pdf = html_to_pdf_via_chrome("<html><body><h1>Hello</h1></body></html>", node_modules=node_modules)

    assert pdf.startswith(b"%PDF")
