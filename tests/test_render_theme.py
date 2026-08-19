import shutil

import pytest

from rac.model import Person
from rac.render.sections import ResumeSections
from rac.render.theme import ThemeRenderError, inject_css, render_jsonresume_theme

requires_node = pytest.mark.skipif(shutil.which("node") is None, reason="requires Node.js")


def test_inject_css_inserts_before_closing_head():
    html = "<html><head><title>x</title></head><body></body></html>"

    result = inject_css(html, ".left-column { float: none; }")

    assert result == "<html><head><title>x</title><style>.left-column { float: none; }</style></head><body></body></html>"


def test_inject_css_prepends_when_no_head_tag():
    html = "<body>no head here</body>"

    result = inject_css(html, "body { margin: 0; }")

    assert result == "<style>body { margin: 0; }</style><body>no head here</body>"


@pytest.fixture
def fake_theme(tmp_path):
    package_dir = tmp_path / "node_modules" / "jsonresume-theme-fake"
    package_dir.mkdir(parents=True)
    (package_dir / "package.json").write_text('{"name": "jsonresume-theme-fake", "main": "index.js"}')
    (package_dir / "index.js").write_text(
        'function render(resume) { return "<h1>" + resume.basics.name + "</h1>"; }\n'
        "module.exports = { render: render };\n"
    )
    return tmp_path / "node_modules"


@requires_node
def test_render_jsonresume_theme_invokes_installed_theme(fake_theme):
    sections = ResumeSections(person=Person(id="p1", name="Jamie Rivera"))

    html = render_jsonresume_theme(sections, "jsonresume-theme-fake", node_modules=fake_theme)

    assert html == "<h1>Jamie Rivera</h1>"


@pytest.fixture
def noisy_theme(tmp_path):
    package_dir = tmp_path / "node_modules" / "jsonresume-theme-noisy"
    package_dir.mkdir(parents=True)
    (package_dir / "package.json").write_text('{"name": "jsonresume-theme-noisy", "main": "index.js"}')
    (package_dir / "index.js").write_text(
        'console.log("[Theme] loaded");\n'
        "function render(resume) {\n"
        '  console.log("rendering", resume.basics.name);\n'
        '  return "<h1>" + resume.basics.name + "</h1>";\n'
        "}\n"
        "module.exports = { render: render };\n"
    )
    return tmp_path / "node_modules"


@requires_node
def test_render_jsonresume_theme_ignores_themes_own_console_log(noisy_theme):
    """A theme that logs to stdout (at require-time or inside render()) is common and not
    against the JSON Resume theme contract -- rac must not let that corrupt the captured
    HTML, since stdout here is read whole rather than parsed for a delimiter."""
    sections = ResumeSections(person=Person(id="p1", name="Jamie Rivera"))

    html = render_jsonresume_theme(sections, "jsonresume-theme-noisy", node_modules=noisy_theme)

    assert html == "<h1>Jamie Rivera</h1>"


@requires_node
def test_render_jsonresume_theme_raises_for_missing_theme(fake_theme):
    sections = ResumeSections(person=Person(id="p1", name="Jamie Rivera"))

    with pytest.raises(ThemeRenderError, match="jsonresume-theme-does-not-exist"):
        render_jsonresume_theme(sections, "jsonresume-theme-does-not-exist", node_modules=fake_theme)
