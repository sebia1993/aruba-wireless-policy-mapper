"""Read the actual offline browser export with an independent XLSX consumer."""
import json
import shutil
import subprocess
from pathlib import Path

import openpyxl
import pytest


STATIC = Path(__file__).resolve().parents[1] / "src/wlc_role_acl_collector/static"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is required for browser XLSX export")
def test_exported_xlsx_preserves_literal_notes_scope_and_utf16_continuations(tmp_path):
    # A split through the emoji would corrupt the note; a missing continuation
    # would discard its final Korean line. Read real bytes with openpyxl.
    long_note = "한" * 32766 + "😀" + "\n=1+1 끝"
    annotation = {
        "text": long_note,
        "status": "needs_review",
        "updatedAt": "2026-11-16T12:00:00Z",
        "confirmedAt": None,
        "reasons": ["순서 변경"],
        "source": None,
    }
    model = {
        "projectId": "=project-id",
        "snapshotId": "snapshot-a",
        "revision": 2,
        "collectedAt": "2026-11-16T10:00:00Z",
        "updatedAt": "2026-11-16T12:00:00Z",
        "exportedAt": "2026-11-16T13:00:00Z",
        "scopeLabel": "선택한 역할",
        "summary": {"controllerCount": 1, "roleCount": 1, "ruleCount": 1, "annotatedRuleCount": 1, "needsReviewCount": 1},
        "controllers": [{"id": "ctrl-a", "name": "컨트롤러", "coverage": "partial", "failedCommands": ["show rights"]}],
        "roles": [{"id": "role-a", "controllerId": "ctrl-a", "name": "선택 역할", "annotation": {**annotation, "text": "=1+1"}}],
        "rules": [{"id": "rule-a", "controllerId": "ctrl-a", "roleId": "role-a", "raw": "any any any permit", "annotation": annotation}],
        "aliases": [{"id": "alias-a", "controllerId": "ctrl-a", "name": "alias", "entries": [{"type": "host", "value": "+1+1", "raw": long_note}]}],
        "changes": [], "unresolvedAnnotations": [], "localNetworks": [], "issues": [],
    }
    output = tmp_path / "offline.xlsx"
    script = """
const fs = require('node:fs');
const exporter = require(process.argv[1] + '/annotation_export.js');
const ExcelJS = require(process.argv[1] + '/exceljs.min.js');
const model = JSON.parse(fs.readFileSync(0, 'utf8'));
exporter.workbookBytes(model, ExcelJS).then(bytes => fs.writeFileSync(process.argv[2], bytes)).catch(error => { console.error(error); process.exitCode = 1; });
"""
    subprocess.run(["node", "-e", script, str(STATIC), str(output)], input=json.dumps(model), text=True, capture_output=True, check=True)
    workbook = openpyxl.load_workbook(output, data_only=False)
    assert workbook.sheetnames == ["보고 요약", "Role 설명", "ACL 상세", "변경·확인 사항", "Alias 상세"]
    for sheet in workbook:
        assert sheet.freeze_panes == "A2"
        assert sheet.auto_filter.ref
        for row in sheet:
            for cell in row:
                assert cell.data_type != "f"
                if isinstance(cell.value, str):
                    assert len(cell.value.encode("utf-16-le")) // 2 <= 32767
    roles = workbook["Role 설명"]
    headers = [cell.value for cell in roles[1]]
    assert roles.cell(2, headers.index("주석") + 1).value == "=1+1"
    rules = workbook["ACL 상세"]
    headers = [cell.value for cell in rules[1]]
    note_column = headers.index("주석") + 1
    assert "".join(rules.cell(row, note_column).value or "" for row in range(2, rules.max_row + 1)) == long_note
    aliases = workbook["Alias 상세"]
    alias_headers = [cell.value for cell in aliases[1]]
    raw_column = alias_headers.index("원문") + 1
    assert "".join(aliases.cell(row, raw_column).value or "" for row in range(2, aliases.max_row + 1)) == long_note
    assert aliases.cell(2, alias_headers.index("값") + 1).value == "+1+1"
    summary_values = "\n".join(str(cell.value or "") for row in workbook["보고 요약"] for cell in row)
    assert "=project-id" in summary_values
    assert "partial" in summary_values
    assert "show rights" in summary_values
    assert "선택한 역할" in summary_values
