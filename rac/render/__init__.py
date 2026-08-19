from rac.render.browser_pdf import ChromePdfError, html_to_pdf_via_chrome
from rac.render.html import render_html
from rac.render.jsonresume import to_json_resume
from rac.render.markdown import render_markdown
from rac.render.paginate import PageLimitError, fit_claims_to_page_limit, order_by_importance
from rac.render.pdf import html_to_pdf, render_pdf
from rac.render.sections import build_resume_sections
from rac.render.theme import ThemeRenderError, inject_css, render_jsonresume_theme
from rac.render.web import render_web

__all__ = [
    "build_resume_sections",
    "fit_claims_to_page_limit",
    "order_by_importance",
    "render_markdown",
    "render_html",
    "render_pdf",
    "render_web",
    "render_jsonresume_theme",
    "inject_css",
    "to_json_resume",
    "html_to_pdf",
    "html_to_pdf_via_chrome",
    "ThemeRenderError",
    "ChromePdfError",
    "PageLimitError",
]
