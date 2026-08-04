"""
Render a ResumeSections projection to PDF bytes by converting the same
HTML `rac.render.html.render_html` produces with WeasyPrint, so HTML and
PDF output share one template/CSS.

`weasyprint` is an optional dependency (`pip install -e ".[pdf]"`) since it
requires system libraries (Pango/Cairo/GDK-Pixbuf) beyond a plain pip
install. It is imported lazily here so importing `rac.render` -- or using
markdown/HTML rendering, or any other rac command -- never requires it.
"""

from __future__ import annotations

from rac.render.html import render_html
from rac.render.sections import ResumeSections


def render_pdf(sections: ResumeSections) -> bytes:
    import weasyprint

    html = render_html(sections)
    return weasyprint.HTML(string=html).write_pdf()
