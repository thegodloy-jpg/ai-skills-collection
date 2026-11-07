#!/usr/bin/env python3
"""Convert an explicitly selected Markdown draft to Word without editing its source.

Requires: python-docx, markdown-it-py, Pillow.  SVG/diagram rendering is deliberately
outside this converter.  See --help for the optional style and image mapping files.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata
from urllib.parse import unquote, urlsplit

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION_START
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from lxml import etree
from markdown_it import MarkdownIt
from PIL import Image


DEFAULTS = {
    "Normal": dict(size_pt=12, first_line_pt=24, line_spacing=1.2, after_pt=0),
    "Title": dict(size_pt=18, bold=True, alignment="center", first_line_pt=0, before_pt=12, after_pt=12),
    "Heading 1": dict(size_pt=16, bold=True, first_line_pt=0, before_pt=12, after_pt=6),
    "Heading 2": dict(size_pt=15, bold=True, first_line_pt=0, before_pt=10, after_pt=5),
    "Heading 3": dict(size_pt=13, bold=True, first_line_pt=0, before_pt=8, after_pt=4),
    "Heading 4": dict(size_pt=12, bold=True, first_line_pt=0, before_pt=6, after_pt=3),
    "Heading 5": dict(size_pt=12, bold=True, first_line_pt=0, before_pt=6, after_pt=3),
    "Heading 6": dict(size_pt=12, bold=True, first_line_pt=0, before_pt=6, after_pt=3),
    "MD Code": dict(font="Consolas", east_asia="宋体", size_pt=9.5,
                    first_line_pt=0, line_height_pt=11.5, before_pt=0, after_pt=0),
    "MD Table": dict(size_pt=10.5, first_line_pt=0, line_spacing=1.2, before_pt=0, after_pt=3),
    "Caption": dict(size_pt=10.5, bold=True, alignment="center", first_line_pt=0, before_pt=0, after_pt=6),
}
STYLE_KEYS = {"font", "east_asia", "size_pt", "first_line_pt", "line_spacing",
              "line_height_pt", "before_pt", "after_pt", "bold", "alignment"}
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
DIAGRAMS = {"mermaid", "plantuml", "puml", "dot", "graphviz", "drawio"}
SUCCESSORS = {
    "tblBorders": "shd tblLayout tblCellMar tblLook tblCaption tblDescription tblPrChange",
    "tblCellMar": "tblLook tblCaption tblDescription tblPrChange",
    "cantSplit": "trHeight tblHeader tblCellSpacing jc hidden ins del trPrChange",
    "tblHeader": "tblCellSpacing jc hidden ins del trPrChange",
    "shd": "noWrap tcMar textDirection tcFitText vAlign hideMark headers tcPrChange",
    "updateFields": "hdrShapeDefaults footnotePr endnotePr compat docVars rsids m:mathPr attachedSchema themeFontLang clrSchemeMapping doNotIncludeSubdocsInStats doNotAutoCompressPictures forceUpgrade captions readModeInkLockDown smartTagType sl:schemaLibrary shapeDefaults doNotEmbedSmartTags decimalSymbol listSeparator",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def element(parent, tag, **attrs):
    child = parent.find(qn("w:" + tag))
    if child is None:
        factory = getattr(parent, "get_or_add_" + tag, None)
        if factory is not None:
            child = factory()
        else:
            child = OxmlElement("w:" + tag)
            successors = {qn(s if ":" in s else "w:" + s) for s in SUCCESSORS.get(tag, "").split()}
            position = next((i for i, e in enumerate(parent) if e.tag in successors), len(parent))
            parent.insert(position, child)
    for key, value in attrs.items():
        child.set(qn("w:" + key), str(value))
    return child


def xml_text(node):
    return "".join(e.text or "" if e.tag == qn("w:t") else
                   "\t" if e.tag == qn("w:tab") else "\n"
                   for e in node.iter() if e.tag in
                   {qn("w:t"), qn("w:tab"), qn("w:br"), qn("w:cr")})


def inline_text(tokens):
    return "".join(t.content if t.type in {"text", "code_inline"} else
                   " " if t.type == "softbreak" else "\n" if t.type in {"hardbreak", "html_inline"}
                   else "" for t in tokens)


def slug(text):
    return re.sub(r"[^\w\-\s]", "", text.lower()).replace(" ", "-")


def explicit_fonts(obj, latin, east_asia):
    rf = element(obj.get_or_add_rPr(), "rFonts", ascii=latin, hAnsi=latin,
                 eastAsia=east_asia, cs=latin)
    for key in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "csTheme", "cstheme"):
        rf.attrib.pop(qn("w:" + key), None)


def effective_font(style, attr, fallback, theme=None):
    while style is not None:
        rf = style.element.find("./" + qn("w:rPr") + "/" + qn("w:rFonts"))
        if rf is not None and rf.get(qn("w:" + attr)):
            return rf.get(qn("w:" + attr))
        if rf is not None and theme:
            themed = rf.get(qn("w:" + attr + "Theme"), "")
            if themed and theme.get((themed[:5], attr)):
                return theme[(themed[:5], attr)]
        style = style.base_style
    return fallback


def configure_styles(doc, template, overrides):
    if "Hyperlink" not in doc.styles:
        link_style = doc.styles.add_style("Hyperlink", WD_STYLE_TYPE.CHARACTER)
        link_style.font.underline = True
    theme = {}
    for rel in doc.part.rels.values():
        if rel.reltype == REL + "theme":
            root = etree.fromstring(rel.target_part.blob)
            for group in ("major", "minor"):
                fonts = root.find(".//" + qn("a:" + group + "Font"))
                if fonts is not None:
                    latin = fonts.find(qn("a:latin")).get("typeface")
                    east = fonts.find(qn("a:ea")).get("typeface")
                    hans = next((e.get("typeface") for e in fonts if e.get("script") == "Hans"), None)
                    theme[(group, "ascii")] = latin
                    theme[(group, "eastAsia")] = east or hans or "宋体"
    for name, default in DEFAULTS.items():
        existed = name in doc.styles
        style = doc.styles[name] if existed else doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        inherit_code = template and name == "MD Code" and not existed and "Wings Code" in doc.styles
        if inherit_code: style.base_style = doc.styles["Wings Code"]
        cfg = {} if template and (existed or inherit_code) else {"font": "宋体", "east_asia": "宋体", **default}
        cfg.update(overrides.get(name, {}))
        unknown = cfg.keys() - STYLE_KEYS
        if unknown:
            raise ValueError(f"Unknown style options for {name}: {sorted(unknown)}")
        latin = cfg.get("font", effective_font(style, "ascii", "宋体", theme))
        east = cfg.get("east_asia", effective_font(style, "eastAsia", "宋体", theme))
        explicit_fonts(style.element, latin, east)
        if "size_pt" in cfg:
            style.font.size = Pt(cfg["size_pt"])
        if "bold" in cfg: style.font.bold = cfg["bold"]
        pf = style.paragraph_format
        if "alignment" in cfg:
            choices = dict(left=WD_ALIGN_PARAGRAPH.LEFT, center=WD_ALIGN_PARAGRAPH.CENTER,
                           right=WD_ALIGN_PARAGRAPH.RIGHT, justify=WD_ALIGN_PARAGRAPH.JUSTIFY)
            if cfg["alignment"] not in choices: raise ValueError(f"Invalid alignment: {cfg['alignment']}")
            pf.alignment = choices[cfg["alignment"]]
        for key, prop in (("first_line_pt", "first_line_indent"),
                          ("before_pt", "space_before"), ("after_pt", "space_after")):
            if key in cfg:
                setattr(pf, prop, Pt(cfg[key]))
        if "line_spacing" in cfg:
            pf.line_spacing = cfg["line_spacing"]
        if "line_height_pt" in cfg:
            pf.line_spacing = Pt(cfg["line_height_pt"])
        if name.startswith("Heading") or name == "Title":
            pf.keep_with_next = True
    if overrides.keys() - DEFAULTS.keys():
        raise ValueError(f"Unknown styles: {sorted(overrides.keys() - DEFAULTS.keys())}")


def clean_template(doc):
    body = doc.element.body
    final = body.sectPr
    inherited = {}
    for section in doc.sections:
        for child in section._sectPr:
            if child.tag in {qn("w:headerReference"), qn("w:footerReference")}:
                inherited[(child.tag, child.get(qn("w:type")))] = deepcopy(child)
    for child in list(body):
        if child is not final:
            body.remove(child)
    if final is not None:
        for child in list(final):
            if child.tag != qn("w:pgMar"):
                final.remove(child)
        refs = sorted(inherited.values(), key=lambda e: e.tag == qn("w:footerReference"))
        for child in reversed(refs): final.insert(0, child)
    used = {value for e in body.iter() for key, value in e.attrib.items()
            if key.startswith("{" + REL.rstrip("/") + "}")}
    static = {"styles", "stylesWithEffects", "settings", "webSettings", "fontTable",
              "theme", "numbering"}
    # Settings refer to note separators by numeric IDs, without an explicit r:id.
    for note in ("footnote", "endnote"):
        if doc.settings.element.find(qn("w:" + note + "Pr")) is not None:
            static.add(note + "s")
    for rid, rel in list(doc.part.rels.items()):
        if rid not in used and rel.reltype.rsplit("/", 1)[-1] not in static:
            doc.part.drop_rel(rid)
    element(doc.settings.element, "updateFields", val="false")


class Builder:
    def __init__(self, args, tokens, mapping, styles):
        self.args, self.tokens, self.mapping = args, tokens, mapping
        self.doc = Document(args.template) if args.template else Document()
        clean_template(self.doc)
        configure_styles(self.doc, bool(args.template), styles)
        self.expected, self.images, self.links, self.warnings = [], [], [], []
        self.counts = Counter(code_blocks=0, code_lines=0, tables=0, figures=0)
        self.lists, self.quote = [], 0
        self.landscape, self.has_title = False, False
        self.section(self.doc.sections[0], False)
        if not args.template:
            for attr in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
                setattr(self.doc.sections[0], attr, Pt(72))
        self.bookmarks, seen = {}, Counter()
        for i, token in enumerate(tokens):
            if token.type == "heading_open":
                base = slug(inline_text(tokens[i + 1].children or [])) or "heading"
                suffix = f"-{seen[base]}" if seen[base] else ""
                self.bookmarks[i] = base + suffix
                seen[base] += 1
        self.valid_anchors = {value: f"md_heading_{i}" for i, value in self.bookmarks.items()}
        self.reverse_anchors = {value: key for key, value in self.valid_anchors.items()}

    @staticmethod
    def section(section, landscape):
        section.orientation = WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
        section.page_width, section.page_height = (Cm(29.7), Cm(21)) if landscape else (Cm(21), Cm(29.7))
        for attr in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
            if getattr(section, attr) is None: setattr(section, attr, Cm(2.54))

    def space(self):
        s = self.doc.sections[-1]
        return ((s.page_width - s.left_margin - s.right_margin) / 12700,
                (s.page_height - s.top_margin - s.bottom_margin) / 12700)

    def record(self, text):
        self.expected.append({"kind": "paragraph", "text": text})

    def run(self, paragraph, text, bold=False, italic=False, code=False, parent=None):
        r = paragraph.add_run(text)
        if parent is not None:
            parent.append(r._r)
        r.bold = True if bold else None
        r.italic = True if italic else None
        style = self.doc.styles["MD Code"] if code and paragraph.style.name != "MD Code" else paragraph.style
        explicit_fonts(r._r, effective_font(style, "ascii", "Consolas" if code else "宋体"),
                       effective_font(style, "eastAsia", "宋体"))
        return r

    def image_path(self, token):
        raw = token.attrGet("src")
        source = (self.args.source.parent / unquote(raw)).resolve()
        target = self.mapping.get(raw, self.mapping.get(str(source)))
        if target is not None:
            path = Path(target)
            path = path if path.is_absolute() else self.args.image_map.parent / path
        else:
            if urlsplit(raw).scheme or raw.startswith("//"):
                raise ValueError(f"Remote image needs a local --image-map entry: {raw}")
            path = source
        path = path.resolve()
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            raise ValueError(f"Image must be rendered to PNG/JPEG first; use explicit --image-map: {raw}")
        if not path.is_file():
            raise ValueError(f"Missing image: {path}")
        return path

    def picture(self, paragraph, token):
        path = self.image_path(token)
        blob = path.read_bytes()
        with Image.open(path) as im:
            if im.format not in {"PNG", "JPEG"}:
                raise ValueError(f"Unsupported image data: {path}")
            iw, ih = im.size
            im.verify()
        width_limit, height_limit = self.space()
        width = min(iw * 72 / 96, width_limit)
        width = min(width, max(1, height_limit - 30) * iw / ih)
        shape = paragraph.add_run().add_picture(str(path), width=Pt(width))
        shape._inline.docPr.set("descr", token.content)
        shape._inline.docPr.set("title", token.content)
        self.images.append({"sha256": sha(blob), "alt": token.content,
                            "source": token.attrGet("src"), "resource": str(path)})
        self.counts["figures"] += 1

    def inline(self, paragraph, tokens):
        bold = italic = 0
        link = None
        for t in tokens:
            kind = t.type
            if kind == "strong_open": bold += 1
            elif kind == "strong_close": bold -= 1
            elif kind == "em_open": italic += 1
            elif kind == "em_close": italic -= 1
            elif kind == "link_open":
                href = t.attrGet("href")
                link = OxmlElement("w:hyperlink")
                if href.startswith("#"):
                    anchor = unquote(href[1:])
                    if anchor not in self.valid_anchors:
                        raise ValueError(f"Unresolved heading link: {href}")
                    link.set(qn("w:anchor"), self.valid_anchors[anchor])
                elif urlsplit(href).scheme.lower() in {"http", "https", "mailto", "tel"}:
                    link.set(qn("r:id"), self.doc.part.relate_to(href, REL + "hyperlink", is_external=True))
                else:
                    raise ValueError(f"Local-file/unsupported hyperlink needs explicit revision: {href}")
                paragraph._p.append(link)
                self.links.append(unquote(href) if href.startswith("#") else href)
            elif kind == "link_close": link = None
            elif kind in {"text", "code_inline", "softbreak", "hardbreak", "html_inline"}:
                text = " " if kind == "softbreak" else "\n" if kind in {"hardbreak", "html_inline"} else t.content
                r = self.run(paragraph, text, bold > 0, italic > 0, kind == "code_inline", link)
                if link is not None:
                    element(r._r.get_or_add_rPr(), "rStyle", val="Hyperlink")
            elif kind == "image":
                if link is not None:
                    raise ValueError("Linked images are unsupported; use separate image and link.")
                self.picture(paragraph, t)
            else:
                raise ValueError(f"Unsupported inline token: {kind}")

    def paragraph(self, tokens, style="Normal"):
        p = self.doc.add_paragraph(style=style)
        pf = p.paragraph_format
        prefix = ""
        if self.lists:
            state = self.lists[-1]
            prefix = (f"{state['index']}. " if state["ordered"] else "• ") if not state["used"] else ""
            state["used"] = True
            self.run(p, prefix)
            pf.left_indent = Pt(18 * len(self.lists))
            pf.first_line_indent = Pt(-18 if prefix else 0)
        if self.quote:
            pf.left_indent = Pt(18 * (len(self.lists) + self.quote))
            if not self.lists: pf.first_line_indent = Pt(0)
        pf.keep_together = False
        self.inline(p, tokens)
        self.record(prefix + inline_text(tokens))
        return p

    def table(self, rows, code=False):
        table = self.doc.add_table(rows=len(rows), cols=len(rows[0]))
        table.autofit = False
        width = self.space()[0] / len(rows[0])
        element(table._tbl.tblPr, "tblLayout", type="fixed")
        element(table._tbl.tblPr, "tblW", w=round(self.space()[0] * 20), type="dxa")
        borders = element(table._tbl.tblPr, "tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            element(borders, edge, val="nil" if code and edge.startswith("inside") else "single", sz=4, color="B8BEC6")
        margins = element(table._tbl.tblPr, "tblCellMar")
        for edge in ("top", "left", "bottom", "right"):
            element(margins, edge, w=0 if code and edge in {"top", "bottom"} else 60, type="dxa")
        for column in table.columns: column.width = Pt(width)
        for index, (row, values) in enumerate(zip(table.rows, rows)):
            element(row._tr.get_or_add_trPr(), "cantSplit")
            if index == 0 and not code: element(row._tr.get_or_add_trPr(), "tblHeader")
            for cell, value in zip(row.cells, values):
                cell.width = Pt(width)
                p = cell.paragraphs[0]
                p.style = "MD Code" if code else "MD Table"
                pf = p.paragraph_format
                pf.first_line_indent = pf.left_indent = pf.right_indent = Pt(0)
                pf.keep_together, pf.keep_with_next = False, False
                if code:
                    element(cell._tc.get_or_add_tcPr(), "shd", fill="F5F5F5", val="clear")
                    self.run(p, value, code=True)
                    pf.keep_with_next = index < len(rows) - 1 and (
                        index == 0 or bool(re.match(r"^\s*(?:#\s|(?:async\s+)?def\s|class\s|function\s)", value)))
                else:
                    self.inline(p, value)
                    if index == 0:
                        for r in p.runs: r.bold = True
        return table

    def code(self, token):
        if self.lists and not self.lists[-1]["used"]: self.paragraph([])
        lines = token.content.splitlines() or [""]
        table = self.table([[line] for line in lines], code=True)
        ident = f"md-code-{self.counts['code_blocks'] + 1}"
        element(table._tbl.tblPr, "tblCaption", val=ident)
        self.expected.append({"kind": "code", "rows": [[line] for line in lines]})
        self.counts.update(code_blocks=1, code_lines=len(lines))
        width = self.space()[0] - 6
        for number, line in enumerate(lines, 1):
            estimate = sum(4.75 * (4 if c == "\t" else 2 if unicodedata.east_asian_width(c) in "WF" else 1)
                           for c in line)
            if estimate > width:
                self.warnings.append(f"{ident} line {number}: may wrap at unchanged 9.5 pt; inspect rendered pages.")

    def build(self):
        i, first = 0, True
        while i < len(self.tokens):
            t = self.tokens[i]
            kind = t.type
            if kind in {"heading_open", "paragraph_open"}:
                children = self.tokens[i + 1].children or []
                if kind == "heading_open":
                    text = inline_text(children)
                    if self.args.landscape_heading and text == self.args.landscape_heading:
                        if self.landscape: raise ValueError("Landscape heading must be unique.")
                        if self.expected: self.doc.add_section(WD_SECTION_START.NEW_PAGE)
                        self.section(self.doc.sections[-1], True)
                        self.landscape = True
                    level = int(t.tag[1:])
                    if first and level == 1:
                        style, self.has_title = "Title", True
                    else:
                        style = f"Heading {max(1, level - int(self.has_title))}"
                    p = self.paragraph(children, style)
                    start, end = OxmlElement("w:bookmarkStart"), OxmlElement("w:bookmarkEnd")
                    start.set(qn("w:id"), str(i)); start.set(qn("w:name"), self.valid_anchors[self.bookmarks[i]])
                    end.set(qn("w:id"), str(i)); p._p.insert(1, start); p._p.append(end)
                else:
                    p = self.paragraph(children)
                    if len(children) == 1 and children[0].type == "image":
                        p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        p.paragraph_format.first_line_indent = Pt(0)
                        alt = children[0].content
                        following = self.tokens[i + 3:i + 6]
                        caption = None
                        if [token.type for token in following] == ["paragraph_open", "inline", "paragraph_close"]:
                            candidate = following[1].children or []
                            text = inline_text(candidate)
                            if text and not any(token.type == "image" for token in candidate) and (
                                    text == alt or re.match(r"^(?:图\s*|Figure\s+)\d+(?!\d)", text, re.I)):
                                caption = candidate
                        p.paragraph_format.keep_with_next = caption is not None or bool(alt)
                        if caption is not None:
                            self.paragraph(caption, "Caption")
                            i += 3
                        elif alt:
                            self.paragraph_text(alt, "Caption")
                first = False
                i += 3
                continue
            if kind in {"fence", "code_block"}: self.code(t); first = False
            elif kind in {"bullet_list_open", "ordered_list_open"}:
                self.lists.append(dict(ordered=kind.startswith("ordered"),
                                       index=int(t.attrGet("start") or 1) - 1, used=False))
            elif kind in {"bullet_list_close", "ordered_list_close"}: self.lists.pop()
            elif kind == "list_item_open":
                self.lists[-1]["index"] += 1; self.lists[-1]["used"] = False
            elif kind == "list_item_close": pass
            elif kind == "blockquote_open": self.quote += 1
            elif kind == "blockquote_close": self.quote -= 1
            elif kind == "table_open":
                if self.lists and not self.lists[-1]["used"]: self.paragraph([])
                rows, row = [], []
                i += 1
                while self.tokens[i].type != "table_close":
                    cell = self.tokens[i]
                    if cell.type == "tr_open": row = []
                    elif cell.type == "inline": row.append(cell.children or [])
                    elif cell.type == "tr_close": rows.append(row)
                    i += 1
                table = self.table(rows)
                self.expected.append({"kind": "table", "rows": [[inline_text(c) for c in r] for r in rows]})
                self.counts["tables"] += 1
            elif kind == "hr":
                p = self.doc.add_paragraph()
                element(element(p._p.get_or_add_pPr(), "pBdr"), "bottom", val="single", sz=4)
                self.record("")
            else: raise ValueError(f"Unsupported block token: {kind}")
            i += 1
        if self.args.landscape_heading and not self.landscape:
            raise ValueError(f"Landscape heading not found: {self.args.landscape_heading}")

    def paragraph_text(self, text, style):
        p = self.doc.add_paragraph(style=style)
        self.run(p, text)
        self.record(text)


def validate(path, builder):
    doc, actual = Document(path), []
    for node in doc.element.body:
        if node.tag == qn("w:p"):
            if node.find("./" + qn("w:pPr") + "/" + qn("w:sectPr")) is not None and not xml_text(node):
                continue
            actual.append({"kind": "paragraph", "text": xml_text(node)})
        elif node.tag == qn("w:tbl"):
            caption = node.find("./" + qn("w:tblPr") + "/" + qn("w:tblCaption"))
            code = caption is not None and caption.get(qn("w:val"), "").startswith("md-code-")
            rows = [[xml_text(c) for c in row.findall(qn("w:tc"))] for row in node.findall(qn("w:tr"))]
            actual.append({"kind": "code" if code else "table", "rows": rows})
    if actual != builder.expected:
        raise ValueError("DOCX semantic validation failed: paragraph/table/code sequence differs.")
    pictures = []
    for blip in doc.element.body.iter(qn("a:blip")):
        rid = blip.get(qn("r:embed"))
        if not rid: raise ValueError("DOCX contains a linked or missing image resource.")
        pictures.append(sha(doc.part.rels[rid].target_part.blob))
    if pictures != [i["sha256"] for i in builder.images]:
        raise ValueError("DOCX semantic validation failed: image resources/order differ.")
    alts = [e.get("descr", "") for e in doc.element.body.iter(qn("wp:docPr"))]
    if alts != [i["alt"] for i in builder.images]:
        raise ValueError("DOCX semantic validation failed: image alternative text differs.")
    links = [("#" + builder.reverse_anchors.get(e.get(qn("w:anchor")), "INVALID_ANCHOR")) if e.get(qn("w:anchor")) is not None
             else doc.part.rels[e.get(qn("r:id"))].target_ref
             for e in doc.element.body.iter(qn("w:hyperlink"))]
    if links != builder.links:
        raise ValueError("DOCX semantic validation failed: hyperlink targets/order differ.")
    external, relationships = [], Counter()
    for part in doc.part.package.parts:
        for rid, rel in part.rels.items():
            mode = "External" if rel.is_external else "Internal"
            relationships[(rel.reltype, mode)] += 1
            if rel.is_external:
                entry = dict(part=str(part.partname), id=rid, type=rel.reltype,
                             target_mode=mode, target=rel.target_ref)
                external.append(entry)
                if rel.reltype != REL + "hyperlink" or urlsplit(rel.target_ref).scheme.lower() not in {"http", "https", "mailto", "tel"}:
                    raise ValueError(f"External file/non-web relationship is forbidden: {entry}")
    fields = []
    for part in doc.part.package.parts:
        root = getattr(part, "element", None)
        if root is not None:
            fields.extend(e.text.strip() for e in root.iter(qn("w:instrText"))
                          if e.text and re.search(r"\b(?:PAGE|NUMPAGES)\b", e.text))
            fields.extend(e.get(qn("w:instr")) for e in root.iter(qn("w:fldSimple"))
                          if re.search(r"\b(?:PAGE|NUMPAGES)\b", e.get(qn("w:instr"), "")))
    if fields:
        builder.warnings.append("PAGE/NUMPAGES fields and cached results are retained. Render in Word/LibreOffice and verify page counts; updateFields=false.")
    return dict(body_fidelity="passed", semantic_records=len(actual),
                semantic_sha256=sha(json.dumps(actual, ensure_ascii=False).encode()),
                counts=dict(builder.counts), image_resources=len(set(pictures)), page_fields=fields,
                sections=[dict(orientation="landscape" if s.page_width > s.page_height else "portrait",
                               width_mm=round(s.page_width / 36000, 2), height_mm=round(s.page_height / 36000, 2))
                          for s in doc.sections], external_relationships=external,
                relationships_by_type_targetmode=[dict(type=k[0], target_mode=k[1], count=v)
                                                   for k, v in sorted(relationships.items())],
                visual_validation="not_run", warnings=builder.warnings)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--template", type=Path)
    parser.add_argument("--style-json", type=Path, help='Object keyed by Normal/Title/Heading 1..6/MD Code/MD Table/Caption; options: ' + ", ".join(sorted(STYLE_KEYS)))
    parser.add_argument("--image-map", type=Path, help='JSON object: Markdown image src (or absolute source path) -> rendered PNG/JPEG path; relative values resolve against this JSON.')
    parser.add_argument("--landscape-heading", help="Exact heading text starting the final landscape section.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--report", type=Path, help="Default: OUTPUT.validation.json")
    args, temporary = parser.parse_args(), []
    try:
        for name in ("source", "output", "template", "style_json", "image_map", "report"):
            value = getattr(args, name)
            if value is not None: setattr(args, name, value.resolve())
        args.report = args.report or args.output.with_suffix(".validation.json")
        protected = {p for p in (args.source, args.template, args.style_json, args.image_map) if p}
        if args.output in protected or args.report in protected or args.output == args.report:
            raise ValueError("Output/report must differ from all input files and from each other.")
        if args.output.suffix.lower() != ".docx": raise ValueError("--output must end in .docx")
        for path in (args.output, args.report):
            if path.exists() and not args.overwrite: raise ValueError(f"Refusing to overwrite: {path}; use --overwrite explicitly.")
        source_hash = sha(args.source.read_bytes())
        template_hash = sha(args.template.read_bytes()) if args.template else None
        tokens = MarkdownIt("commonmark", {"html": True}).enable("table").parse(args.source.read_text(encoding="utf-8-sig"))
        for t in tokens:
            if t.type.startswith("html") or any(c.type.startswith("html") and not
                    (c.type == "html_inline" and re.fullmatch(r"<br\s*/?>", c.content, re.I)) for c in (t.children or [])):
                raise ValueError(f"HTML is unsupported (source line {(t.map or [0])[0] + 1}); convert it explicitly first.")
            if t.type == "fence" and t.info.strip() and t.info.split(maxsplit=1)[0].lower() in DIAGRAMS:
                raise ValueError(f"Render {t.info} diagrams first, then reference their PNG/JPEG explicitly.")
        def read_object(path):
            value = json.loads(path.read_text(encoding="utf-8-sig")) if path else {}
            if not isinstance(value, dict): raise ValueError(f"Expected a JSON object: {path}")
            return value
        builder = Builder(args, tokens, read_object(args.image_map), read_object(args.style_json))
        builder.build()
        for path in (args.output, args.report): path.parent.mkdir(parents=True, exist_ok=True)
        for target in (args.output, args.report):
            fd, name = tempfile.mkstemp(prefix=".build-word-", suffix=target.suffix, dir=target.parent)
            os.close(fd); temporary.append(Path(name))
        builder.doc.save(temporary[0])
        report = validate(temporary[0], builder)
        if sha(args.source.read_bytes()) != source_hash or (args.template and sha(args.template.read_bytes()) != template_hash):
            raise ValueError("An input changed during conversion; no output was replaced.")
        report.update(source=str(args.source), source_sha256=source_hash,
                      template=str(args.template) if args.template else None,
                      template_sha256=template_hash, output=str(args.output), images=builder.images)
        temporary[1].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary[1], args.report)
        os.replace(temporary[0], args.output)
        print(json.dumps(dict(output=str(args.output), report=str(args.report), body_fidelity="passed",
                              visual_validation="not_run", warnings=len(builder.warnings)), ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    finally:
        for path in temporary: path.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
