"""
Render a ResumeSections projection through an installed JSON Resume theme
package (https://jsonresume.org/themes) instead of rac's own HTML template.

A JSON Resume theme is an npm package named `jsonresume-theme-<name>` that
exports a pure `render(resume) -> htmlString` function, per
https://jsonresume.org/theme-development. This module hands it the
`rac.render.jsonresume.to_json_resume` projection of `sections` and returns
the HTML it produces.

Node.js plus the theme package (`npm install jsonresume-theme-<name>`) must
already be present -- neither is a Python dependency of rac, so this stays
out of rac.render's default import path the same way rac.render.pdf keeps
WeasyPrint optional. The theme's own `render` runs as a subprocess, not
in-process, since it's arbitrary JavaScript with its own module resolution.

`inject_css` is a separate, theme-agnostic escape hatch: JSON Resume themes
are written and tested against a browser, not WeasyPrint, so browser-only
CSS (floats spanning a page break is a known WeasyPrint weak spot) can
render fine in the theme's own screen preview but break badly once
converted to PDF -- see `rac render --print-css`. rac has no opinion on
what a given theme needs; the caller supplies the override.

The runner script is invoked with `node -e`, not as a script file, so that
both CommonJS `require()` and ESM `import()` resolve theme packages relative
to the *working directory* rather than the runner script's own location --
this is what lets `--node-modules` (or the default of wherever `rac` was
invoked) find a locally `npm install`-ed theme.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from rac.render.jsonresume import to_json_resume
from rac.render.sections import ResumeSections

_RUNNER_SCRIPT = """
const { createRequire } = await import("node:module");
const { readFile } = await import("node:fs/promises");

// Many themes log to stdout (debug prints left in at require-time or inside
// render()) as a matter of course -- nothing in the JSON Resume theme
// contract forbids it. Since stdout here is reserved for the rendered HTML
// (captured whole, not parsed for a delimiter), redirect console output to
// stderr for the lifetime of this script so a theme's own logging can't
// corrupt the document it's asked to produce.
for (const method of ["log", "info", "debug", "warn"]) {
  console[method] = (...args) => console.error(...args);
}

const [themeName, resumeJsonPath] = process.argv.slice(1);
const resume = JSON.parse(await readFile(resumeJsonPath, "utf-8"));
const require = createRequire(process.cwd() + "/");

async function loadTheme() {
  try {
    return require(themeName);
  } catch (requireError) {
    try {
      return await import(themeName);
    } catch {
      throw requireError;
    }
  }
}

const theme = await loadTheme();
const render = theme.render ?? theme.default?.render ?? theme.default;
if (typeof render !== "function") {
  throw new Error(`Theme "${themeName}" does not export a render(resume) function`);
}
process.stdout.write(await render(resume));
"""


class ThemeRenderError(RuntimeError):
    pass


def inject_css(html: str, css: str) -> str:
    """Insert `css` as a <style> block right before </head>, after whatever
    styles the theme already emitted -- later rules win on equal specificity,
    so this can override the theme's own layout without touching its source."""
    style_block = f"<style>{css}</style>"
    if "</head>" in html:
        return html.replace("</head>", f"{style_block}</head>", 1)
    return style_block + html


def render_jsonresume_theme(
    sections: ResumeSections,
    theme: str,
    node_modules: Path | None = None,
) -> str:
    """Render `sections` with an installed JSON Resume theme package.

    `theme` is the npm package name (e.g. "jsonresume-theme-elegant"),
    resolved via normal Node module resolution starting from `node_modules`'s
    parent directory (default: the current working directory, i.e. rac
    behaves like any other tool expecting `npm install` to have been run
    where it's invoked).
    """
    node = shutil.which("node")
    if node is None:
        raise ThemeRenderError("Rendering with a JSON Resume theme requires Node.js (`node` not found on PATH).")

    resume = to_json_resume(sections)
    cwd = str(node_modules.parent) if node_modules is not None else None

    with tempfile.TemporaryDirectory() as tmp:
        resume_path = Path(tmp) / "resume.json"
        resume_path.write_text(json.dumps(resume))

        result = subprocess.run(
            [node, "--input-type=module", "-e", _RUNNER_SCRIPT, theme, str(resume_path)],
            capture_output=True,
            text=True,
            cwd=cwd,
        )

    if result.returncode != 0:
        install_hint = f"npm install {theme}" + (f" (in {cwd})" if cwd else "")
        raise ThemeRenderError(
            f'Theme "{theme}" failed to render:\n{result.stderr.strip()}\n\nIs it installed? Try `{install_hint}`.'
        )
    return result.stdout
