#!/usr/bin/env python3
"""Read-only, evidence-bounded Markdown checks; requires markdown-it-py.

Usage: python check_markdown.py SOURCE [--report PATH] [--final] [--strict-links]
Exit codes: 0 = no errors (warnings allowed), 1 = check errors, 2 = run failure.
The report is UTF-8 JSON. No URL fetching or source-file changes are performed.
"""

from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import unquote, urlsplit


SCHEMA_VERSION = "1.0"
SCOPE = {
    "parser": "markdown-it-py: CommonMark with the built-in table rule enabled",
    "supported": [
        "ATX and Setext headings; parent-scoped section-number duplicates",
        "backtick and tilde fences, indented code, Markdown and HTML tables",
        "inline and defined reference links/images, HTML img src and a href",
        "URL-decoded relative paths, local file URLs and absolute Windows drive paths",
    ],
    "limitations": [
        "Heading and link locations use the start line of their parsed block.",
        "Unresolved reference labels are CommonMark literal text, not resolved links; they are not checked.",
        "MDX, template variables and custom Markdown extensions are not evaluated; detected dynamic targets are reported as unchecked.",
        "HTML srcset is reported as unsupported rather than silently assumed valid.",
        "Remote URLs, explicit network shares and fragment validity are not checked; existing files are not assessed for image format or content quality.",
        "Destinations follow CommonMark escaping rules; use file URLs or forward slashes for Windows paths containing backslash escapes.",
        "Final review checks recognize explicit markers only and make no semantic completeness judgment.",
    ],
}
DRIVE = re.compile(r"^[A-Za-z]:")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
DYNAMIC_TARGET = re.compile(r"\{\{|\{%|\$\{|<%")
CJK_NUMBERS = "零〇一二三四五六七八九十百千万两"
REVIEW_BRACKET = re.compile(
    r"(?:\[|【|（|\()(?:TODO|TBD|FIXME|待补(?:充)?|待完善|待确认|待审阅|待审核|占位(?:图|内容)?)(?:\s*[:：][^\]】）)]*)?(?:\]|】|）|\))",
    re.IGNORECASE,
)
REVIEW_LINE = re.compile(
    r"^\s*(?:(?:TODO|TBD|FIXME|审阅意见|审稿意见|批注|REVIEW(?:ER)?)(?:\s*[:：]\s*.*)|"
    r"(?:待补(?:充)?|待完善|待确认|待审阅|待审核|占位(?:图|内容)?|TBD)(?:\s*[:：]\s*.*)?)\s*$",
    re.IGNORECASE,
)
PLACEHOLDER_TEXT = re.compile(
    r"^\s*(?:(?:此处|这里)(?:待|需|请)?(?:插入|补充|添加|填写)(?:图片|图表|内容|正文|说明)|"
    r"placeholder[ _-]+(?:image|content|text)|lorem\s+ipsum(?:\s+.*)?)(?:\s*[:：].*)?[。.!！]?\s*$",
    re.IGNORECASE,
)
REVIEW_COMMENT = re.compile(
    r"^\s*(?:(?:TODO|TBD|FIXME|REVIEW|REVIEWER|审阅意见|审稿意见|批注)(?:\s*[:：]|\s*$)|"
    r"(?:待补(?:充)?|待完善|待确认|待审阅|占位(?:图|内容)?)(?:\s*[:：]|\s*$))",
    re.IGNORECASE | re.MULTILINE,
)


class RunFailure(Exception):
    """An actionable operational failure, distinct from document findings."""


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise RunFailure("Invalid command line: " + message)


def issue(report, severity, code, message, line=None, **extra):
    item = {"severity": severity, "code": code, "message": message}
    if line is not None:
        item["line"] = line
        item["line_precision"] = "block_start"
    item.update(extra)
    report["issues"].append(item)


def plain_text(tokens):
    parts = []
    for token in tokens or []:
        if token.type in ("text", "code_inline"):
            parts.append(token.content)
        elif token.type in ("softbreak", "hardbreak"):
            parts.append("\n")
        elif token.type == "image":
            parts.append(plain_text(token.children) or token.content)
        elif token.children:
            parts.append(plain_text(token.children))
    return "".join(parts)


def chinese_integer(text):
    digits = {char: value for value, char in enumerate("零一二三四五六七八九")}
    digits.update({"〇": 0, "两": 2})
    if all(char in digits for char in text):
        return int("".join(str(digits[char]) for char in text))
    units = {"十": 10, "百": 100, "千": 1000, "万": 10000}
    total = section = number = 0
    for char in text:
        if char in digits:
            number = digits[char]
        elif char == "万":
            section = (section + number) * units[char]
            total += section
            section = number = 0
        elif char in units:
            section += (number or 1) * units[char]
            number = 0
        else:
            return text
    return total + section + number


