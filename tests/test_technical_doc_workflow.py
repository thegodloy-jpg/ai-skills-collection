"""Word converter regressions; optional document dependencies are not installer requirements.

By default exercise the bundled skill. TECHNICAL_DOC_WORKFLOW_SKILL_DIR can point
to a local skill directory while preparing a release. All test artifacts are temporary.
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

try:
    from docx import Document
    from docx.enum.style import WD_STYLE_TYPE
    from docx.oxml.ns import qn
    from docx.shared import Pt
    import markdown_it  # noqa: F401 -- optional CLI dependency probe
    from PIL import Image
    DOCUMENT_DEPENDENCIES = True
except ImportError:
    DOCUMENT_DEPENDENCIES = False


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = Path(os.environ.get(
    "TECHNICAL_DOC_WORKFLOW_SKILL_DIR", REPO_ROOT / "skills" / "technical-doc-workflow"
))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@unittest.skipUnless(DOCUMENT_DEPENDENCIES, "Optional python-docx, markdown-it-py, and Pillow dependencies required")
class WordConversionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="technical-doc-test-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.script = SKILL_ROOT / "scripts" / "build_word.py"
        self.assertTrue(self.script.is_file(), f"Missing bundled converter: {self.script}")
        Image.new("RGB", (160, 60), "navy").save(self.directory / "image.png")
        self.counter = 0

    def run_cli(self, source, output, *options, expected=0):
        original_hash = digest(source)
        environment = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(
            [sys.executable, "-B", str(self.script), str(source), "--output", str(output),
             *map(str, options)], capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=environment,
        )
        self.assertEqual(digest(source), original_hash, "Conversion changed the source Markdown")
        self.assertEqual(result.returncode, expected, result.stderr or result.stdout)
        return result

    def build(self, text, *options):
        self.counter += 1
        source = self.directory / f"sample-{self.counter}.md"
        output = source.with_suffix(".docx")
        source.write_text(text, encoding="utf-8")
        self.run_cli(source, output, *options)
        report = json.loads(output.with_suffix(".validation.json").read_text(encoding="utf-8"))
        self.assertEqual(report["source_sha256"], digest(source))
        self.assertEqual(report["body_fidelity"], "passed")
        self.assertEqual(report["visual_validation"], "not_run")
        return Document(output), report

    def assert_code_fonts(self, document, latin, east_asia):
        inline = next(run for paragraph in document.paragraphs for run in paragraph.runs
                      if run.text == "inline()")
        code_runs = [run for table in document.tables for row in table.rows
                     for cell in row.cells for paragraph in cell.paragraphs
                     if paragraph.style.name == "MD Code" for run in paragraph.runs]
        self.assertTrue(code_runs)
        for run in [inline, *code_runs]:
            fonts = run._r.find("./" + qn("w:rPr") + "/" + qn("w:rFonts"))
            self.assertEqual(fonts.get(qn("w:ascii")), latin)
            self.assertEqual(fonts.get(qn("w:hAnsi")), latin)
            self.assertEqual(fonts.get(qn("w:eastAsia")), east_asia)
            self.assertNotIn(qn("w:asciiTheme"), fonts.attrib)
            self.assertNotIn(qn("w:eastAsiaTheme"), fonts.attrib)

    def test_default_and_explicit_code_fonts(self):
        text = '`inline()`\n\n```python\ndef value():\n    return "中文"\n```\n'
        document, _ = self.build(text)
        self.assert_code_fonts(document, "Consolas", "宋体")
        self.assertEqual(document.styles["MD Code"].font.size.pt, 9.5)
        style = self.directory / "style.json"
        style.write_text(json.dumps({"MD Code": {"font": "Courier New", "east_asia": "仿宋"}}), encoding="utf-8")
        document, _ = self.build(text, "--style-json", style)
        self.assert_code_fonts(document, "Courier New", "仿宋")

    def test_template_code_fonts_and_explicit_override(self):
        text = '`inline()`\n\n```python\n    return 1\n```\n'
        for style_name in ("MD Code", "Wings Code"):
            with self.subTest(style=style_name):
                template = Document()
                style = template.styles.add_style(style_name, WD_STYLE_TYPE.PARAGRAPH)
                style.font.name, style.font.size = "Lucida Console", Pt(10)
                style.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "黑体")
                template_path = self.directory / f"{style_name}.docx"
                template.save(template_path)
                template_hash = digest(template_path)
                document, _ = self.build(text, "--template", template_path)
                self.assert_code_fonts(document, "Lucida Console", "黑体")
                self.assertEqual(digest(template_path), template_hash)
                overrides = self.directory / "override.json"
                overrides.write_text(json.dumps({"MD Code": {"font": "Courier New", "east_asia": "仿宋"}}), encoding="utf-8")
                document, _ = self.build(text, "--template", template_path, "--style-json", overrides)
                self.assert_code_fonts(document, "Courier New", "仿宋")
                self.assertEqual(digest(template_path), template_hash)

    def test_image_caption_priority_and_alt_metadata(self):
        cases = [
            ("alt only", "Architecture", "", ["Architecture"]),
            ("same alt", "图1 架构", "图1 架构", ["图1 架构"]),
            ("numbered Chinese", "Architecture", "**图2：显式说明**", ["图2：显式说明"]),
            ("numbered English", "Architecture", "Figure 3: Explicit caption", ["Figure 3: Explicit caption"]),
            ("English with Chinese", "Architecture", "Figure 4中文说明", ["Figure 4中文说明"]),
            ("empty alt explicit", "", "图5 显式说明", ["图5 显式说明"]),
            ("no caption", "", "", []),
        ]
        for label, alt, explicit, expected in cases:
            with self.subTest(case=label):
                text = f"![{alt}](image.png)\n\n"
                if explicit:
                    text += explicit + "\n\n"
                text += "Ordinary text remains.\n"
                document, report = self.build(text)
                captions = [p for p in document.paragraphs if p.style.name == "Caption"]
                self.assertEqual([p.text for p in captions], expected)
                self.assertEqual(document.paragraphs[-1].text, "Ordinary text remains.")
                self.assertEqual(document.paragraphs[-1].style.name, "Normal")
                self.assertEqual(document.inline_shapes[0]._inline.docPr.get("descr"), alt)
                self.assertEqual(report["images"][0]["alt"], alt)
                self.assertEqual(report["counts"]["figures"], 1)
                self.assertEqual(len(document.paragraphs), 2 + len(expected))
                if explicit:
                    self.assertEqual(sum(p.text == expected[0] for p in document.paragraphs), 1)
                if label == "numbered Chinese":
                    self.assertTrue(next(r for r in captions[0].runs if r.text).bold)

    def test_caption_lookup_stops_at_next_block(self):
        document, _ = self.build("![Architecture](image.png)\n\n## Boundary\n\n图1 Later text\n")
        self.assertEqual([p.text for p in document.paragraphs if p.style.name == "Caption"], ["Architecture"])
        self.assertEqual(document.paragraphs[-1].text, "图1 Later text")
        self.assertEqual(document.paragraphs[-1].style.name, "Normal")

    def test_integrated_content_code_lines_and_landscape(self):
        code = ['def build(request):', '    config = {"workers": 2}', '', '\treturn config  # 中文注释']
        text = (
            '# Conversion sample\n\n## Content\n\n'
            '**Bold**, *emphasis*, `inline()`, [web](https://example.com/guide) '
            'and [section](#implementation).\n\n'
            '- First item\n- Second item\n  1. Nested item\n\n> Quote.\n\n'
            '![图1 测试图片](image.png)\n\n'
            '| Name | Description |\n| --- | --- |\n| config | First<br />Second |\n\n'
            '## Implementation\n\n**Code**\n\n```python\n' + '\n'.join(code) + '\n```\n\n'
            '## Plan\n\n| Step | Result |\n| --- | --- |\n| Verify | Complete |\n'
        )
        document, report = self.build(text, "--landscape-heading", "Plan")
        self.assertEqual(report["counts"], {"code_blocks": 1, "code_lines": 4, "tables": 2, "figures": 1})
        self.assertEqual([cell.text for row in document.tables[1].rows for cell in row.cells], code)
        self.assertEqual(document.tables[0].cell(1, 1).text, "First\nSecond")
        self.assertEqual([s["orientation"] for s in report["sections"]], ["portrait", "landscape"])
        self.assertEqual(document.paragraphs[0].style.name, "Title")
        self.assertEqual(document.paragraphs[1].style.name, "Heading 1")
        self.assertEqual(len(report["external_relationships"]), 1)
        self.assertEqual(report["external_relationships"][0]["target"], "https://example.com/guide")
        self.assert_code_fonts(document, "Consolas", "宋体")

    def test_unsupported_content_and_failed_overwrite_preserve_output(self):
        source, output = self.directory / "guard.md", self.directory / "guard.docx"
        source.write_text("# Preserve output\n", encoding="utf-8")
        self.run_cli(source, output)
        output_hash = digest(output)
        self.run_cli(source, output, expected=2)
        self.assertEqual(digest(output), output_hash)
        for text in ("<!-- review comment -->", "<div>HTML</div>",
                     "```mermaid\ngraph TD; A-->B\n```", "![SVG](diagram.svg)",
                     "![Missing](missing.png)", "[Local](other.docx)"):
            with self.subTest(content=text):
                source.write_text(text, encoding="utf-8")
                self.run_cli(source, output, "--overwrite", expected=2)
                self.assertEqual(digest(output), output_hash)


if __name__ == "__main__":
    unittest.main()
