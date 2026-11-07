"""Synthetic Excel COM regression for presentation formatting.

Run on Windows with Python, openpyxl, Excel and Windows PowerShell 5.1:
    python -X utf8 -m unittest discover -s tests -p test_format_workbook_presentation.py

No real workbook is used. Fixtures are created in a temporary directory; existing
user Excel processes are observed but are never opened, closed, or terminated.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Border, PatternFill, Side

SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "format_workbook_presentation.ps1"
POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
SCENE1 = "对话(2K/2K) - 中短对话"
SCENE2 = "特长上下文（1M/1K）99% Prefix Cache命中率"
SCENE2_NEW = "特长上下文（1M/1K）99% 前缀配置比例"
GREEN = "FF92D050"
GREEN_ALT = "0092D050"


def excel_pids() -> set[int]:
    p = subprocess.run(
        ["tasklist.exe", "/fi", "IMAGENAME eq EXCEL.EXE", "/fo", "csv", "/nh"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    result = set()
    for row in csv.reader(p.stdout.splitlines()):
        if len(row) > 1 and row[0].lower() == "excel.exe":
            result.add(int(row[1]))
    return result


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_fixture(path: Path, dual: bool) -> None:
    wb = Workbook()
    note = wb.active
    note.title = "说明"
    note["A1"] = "仅为合成测试数据；不读取真实工作簿。"
    note["A2"] = "来源及证据状态保留"
    sheets = ["基线", "调优"] if dual else ["单组实测"]
    thin = Side(style="thin", color="FF000000")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for name in sheets:
        ws = wb.create_sheet(name)
        for col in range(1, 25 if name == "调优" else 23):
            ws.cell(1, col, f"header-{col}")
        # Real perf-benchmark headers are required before SLA recoloring.
        ws["G1"] = "场景"
        ws["J1"] = "并发"
        ws["M1"] = "Mean TTFT (s)"
        ws["O1"] = "Mean TPOT (ms)"
        for row in range(2, 6):
            for col in range(1, 25 if name == "调优" else 23):
                ws.cell(row, col).border = border
        for col in "ABCDEF":
            ws.merge_cells(f"{col}2:{col}5")
        for col in "GHI":
            ws.merge_cells(f"{col}2:{col}3")
            ws.merge_cells(f"{col}4:{col}5")
        ws["A2"] = "synthetic model"
        ws["D2"] = "synthetic hardware"
        ws["E2"] = "old software"
        ws["F2"] = "TP4\n\n补充历史实测信息：\nTP4"
        ws["G2"] = SCENE1
        ws["G4"] = SCENE2
        ws["H2"] = "old SLA"
        ws["H4"] = "old long SLA"
        ws["I2"] = "old feature"
        ws["I4"] = "old feature"
        # J = concurrency; M = mean TTFT seconds; O = mean TPOT ms.
        # S x J = T, as required by the E2E contract.
        values = (
            [(1, 2, 35, 100), (4, 7, 55, 200), (1, 5, 50, 100), (2, 31, 130, 200)]
            if name != "调优" else
            [(1, 3, 50, 120), (3, 9, 80, 210), (1, 10, 100, 150), (2, 30, 120, 230)]
        )
        for i, (concurrency, ttft, tpot, total) in enumerate(values, 2):
            ws.cell(i, 10, concurrency)
            ws.cell(i, 11, 2048 if i < 4 else 1048576)
            ws.cell(i, 12, 1024)
            ws.cell(i, 13, ttft)
            ws.cell(i, 14, ttft + 0.1)
            ws.cell(i, 15, tpot)
            ws.cell(i, 16, tpot + 1)
            ws.cell(i, 17, total / (2 * concurrency))
            ws.cell(i, 18, total / 2)
            ws.cell(i, 19, total / concurrency)
            ws.cell(i, 20, total)
            ws.cell(i, 21, 0.1)
            ws.cell(i, 22, "preserve notes")
        # Start by highlighting first row of each block.
        green = PatternFill("solid", fgColor=GREEN)
        for row in (2, 4):
            for col in range(10, 21):
                ws.cell(row, col).fill = green
        if name == "调优":
            ws["W2"] = 100
            ws["X2"] = "=(T2-W2)/W2"
            # C3 has no matching baseline; W3/X3 must stay blank.
            ws["W4"] = 100
            ws["X4"] = "=(T4-W4)/W4"
            ws["W5"] = 200
            ws["X5"] = "=(T5-W5)/W5"
    wb.save(path)
    wb.close()


def scenario(name: str, *, rename: bool = False, eligible: list[int] | None = None) -> dict:
    d = {
        "name": name,
        "sla_text": "TPOT≈50~60ms\nTTFT≈5~8秒" if name == SCENE1 else "TPOT≤120ms\nTTFT≤30秒",
        "feature_text": "SmartDecoding",
        "ttft_limit_s": 8 if name == SCENE1 else 30,
        "tpot_limit_ms": 60 if name == SCENE1 else 120,
        "eligible_concurrency": eligible if eligible is not None else ([1, 4] if name == SCENE1 else [1, 2]),
    }
    if rename:
        d["display_name"] = SCENE2_NEW
    return d


def launch(src: Path, dst: Path, manifest: dict, meta: Path):
    meta.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return subprocess.run(
        [str(POWERSHELL), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
         "-WorkbookPath", str(src), "-PresentationPath", str(meta), "-OutputPath", str(dst)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240,
    )


def color(cell):
    value = cell.fill.fgColor
    return (value.rgb or "").upper() if value.type == "rgb" else ""


class FormatWorkbookPresentationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="perf-e2e-synthetic-")
        self.base = Path(self.temp.name)
        self.existing_excel = excel_pids()

    def tearDown(self):
        # The formatting script may clean up only the Excel instance that it created.
        # Never close or terminate any process from this test harness.
        remaining = excel_pids()
        self.assertTrue(self.existing_excel.issubset(remaining),
                        f"An existing Excel session disappeared: {self.existing_excel - remaining}")
        for _ in range(10):
            leaked = excel_pids() - self.existing_excel
            if not leaked:
                break
            time.sleep(0.5)
        self.assertFalse(leaked, f"New Excel process remains after formatter: {leaked}")
        self.temp.cleanup()

    def test_single_run_preserves_metrics_and_formats_explicit_metadata(self):
        src, dst, meta = self.base / "single.xlsx", self.base / "single-out.xlsx", self.base / "single.json"
        make_fixture(src, dual=False)
        source_hash = sha256(src)
        software = "OS:SyntheticOS\n推理引擎:example\n测试执行命令:\nrun --example 'a b'"
        parallel = "DP1 / TP4 / PP4"
        manifest = {"sheets": [{"sheet": "单组实测", "software_text": software,
                                "parallelism_text": parallel, "software_column_width": 45,
                                "data_row_height": 28,
                                "scenarios": [scenario(SCENE1), scenario(SCENE2, rename=True)]}]}
        p = launch(src, dst, manifest, meta)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("PRESENTATION_VALIDATION=PASS", p.stdout)
        self.assertEqual(sha256(src), source_hash)
        before = load_workbook(io.BytesIO(src.read_bytes()), data_only=False)
        after = load_workbook(io.BytesIO(dst.read_bytes()), data_only=False)
        self.assertEqual(before.sheetnames, after.sheetnames)
        x, y = before["单组实测"], after["单组实测"]
        self.assertEqual(set(map(str, x.merged_cells.ranges)), set(map(str, y.merged_cells.ranges)))
        self.assertEqual(y["E2"].value, software)
        self.assertEqual(y["F2"].value, parallel)
        self.assertTrue(44 <= y.column_dimensions["E"].width <= 46, y.column_dimensions["E"].width)
        for row in range(2, 6):
            self.assertAlmostEqual(y.row_dimensions[row].height, 28, delta=0.1)
        self.assertEqual(y["G4"].value, SCENE2_NEW)
        self.assertEqual(y["H2"].value, "TPOT≈50~60ms\nTTFT≈5~8秒")
        self.assertEqual(y["H4"].value, "TPOT≤120ms\nTTFT≤30秒")
        self.assertEqual((y["I2"].value, y["I4"].value), ("SmartDecoding", "SmartDecoding"))
        for row in range(2, 6):
            for col in range(10, 23):
                self.assertEqual(y.cell(row, col).value, x.cell(row, col).value, (row, col))
            self.assertAlmostEqual(y.cell(row, 19).value * y.cell(row, 10).value, y.cell(row, 20).value)
        # Dialogue C4 is highest compliant, 1M C1 is highest compliant.
        for row, expected in ((2, False), (3, True), (4, True), (5, False)):
            self.assertEqual(color(y[f"J{row}"]) in {GREEN, GREEN_ALT}, expected, f"J{row}")
        self.assertEqual(after["说明"]["A1"].value, before["说明"]["A1"].value)
        before.close(); after.close()

    def test_dual_run_preserves_same_concurrency_comparison_and_unmatched(self):
        src, dst, meta = self.base / "dual.xlsx", self.base / "dual-out.xlsx", self.base / "dual.json"
        make_fixture(src, dual=True)
        source_hash = sha256(src)
        manifest = {"sheets": [
            {"sheet": "基线", "software_text": "OS:BaseOS", "parallelism_text": "TP4",
             "scenarios": [scenario(SCENE1), scenario(SCENE2)]},
            {"sheet": "调优", "software_text": "OS:TunedOS", "parallelism_text": "TP8",
             "scenarios": [scenario(SCENE1, eligible=[1, 3]), scenario(SCENE2)]},
        ]}
        p = launch(src, dst, manifest, meta)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("PRESENTATION_VALIDATION=PASS", p.stdout)
        self.assertEqual(sha256(src), source_hash)
        before = load_workbook(io.BytesIO(src.read_bytes()), data_only=False)
        after = load_workbook(io.BytesIO(dst.read_bytes()), data_only=False)
        self.assertEqual(after.sheetnames, before.sheetnames)
        for name, software in (("基线", "OS:BaseOS"), ("调优", "OS:TunedOS")):
            x, y = before[name], after[name]
            self.assertEqual(y["E2"].value, software)
            self.assertEqual(set(map(str, x.merged_cells.ranges)), set(map(str, y.merged_cells.ranges)))
            for row in range(2, 6):
                for col in range(10, 25 if name == "调优" else 23):
                    self.assertEqual(y.cell(row, col).value, x.cell(row, col).value, (name, row, col))
                self.assertAlmostEqual(y.cell(row, 19).value * y.cell(row, 10).value, y.cell(row, 20).value)
        t = after["调优"]
        self.assertEqual((t["W2"].value, t["X2"].value), (100, "=(T2-W2)/W2"))
        self.assertIsNone(t["W3"].value)
        self.assertIsNone(t["X3"].value)
        self.assertEqual(t["W5"].value, 200)
        self.assertEqual(t["X5"].value, "=(T5-W5)/W5")
        before.close(); after.close()

    def test_locked_input_and_existing_output_are_rejected_without_mutation(self):
        src, dst, meta = self.base / "source.xlsx", self.base / "out.xlsx", self.base / "meta.json"
        make_fixture(src, dual=False)
        source_hash = sha256(src)
        manifest = {"sheets": [{"sheet": "单组实测", "software_text": "OS:test"}]}
        lock = src.parent / ("~$" + src.name)
        lock.write_text("synthetic lock; never delete user locks", encoding="utf-8")
        p = launch(src, dst, manifest, meta)
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse(dst.exists())
        self.assertFalse(list(self.base.glob(".presentation-*.xlsx")))
        self.assertTrue(lock.exists())
        self.assertEqual(sha256(src), source_hash)
        lock.unlink()  # this file was created solely by the test in its temporary directory
        dst.write_bytes(b"synthetic existing output")
        old_output = dst.read_bytes()
        p = launch(src, dst, manifest, meta)
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(dst.read_bytes(), old_output)
        self.assertEqual(sha256(src), source_hash)

    def test_missing_threshold_or_custom_fill_cannot_be_silently_destroyed(self):
        src, dst, meta = self.base / "source.xlsx", self.base / "out.xlsx", self.base / "meta.json"
        make_fixture(src, dual=False)
        source_hash = sha256(src)
        partial = {"sheets": [{"sheet": "单组实测", "scenarios": [
            {"name": SCENE1, "tpot_limit_ms": 60}
        ]}]}
        p = launch(src, dst, partial, meta)
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse(dst.exists())
        self.assertFalse(list(self.base.glob(".presentation-*.xlsx")))
        self.assertEqual(sha256(src), source_hash)
        # A custom red highlight must never be repainted as the SLA row.
        raw = io.BytesIO(src.read_bytes())
        wb = load_workbook(raw)
        wb["单组实测"]["J3"].fill = PatternFill("solid", fgColor="FFFF0000")
        out_buffer = io.BytesIO()
        wb.save(out_buffer); wb.close(); raw.close()
        src.write_bytes(out_buffer.getvalue()); out_buffer.close()
        source_hash = sha256(src)
        custom = {"sheets": [{"sheet": "单组实测", "scenarios": [scenario(SCENE1)]}]}
        p = launch(src, dst, custom, meta)
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse(dst.exists())
        self.assertFalse(list(self.base.glob(".presentation-*.xlsx")))
        self.assertEqual(sha256(src), source_hash)

    def test_no_passing_row_removes_sla_green_and_display_only_preserves_other(self):
        src, dst, meta = self.base / "source.xlsx", self.base / "out.xlsx", self.base / "meta.json"
        make_fixture(src, dual=False)
        impossible = scenario(SCENE1)
        impossible["ttft_limit_s"] = 1
        impossible["tpot_limit_ms"] = 1
        display_only = {"name": SCENE2, "sla_text": "TPOT≤120ms\nTTFT≤30秒", "sla_limits_unchanged": True}
        manifest = {"sheets": [{"sheet": "单组实测", "scenarios": [impossible, display_only]}]}
        p = launch(src, dst, manifest, meta)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("PRESENTATION_VALIDATION=PASS", p.stdout)
        w = load_workbook(io.BytesIO(dst.read_bytes()), data_only=False)
        s = w["单组实测"]
        # No row meets impossible thresholds: no green row must be fabricated.
        self.assertNotIn(color(s["J2"]), {GREEN, GREEN_ALT})
        self.assertNotIn(color(s["J3"]), {GREEN, GREEN_ALT})
        # 1M display only has no threshold inputs: existing highlight preserved.
        self.assertIn(color(s["J4"]), {GREEN, GREEN_ALT})
        self.assertNotIn(color(s["J5"]), {GREEN, GREEN_ALT})
        self.assertEqual(s["H4"].value, "TPOT≤120ms\nTTFT≤30秒")
        w.close()

    def test_duplicate_concurrency_is_rejected_when_sla_is_recomputed(self):
        src, dst, meta = self.base / "source.xlsx", self.base / "out.xlsx", self.base / "meta.json"
        make_fixture(src, dual=False)
        raw = io.BytesIO(src.read_bytes())
        wb = load_workbook(raw)
        wb["单组实测"]["J3"] = 1
        out_buffer = io.BytesIO()
        wb.save(out_buffer); wb.close(); raw.close()
        src.write_bytes(out_buffer.getvalue()); out_buffer.close()
        source_hash = sha256(src)
        manifest = {"sheets": [{"sheet": "单组实测", "scenarios": [scenario(SCENE1)]}]}
        p = launch(src, dst, manifest, meta)
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse(dst.exists())
        self.assertFalse(list(self.base.glob(".presentation-*.xlsx")))
        self.assertEqual(sha256(src), source_hash)

    def test_sla_recolor_rejects_wrong_metric_headers_and_units(self):
        src, dst, meta = self.base / "source.xlsx", self.base / "out.xlsx", self.base / "meta.json"
        for address, header in (("M1", "Mean TTFT (ms)"), ("M1", "TTFT P90 (s)"), ("O1", "Mean TPOT (s)")):
            make_fixture(src, dual=False)
            raw = io.BytesIO(src.read_bytes()); wb = load_workbook(raw)
            wb["单组实测"][address] = header
            buf = io.BytesIO(); wb.save(buf); wb.close(); raw.close()
            src.write_bytes(buf.getvalue()); buf.close()
            digest = sha256(src)
            manifest = {"sheets": [{"sheet": "单组实测", "scenarios": [scenario(SCENE1)]}]}
            p = launch(src, dst, manifest, meta)
            self.assertNotEqual(p.returncode, 0, f"{address}={header!r}\n" + p.stdout + p.stderr)
            self.assertFalse(dst.exists())
            self.assertFalse(list(self.base.glob(".presentation-*.xlsx")))
            self.assertEqual(sha256(src), digest)

    def test_sensitive_values_are_rejected_without_disclosure(self):
        src, dst, meta = self.base / "source.xlsx", self.base / "out.xlsx", self.base / "meta.json"
        make_fixture(src, dual=False)
        digest = sha256(src)
        sentinel = "SYNTHETIC_SENSITIVE_VALUE_987654321"
        for text in (f"TOKEN={sentinel}", f"HF_TOKEN={sentinel}", f"Authorization: Bearer {sentinel}", f"TOKEN=<{sentinel}>"):
            p = launch(src, dst, {"sheets": [{"sheet": "单组实测", "software_text": text}]}, meta)
            self.assertNotEqual(p.returncode, 0, "sensitive text was accepted")
            self.assertNotIn(sentinel, p.stdout + p.stderr)
            self.assertFalse(dst.exists())
            self.assertFalse(list(self.base.glob(".presentation-*.xlsx")))
            self.assertEqual(sha256(src), digest)

    def test_scene_rename_rejects_normalized_duplicate(self):
        src, dst, meta = self.base / "source.xlsx", self.base / "out.xlsx", self.base / "meta.json"
        make_fixture(src, dual=False)
        digest = sha256(src)
        conflict = {"sheets": [{"sheet": "单组实测", "scenarios": [
            {"name": SCENE1, "display_name": "  " + SCENE2 + "  "}
        ]}]}
        p = launch(src, dst, conflict, meta)
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse(dst.exists())
        self.assertFalse(list(self.base.glob(".presentation-*.xlsx")))
        self.assertEqual(sha256(src), digest)

    def test_eligibility_is_mandatory_valid_and_controls_sla_selection(self):
        src, dst, meta = self.base / "source.xlsx", self.base / "out.xlsx", self.base / "meta.json"
        make_fixture(src, dual=False)
        digest = sha256(src)
        missing = scenario(SCENE1); del missing["eligible_concurrency"]
        outside = scenario(SCENE1, eligible=[1, 9])
        duplicate = scenario(SCENE1, eligible=[1, 1])
        for invalid in (missing, outside, duplicate):
            p = launch(src, dst, {"sheets": [{"sheet": "单组实测", "scenarios": [invalid]}]}, meta)
            self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertFalse(dst.exists())
            self.assertFalse(list(self.base.glob(".presentation-*.xlsx")))
            self.assertEqual(sha256(src), digest)
        # Both C1 and C4 pass; only C1 is eligible. The 1M empty eligibility
        # list means no valid rows and therefore no green selection.
        manifest = {"sheets": [{"sheet": "单组实测", "scenarios": [
            scenario(SCENE1, eligible=[1]), scenario(SCENE2, eligible=[])
        ]}]}
        p = launch(src, dst, manifest, meta)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("PRESENTATION_VALIDATION=PASS", p.stdout)
        w = load_workbook(io.BytesIO(dst.read_bytes()), data_only=False); sheet = w["单组实测"]
        self.assertIn(color(sheet["J2"]), {GREEN, GREEN_ALT})
        for row in (3, 4, 5):
            self.assertNotIn(color(sheet[f"J{row}"]), {GREEN, GREEN_ALT})
        w.close()
        self.assertEqual(sha256(src), digest)

    def test_safe_placeholders_and_token_length_flags_are_allowed(self):
        src, dst, meta = self.base / "source.xlsx", self.base / "out.xlsx", self.base / "meta.json"
        make_fixture(src, dual=False)
        software = ("OS:Example\nTOKEN=<TOKEN>\nHF_TOKEN=${HF_TOKEN}\n"
                    "Authorization: Bearer <REDACTED>\n"
                    "测试执行命令: serve --max-num-batched-tokens 1024")
        manifest = {"sheets": [{"sheet": "单组实测", "software_text": software,
                                "software_column_width": 70, "data_row_height": 30}]}
        p = launch(src, dst, manifest, meta)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("PRESENTATION_VALIDATION=PASS", p.stdout)
        w = load_workbook(io.BytesIO(dst.read_bytes()), data_only=False)
        self.assertEqual(w["单组实测"]["E2"].value, software)
        w.close()

    def test_incomplete_sla_green_is_rejected(self):
        src, dst, meta = self.base / "source.xlsx", self.base / "out.xlsx", self.base / "meta.json"
        make_fixture(src, dual=False)
        raw = io.BytesIO(src.read_bytes()); wb = load_workbook(raw)
        wb["单组实测"]["J2"].fill = PatternFill()
        buf = io.BytesIO(); wb.save(buf); wb.close(); raw.close()
        src.write_bytes(buf.getvalue()); buf.close()
        digest = sha256(src)
        p = launch(src, dst, {"sheets": [{"sheet": "单组实测", "scenarios": [scenario(SCENE1)]}]}, meta)
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse(dst.exists())
        self.assertFalse(list(self.base.glob(".presentation-*.xlsx")))
        self.assertEqual(sha256(src), digest)

    def test_sla_text_without_declared_unchanged_limits_is_rejected(self):
        src, dst, meta = self.base / "source.xlsx", self.base / "out.xlsx", self.base / "meta.json"
        make_fixture(src, dual=False); digest = sha256(src)
        change = {"sheets": [{"sheet": "单组实测", "scenarios": [
            {"name": SCENE2, "sla_text": "TPOT≤120ms\nTTFT≤30秒"}
        ]}]}
        p = launch(src, dst, change, meta)
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse(dst.exists())
        self.assertFalse(list(self.base.glob(".presentation-*.xlsx")))
        self.assertEqual(sha256(src), digest)

    def test_comparison_cell_green_preserved_when_only_display_changes(self):
        src, dst, meta = self.base / "source.xlsx", self.base / "out.xlsx", self.base / "meta.json"
        make_fixture(src, dual=True)
        raw=io.BytesIO(src.read_bytes()); wb=load_workbook(raw)
        wb["调优"]["W3"].fill=PatternFill("solid", fgColor=GREEN)
        wb["调优"]["X3"].fill=PatternFill("solid", fgColor=GREEN)
        buf=io.BytesIO(); wb.save(buf); wb.close(); raw.close(); src.write_bytes(buf.getvalue());buf.close()
        digest=sha256(src)
        manifest={"sheets":[{"sheet":"调优", "scenarios":[
            {"name":SCENE1,"feature_text":"SmartDecoding","sla_text":"TPOT≤60ms\nTTFT≤8秒","sla_limits_unchanged":True}
        ]}]}
        p=launch(src,dst,manifest,meta)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        w=load_workbook(io.BytesIO(dst.read_bytes()),data_only=False);t=w["调优"]
        self.assertIn(color(t["W3"]),{GREEN,GREEN_ALT})
        self.assertIn(color(t["X3"]),{GREEN,GREEN_ALT})
        self.assertIn(color(t["J2"]),{GREEN,GREEN_ALT})
        self.assertIsNone(t["W3"].value);self.assertIsNone(t["X3"].value)
        w.close();self.assertEqual(sha256(src),digest)

    def test_recompute_rejects_extra_green_anywhere_in_U_X_block(self):
        for dual, sheetname, target, scene in (
            (True, "调优", "W3", scenario(SCENE1, eligible=[1,3])),
            (False, "单组实测", "V5", scenario(SCENE2)),
        ):
            src=self.base / ("dual.xlsx" if dual else "single.xlsx")
            dst=self.base / ("dual-out.xlsx" if dual else "single-out.xlsx")
            meta=self.base / ("dual.json" if dual else "single.json")
            make_fixture(src,dual=dual)
            raw=io.BytesIO(src.read_bytes());wb=load_workbook(raw)
            wb[sheetname][target].fill=PatternFill("solid",fgColor=GREEN)
            buf=io.BytesIO();wb.save(buf);wb.close();raw.close();src.write_bytes(buf.getvalue());buf.close()
            digest=sha256(src)
            p=launch(src,dst,{"sheets":[{"sheet":sheetname,"scenarios":[scene]}]},meta)
            self.assertNotEqual(p.returncode,0,f"extra green {target} accepted\n"+p.stdout+p.stderr)
            self.assertFalse(dst.exists())
            self.assertFalse(list(self.base.glob(".presentation-*.xlsx")))
            self.assertEqual(sha256(src),digest)

    def test_unknown_scenario_and_unsafe_formula_text_are_not_silently_accepted(self):
        src, dst, meta = self.base / "source.xlsx", self.base / "out.xlsx", self.base / "meta.json"
        make_fixture(src, dual=False)
        source_hash = sha256(src)
        unknown = {"sheets": [{"sheet": "单组实测", "scenarios": [{"name": "不存在的场景", "feature_text": "X"}]}]}
        p = launch(src, dst, unknown, meta)
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse(dst.exists())
        self.assertFalse(list(self.base.glob(".presentation-*.xlsx")))
        self.assertEqual(sha256(src), source_hash)
        # Values beginning with formula markers must be rejected or persisted as
        # literal text; they must never become an executable Excel formula.
        text = "=1+1"
        malicious = {"sheets": [{"sheet": "单组实测", "software_text": text}]}
        p = launch(src, dst, malicious, meta)
        if p.returncode == 0:
            w = load_workbook(io.BytesIO(dst.read_bytes()), data_only=False)
            cell = w["单组实测"]["E2"]
            self.assertNotEqual(cell.data_type, "f")
            self.assertEqual(cell.value, text)
            w.close()
        else:
            self.assertFalse(dst.exists())
            self.assertFalse(list(self.base.glob(".presentation-*.xlsx")))
        self.assertEqual(sha256(src), source_hash)


if __name__ == "__main__":
    unittest.main(verbosity=2)