def section_number(text):
    """Return an explicit numbering prefix, never an arbitrary leading number."""
    text = unicodedata.normalize("NFKC", text).strip()
    ordinal = re.match(r"^第([0-9" + CJK_NUMBERS + r"]+)(章|节|篇|部分)", text)
    if ordinal:
        number, unit = ordinal.groups()
        return "ordinal:" + unit + ":" + str(int(number) if number.isdigit() else chinese_integer(number))
    arabic = re.match(r"^(\d+(?:\.\d+)+)(?=$|[\s、.)\u4e00-\u9fff])", text)
    if not arabic:
        arabic = re.match(r"^(\d+)(?:[、).](?!\d)|(?=\s|$))", text)
    if arabic:
        return "number:" + ".".join(str(int(part)) for part in arabic.group(1).split("."))
    chinese = re.match(r"^([" + CJK_NUMBERS + r"]+)[、.)]", text)
    if chinese:
        return "number:" + str(chinese_integer(chinese.group(1)))
    return None


def resolve_destination(destination, source):
    """Return (kind, resolved-path-or-None, reason-or-None); never fetch URLs."""
    target = destination.strip()
    if not target or target.startswith("#"):
        return "unchecked", None, "document_fragment_or_empty"
    if DYNAMIC_TARGET.search(unquote(target)):
        return "unsupported", None, "dynamic_or_template_target"
    is_drive = bool(DRIVE.match(target))
    is_unc = target.startswith("\\\\")
    if is_unc:
        return "unchecked", None, "network_share"
    if target.startswith("//") and not is_unc:
        return "unchecked", None, "remote_url"
    if SCHEME.match(target) and not is_drive:
        if not target.lower().startswith("file:"):
            return "unchecked", None, "url_scheme"
        try:
            url = urlsplit(target)
        except ValueError as exc:
            return "invalid", None, str(exc)
        path_text = unquote(url.path)
        if url.netloc and url.netloc.lower() != "localhost":
            return "unchecked", None, "network_share"
        elif re.match(r"^/[A-Za-z]:", path_text):
            path_text = path_text[1:]
    else:
        # Split URL decorations before decoding so %23/%3F remain filename text.
        path_text = unquote(target.split("#", 1)[0].split("?", 1)[0])
    if not path_text:
        return "unchecked", None, "document_fragment_or_empty"
    if DRIVE.match(path_text) and (len(path_text) < 3 or path_text[2] not in "/\\"):
        return "unsupported", None, "drive_relative_path_requires_absolute_path"
    if "\x00" in path_text:
        return "invalid", None, "Destination contains a NUL character."
    if os.name != "nt" and (DRIVE.match(path_text) or path_text.startswith("\\\\")):
        return "unsupported", None, "windows_absolute_path_on_non_windows_host"
    path = Path(path_text)
    if not path.is_absolute() and not DRIVE.match(path_text):
        path = source.parent / path
    try:
        return "local", path.resolve(strict=False), None
    except (OSError, ValueError) as exc:
        return "invalid", None, str(exc)


def review_text(report, text, line, context="prose"):
    for offset, text_line in enumerate(text.splitlines()):
        # Parsed list text has no bullet; these prefixes also support HTML prose.
        candidate = re.sub(r"^\s*(?:[-+*]\s+|\d+[.)]\s+)", "", text_line)
        if REVIEW_BRACKET.match(candidate.lstrip()) or REVIEW_LINE.fullmatch(candidate) or PLACEHOLDER_TEXT.fullmatch(candidate):
            issue(report, "warning", "review_issue", "Explicit unfinished-content or placeholder marker.",
                  line, context=context, marker=text_line.strip()[:240])


def check_link(report, source, target, line, kind, label=""):
    entry = {"kind": kind, "target": target, "line": line, "line_precision": "block_start"}
    if label:
        entry["label"] = label
    disposition, path, reason = resolve_destination(target, source)
    entry["status"] = disposition
    if path is not None:
        entry["resolved_path"] = str(path)
        try:
            present = path.is_file() if kind == "image" else path.exists()
        except (OSError, ValueError) as exc:
            present = None
            issue(report, "error", "local_target_access_error", str(exc), line, target=target, resolved_path=str(path))
        if present is True:
            entry["status"] = "exists"
        elif present is False:
            entry["status"] = "missing"
            severity = "error" if kind == "image" or report["options"]["strict_links"] else "warning"
            code = "missing_local_image" if kind == "image" else "missing_local_link"
            issue(report, severity, code, "Local image file is missing or is not a file." if kind == "image" else "Local link target does not exist.",
                  line, target=target, resolved_path=str(path))
        else:
            entry["status"] = "access_error"
    elif disposition in ("invalid", "unsupported"):
        entry["reason"] = reason
        issue(report, "error" if disposition == "invalid" else "warning", "invalid_target" if disposition == "invalid" else "unsupported_target",
              "Destination cannot be checked: " + str(reason), line, target=target)
    else:
        entry["reason"] = reason
    report["links"].append(entry)
    if kind == "image" and report["options"]["final"]:
        basename = re.split(r"[/\\]", unquote(target).split("#", 1)[0].split("?", 1)[0])[-1]
        placeholder_name = re.match(r"^(?:placeholder(?:[ _-]?(?:image|content|text|\d+))?|todo|tbd|占位(?:图|图片)?)(?:\.[^.]+)?$", basename, re.IGNORECASE)
        placeholder_label = re.fullmatch(r"\s*(?:占位(?:图|图片)|placeholder(?:[ _-]+image)?|TODO|TBD)(?:\s*[:：].*)?\s*", label, re.IGNORECASE)
        if placeholder_name or placeholder_label or REVIEW_BRACKET.fullmatch(label.strip()):
            issue(report, "warning", "review_issue", "Image has an explicit placeholder name or label.", line, context="image", target=target, marker=label or basename)


