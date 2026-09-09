# -*- coding: utf-8 -*-
"""Canonical XLSX validation for RCC BOQ exports.

The exporter supplies the exact in-memory rows derived from Revit. This module
then reads the generated Open XML package back from disk and compares every
non-empty cell, including formulas, before the temporary workbook is published.
Only a bounded summary is written for the local Agent Bridge; no arbitrary
workbook path is exposed through REST or MCP.
"""

from __future__ import division

import hashlib
import io
import json
import os
import re
import time
import zipfile
import xml.etree.ElementTree as ET


VALIDATION_SCHEMA = "rcc-boq-export-validation/1.0.0"
MAX_REPORTED_MISMATCHES = 50
_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CELL_REF = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")
_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


def default_validation_report_path():
    """Return the fixed current-user report path used by Agent Bridge."""
    root = os.environ.get("LOCALAPPDATA", "")
    if not root:
        return ""
    return os.path.join(root, "RCC_BOQ", "last_boq_validation.json")


def _number_text(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return str(value)
    try:
        text = str(value).strip()
        if text and _NUMBER.match(text):
            float(text)
            return text
    except Exception:
        pass
    return None


def _expected_cell(value):
    if isinstance(value, tuple) and len(value) == 2:
        marker = value[0]
        if marker in ("FORMULA", "REF"):
            expression = str(value[1] or "").strip()
            if expression.startswith("="):
                expression = expression[1:]
            return ("formula", expression)
        if marker == "MERGE_V":
            value = value[1]

    numeric = _number_text(value)
    if numeric is not None:
        return ("number", numeric)
    return ("string", "" if value is None else str(value))


def _expected_cells(rows):
    cells = {}
    for row_index, row in enumerate(rows or [], 1):
        for column_index, value in enumerate(row or [], 1):
            cell = _expected_cell(value)
            if cell[1] != "":
                cells[(row_index, column_index)] = cell
    return cells


def _column_number(letters):
    result = 0
    for character in letters:
        result = result * 26 + (ord(character) - ord("A") + 1)
    return result


def _sheet_cells(xml_bytes):
    root = ET.fromstring(xml_bytes)
    cells = {}
    for node in root.findall(".//{%s}c" % _MAIN_NS):
        reference = node.get("r", "")
        match = _CELL_REF.match(reference)
        if not match:
            continue
        key = (int(match.group(2)), _column_number(match.group(1)))
        formula = node.find("{%s}f" % _MAIN_NS)
        if formula is not None:
            value = ("formula", formula.text or "")
        elif node.get("t") == "inlineStr":
            parts = [item.text or "" for item in node.findall(".//{%s}t" % _MAIN_NS)]
            value = ("string", "".join(parts))
        else:
            raw = node.find("{%s}v" % _MAIN_NS)
            value = ("number", "" if raw is None else raw.text or "")
        if value[1] != "":
            cells[key] = value
    return cells


def _workbook_sheet_targets(archive):
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {}
    for relation in relationships.findall("{%s}Relationship" % _PACKAGE_REL_NS):
        targets[relation.get("Id")] = relation.get("Target", "")

    result = []
    for sheet in workbook.findall(".//{%s}sheet" % _MAIN_NS):
        relation_id = sheet.get("{%s}id" % _REL_NS)
        target = targets.get(relation_id, "")
        if target.startswith("/"):
            archive_path = target.lstrip("/")
        elif target.startswith("xl/"):
            archive_path = target
        else:
            archive_path = "xl/" + target.lstrip("/")
        result.append((sheet.get("name", ""), archive_path))
    return result


def _safe_detail(sheet_name, key, expected, actual):
    row_index, column_index = key
    return {
        "sheet": str(sheet_name)[:100],
        "row": row_index,
        "column": column_index,
        "expected_type": expected[0] if expected else "missing",
        "expected": (expected[1] if expected else "")[:250],
        "actual_type": actual[0] if actual else "missing",
        "actual": (actual[1] if actual else "")[:250],
    }


def validate_workbook(workbook_path, sheet_names, sheet_rows,
                      document_title="", export_format="", tool_version=""):
    """Compare a generated XLSX package with its canonical source rows."""
    expected_names = list(sheet_names or [])
    mismatches = []
    mismatch_count = 0
    expected_cell_count = 0
    actual_cell_count = 0
    actual_names = []

    with zipfile.ZipFile(workbook_path, "r") as archive:
        targets = _workbook_sheet_targets(archive)
        actual_names = [item[0] for item in targets]
        if actual_names != expected_names:
            mismatch_count += 1
            mismatches.append({
                "kind": "sheet_order",
                "expected": expected_names[:50],
                "actual": actual_names[:50],
            })

        target_by_name = dict(targets)
        for sheet_name in expected_names:
            expected = _expected_cells(sheet_rows.get(sheet_name, []))
            expected_cell_count += len(expected)
            target = target_by_name.get(sheet_name)
            if not target:
                continue
            actual = _sheet_cells(archive.read(target))
            actual_cell_count += len(actual)
            for key in sorted(set(expected).union(actual)):
                if expected.get(key) != actual.get(key):
                    mismatch_count += 1
                    if len(mismatches) < MAX_REPORTED_MISMATCHES:
                        mismatches.append(_safe_detail(
                            sheet_name, key, expected.get(key), actual.get(key)))

    digest_builder = hashlib.sha256()
    with open(workbook_path, "rb") as workbook_file:
        while True:
            chunk = workbook_file.read(1024 * 1024)
            if not chunk:
                break
            digest_builder.update(chunk)
    digest = digest_builder.hexdigest()

    return {
        "schema": VALIDATION_SCHEMA,
        "ok": mismatch_count == 0,
        "validated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "document_title": str(document_title or "")[:250],
        "workbook_name": os.path.basename(workbook_path)[:250],
        "workbook_sha256": digest,
        "export_format": str(export_format or "")[:50],
        "tool_version": str(tool_version or "")[:100],
        "expected_sheet_count": len(expected_names),
        "actual_sheet_count": len(actual_names),
        "expected_cell_count": expected_cell_count,
        "actual_cell_count": actual_cell_count,
        "mismatch_count": mismatch_count,
        "mismatches_truncated": mismatch_count > len(mismatches),
        "mismatches": mismatches[:MAX_REPORTED_MISMATCHES],
        "source": "Canonical in-memory rows derived from the active Revit document",
    }


def write_validation_report(report_path, report):
    """Atomically publish one bounded validation report."""
    if not report_path:
        return False
    directory = os.path.dirname(report_path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    payload = json.dumps(report, indent=2, sort_keys=True)
    if len(payload.encode("utf-8")) > 512 * 1024:
        raise ValueError("BOQ validation report exceeds the configured limit")
    temporary_path = report_path + ".tmp"
    with io.open(temporary_path, "w", encoding="utf-8") as report_file:
        report_file.write(payload)
    if os.path.exists(report_path):
        os.remove(report_path)
    os.rename(temporary_path, report_path)
    return True


def read_validation_report(report_path):
    """Read one locally generated report with the same bounded contract."""
    if not report_path or not os.path.isfile(report_path):
        raise IOError("BOQ validation report was not created")
    if os.path.getsize(report_path) > 512 * 1024:
        raise ValueError("BOQ validation report exceeds the configured limit")
    with io.open(report_path, "r", encoding="utf-8") as report_file:
        report = json.load(report_file)
    if report.get("schema") != VALIDATION_SCHEMA:
        raise ValueError("BOQ validation report schema is unsupported")
    return report
