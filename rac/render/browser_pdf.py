"""
Render HTML to PDF bytes using headless Chrome (via the `puppeteer` npm
package), as an alternative to rac.render.pdf's WeasyPrint backend.

JSON Resume themes (rac.render.theme) are written and tested against a
browser, not WeasyPrint. Browser-only CSS -- floats or percentage-heights
spanning a page break, in particular -- is a well-known WeasyPrint weak
spot: it can render fine in the theme's own screen preview and still
misrender badly as PDF (see examples/print-overrides/ for CSS-injection
workarounds via `rac render --print-css`, which only chase symptoms).
Printing through the actual browser engine the theme targets sidesteps the
problem at its root instead. This is `rac render --pdf-engine chrome`.

Node.js plus a locally `npm install`-ed `puppeteer` package (which bundles
its own Chromium) must already be present -- neither is a Python dependency
of rac, the same optionality pattern as WeasyPrint for rac.render.pdf. The
runner script is invoked with `node -e`, not a script file, for the same
reason as rac.render.theme: bare-specifier `import()` then resolves
`puppeteer` relative to the working directory (`--node-modules`, default
cwd), matching where `npm install` put it, rather than to some
rac-internal script path.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

_RUNNER_SCRIPT = """
const { readFile, writeFile } = await import("node:fs/promises");
const { default: puppeteer } = await import("puppeteer");

const [htmlPath, pdfPath] = process.argv.slice(1);
const html = await readFile(htmlPath, "utf-8");

const browser = await puppeteer.launch({ headless: true });
try {
  const page = await browser.newPage();
  await page.setContent(html, { waitUntil: "networkidle0" });
  const pdf = await page.pdf({ format: "A4", printBackground: true });
  await writeFile(pdfPath, pdf);
} finally {
  await browser.close();
}
"""


class ChromePdfError(RuntimeError):
    pass


def html_to_pdf_via_chrome(html: str, node_modules: Path | None = None) -> bytes:
    """Render `html` to PDF bytes with headless Chrome instead of WeasyPrint.

    `node_modules` is the directory to resolve `puppeteer` from (default:
    node_modules in the current working directory).
    """
    node = shutil.which("node")
    if node is None:
        raise ChromePdfError("Rendering PDF via headless Chrome requires Node.js (`node` not found on PATH).")

    cwd = str(node_modules.parent) if node_modules is not None else None

    with tempfile.TemporaryDirectory() as tmp:
        html_path = Path(tmp) / "resume.html"
        pdf_path = Path(tmp) / "resume.pdf"
        html_path.write_text(html)

        result = subprocess.run(
            [node, "--input-type=module", "-e", _RUNNER_SCRIPT, str(html_path), str(pdf_path)],
            capture_output=True,
            text=True,
            cwd=cwd,
        )

        if result.returncode != 0:
            install_hint = "npm install puppeteer" + (f" (in {cwd})" if cwd else "")
            raise ChromePdfError(
                f"Chrome PDF rendering failed:\n{result.stderr.strip()}\n\nIs it installed? Try `{install_hint}`."
            )
        return pdf_path.read_bytes()