class HtmlChecks(HTMLParser):
    def __init__(self, report, source, line):
        super().__init__(convert_charrefs=True)
        self.report, self.source, self.line = report, source, line
        self.in_raw = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        line = self.line  # HTML fragments may span tokens; use the documented block location.
        if tag in ("script", "style", "pre", "code"):
            self.in_raw += 1
        if tag == "table":
            self.report["summary"]["table_count"] += 1
        if tag == "img":
            if attrs.get("src") is not None:
                check_link(self.report, self.source, attrs["src"], line, "image", attrs.get("alt") or "")
            elif "srcset" not in attrs:
                issue(self.report, "warning", "html_image_without_src", "HTML img has no src destination to check.", line)
        if tag == "a" and attrs.get("href") is not None:
            check_link(self.report, self.source, attrs["href"], line, "link")
        if "srcset" in attrs:
            issue(self.report, "warning", "unsupported_html_srcset", "HTML srcset destinations are not parsed or checked.", line, target=attrs["srcset"])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "pre", "code") and self.in_raw:
            self.in_raw -= 1

    def handle_comment(self, data):
        if self.report["options"]["final"] and not self.in_raw and REVIEW_COMMENT.search(data):
            issue(self.report, "warning", "review_issue", "Explicit review or unfinished-content marker in an HTML comment.",
                  self.line, context="html_comment", marker=data.strip()[:240])

    def handle_data(self, data):
        if self.report["options"]["final"] and not self.in_raw:
            review_text(self.report, data, self.line, "html_prose")


def inspect_markdown(source, raw, final=False, strict_links=False):
    try:
        from markdown_it import MarkdownIt
    except ImportError as exc:
        raise RunFailure("Missing dependency markdown-it-py. Install with: python -m pip install markdown-it-py") from exc
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise RunFailure(f"Source is not valid UTF-8 at byte {exc.start}: {source}") from exc
    report = {
        "schema_version": SCHEMA_VERSION, "source": str(source), "source_sha256": hashlib.sha256(raw).hexdigest(),
        "options": {"final": final, "strict_links": strict_links}, "status": "ok", "scope": SCOPE,
        "summary": {"heading_count": 0, "code_block_count": 0, "fenced_code_block_count": 0,
                    "indented_code_block_count": 0, "image_count": 0, "link_count": 0, "table_count": 0},
        "headings": [], "links": [], "issues": [],
    }
    try:
        parser = MarkdownIt("commonmark").enable("table")
        # Renderer defaults reject file: and certain URI schemes. This inspector
        # never renders/navigates a destination; preserve them for classification.
        parser.validateLink = lambda _target: True
        tokens = parser.parse(text)
    except Exception as exc:
        raise RunFailure(f"Markdown parsing failed ({type(exc).__name__}): {exc}") from exc

    previous_level = None
    h1_lines = []
    parents = []
    numbered = {}
    html = HtmlChecks(report, source, 1)
    for index, token in enumerate(tokens):
        line = token.map[0] + 1 if token.map else 1
        if token.type == "heading_open":
            level = int(token.tag[1:])
            content = tokens[index + 1] if index + 1 < len(tokens) else None
            title = plain_text(content.children) if content and content.type == "inline" else ""
            report["summary"]["heading_count"] += 1
            heading_id = len(report["headings"]) + 1
            while parents and parents[-1][0] >= level:
                parents.pop()
            parent_id = parents[-1][1] if parents else None
            number = section_number(title)
            report["headings"].append({"level": level, "text": title, "line": line, "number": number, "parent_id": parent_id})
            if previous_level is not None and level > previous_level + 1:
                issue(report, "error", "heading_level_skip", f"Heading level jumps from H{previous_level} to H{level}.", line, heading=title)
            if level == 1:
                if h1_lines:
                    issue(report, "error", "multiple_h1", "Document contains more than one H1 heading.", line, first_h1_line=h1_lines[0])
                h1_lines.append(line)
            if number is not None:
                key = (parent_id, level, number)
                if key in numbered:
                    issue(report, "error", "duplicate_section_number", "Section number repeats under the same parent heading.", line,
                          heading=title, number=number, first_line=numbered[key], parent_id=parent_id)
                else:
                    numbered[key] = line
            parents.append((level, heading_id))
            previous_level = level
        elif token.type in ("fence", "code_block"):
            report["summary"]["code_block_count"] += 1
            if token.type == "code_block":
                report["summary"]["indented_code_block_count"] += 1
            else:
                report["summary"]["fenced_code_block_count"] += 1
                # markdown-it preserves one content newline per source interior line.
                # Its mapped span contains two fence lines only if a closer was found,
                # including inside lists and blockquotes (where raw regexes misread indent).
                span = token.map[1] - token.map[0]
                closed = span == token.content.count("\n") + 2
                if not closed:
                    issue(report, "error", "unclosed_code_fence", "Fenced code block has no matching closing fence before its container ends.", line, fence=token.markup)
                elif not token.info.strip():
                    issue(report, "warning", "code_fence_without_language", "Closed code fence has no language/info string.", line, fence=token.markup)
        elif token.type == "table_open":
            report["summary"]["table_count"] += 1
        elif token.type == "html_block":
            html.line = line
            html.feed(token.content)
        elif token.type == "inline":
            prose = []
            for child in token.children or []:
                if child.type == "image":
                    check_link(report, source, child.attrGet("src") or "", line, "image", plain_text(child.children) or child.content)
                elif child.type == "link_open":
                    check_link(report, source, child.attrGet("href") or "", line, "link")
                elif child.type == "html_inline":
                    html.line = line
                    html.feed(child.content)
                    prose.append(" [HTML boundary] ")
                elif child.type == "text":
                    if not html.in_raw:
                        prose.append(child.content)
                elif child.type in ("softbreak", "hardbreak"):
                    prose.append("\n")
                elif child.type == "code_inline":
                    # Keep adjacent prose apart without interpreting code as a marker.
                    prose.append(" [inline code] ")
            if final:
                review_text(report, "".join(prose), line)
    html.close()
    report["summary"]["image_count"] = sum(link["kind"] == "image" for link in report["links"])
    report["summary"]["link_count"] = sum(link["kind"] == "link" for link in report["links"])
    report["summary"]["unchecked_target_count"] = sum(link["status"] in ("unchecked", "unsupported") for link in report["links"])
    report["summary"]["error_count"] = sum(item["severity"] == "error" for item in report["issues"])
    report["summary"]["warning_count"] = sum(item["severity"] == "warning" for item in report["issues"])
    report["summary"]["review_issue_count"] = sum(item["code"] == "review_issue" for item in report["issues"])
    report["status"] = "errors" if report["summary"]["error_count"] else "ok"
    return report


def main(argv=None):
    parser = JsonArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="UTF-8 Markdown source file (read only)")
    parser.add_argument("--report", help="Optional JSON output path; must differ from source")
    parser.add_argument("--final", action="store_true", help="Warn about explicit review/pending/placeholder markers")
    parser.add_argument("--strict-links", action="store_true", help="Treat missing ordinary local links as errors")
    report = None
    try:
        args = parser.parse_args(argv)
        source = Path(args.source).resolve()
        destination = Path(args.report).resolve() if args.report else None
        if destination is not None:
            same = os.path.normcase(str(destination)) == os.path.normcase(str(source))
            if destination.exists() and source.exists():
                same = same or os.path.samefile(destination, source)
            if same:
                raise RunFailure(f"Report path must differ from the source file: {source}")
        try:
            raw = source.read_bytes()
        except (OSError, ValueError) as exc:
            raise RunFailure(f"Cannot read source {source}: {exc}") from exc
        report = inspect_markdown(source, raw, args.final, args.strict_links)
        # Detect an external concurrent edit; do not claim a stable source snapshot.
        try:
            if hashlib.sha256(source.read_bytes()).hexdigest() != report["source_sha256"]:
                raise RunFailure(f"Source changed during inspection: {source}")
        except OSError as exc:
            raise RunFailure(f"Cannot recheck source {source}: {exc}") from exc
        if destination is not None:
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            except (OSError, ValueError) as exc:
                raise RunFailure(f"Cannot write report {destination}: {exc}") from exc
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if report["summary"]["error_count"] else 0
    except (RunFailure, OSError, ValueError) as exc:
        result = {"schema_version": SCHEMA_VERSION, "status": "runtime_error", "error": str(exc)}
        if report is not None:
            result["inspection"] = report
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
