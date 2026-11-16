import json
import re
import subprocess

from wlc_role_acl_collector.acl_evaluator import build_access_check_data, evaluate_access
from wlc_role_acl_collector.annotation_project import controller_identity
from wlc_role_acl_collector.models import (
    AclRule, CollectionResult, CommandOutput, Controller, NetDestinationEntry,
    ParsedController, RoleNetworkContext, RolePolicy,
)
from wlc_role_acl_collector.report import _build_frames, _write_html, write_reports


def controllers():
    parsed_items, results = [], []
    for index in [1, 2]:
        controller = Controller("same", f"192.0.2.{index}")
        parsed = ParsedController(controller)
        parsed.role_policies["staff"] = RolePolicy(
            "same", "staff", ["staff"],
            [AclRule("same", "staff", 1, "any alias servers any permit", "permit", "any", "alias servers", "any")],
            raw_lines=["session-acl staff"],
        )
        parsed.netdestination_aliases["servers"] = [NetDestinationEntry("same", "servers", 1, "host", f"10.0.0.{index}", f"host 10.0.0.{index}")]
        parsed.role_network_contexts = [RoleNetworkContext("same", "staff", "", "", "", observed_user_count=index)]
        parsed_items.append(parsed)
        results.append(CollectionResult(controller, [CommandOutput("configuration_effective", "show configuration effective", output="policy"), CommandOutput("user_table", "show user-table", output="REDACT_ME")]))
    return parsed_items, results


def embedded_json(html, element_id):
    return json.loads(re.search(rf'<script[^>]*id="{element_id}"[^>]*>(.*?)</script>', html, re.S).group(1))


def test_frames_and_access_checks_isolate_same_names_by_endpoint(tmp_path):
    parsed_items, results = controllers()
    frames = _build_frames(parsed_items, results)
    ids = {controller_identity(item.controller) for item in parsed_items}
    for key in ["Overview", "Role_ACL_Detail", "Alias_Detail", "Role_Network_Context", "Raw_Commands"]:
        assert set(frames[key]["controller_id"]) == ids
    path = tmp_path / "scoped.html"
    _write_html(path, frames)
    html = path.read_text(encoding="utf-8")
    data = embedded_json(html, "access-check-data")
    assert len(data["roles"]) == 2
    assert len({role["key"] for role in data["roles"]}) == 2
    assert {role["userCount"] for role in data["roles"]} == {1, 2}
    assert len({rule["id"] for role in data["roles"] for rule in role["rules"]}) == 2
    for role in data["roles"]:
        index = next(i for i, item in enumerate(parsed_items, 1) if controller_identity(item.controller) == role["controllerId"])
        own = evaluate_access(data, role=role["key"], source_ip="10.1.1.1", destination_ip=f"10.0.0.{index}")
        other = evaluate_access(data, role=role["key"], source_ip="10.1.1.1", destination_ip=f"10.0.0.{3-index}")
        assert own["status"] == "allowed"
        assert other["verdict"] == "기본 차단(Implicit deny)"
    assert evaluate_access(data, role="staff", source_ip="10.1.1.1", destination_ip="10.0.0.1")["status"] == "error"
    comment_ids = re.findall(r'class="comment-input" data-comment-id="([^"]+)"', html)
    assert len(comment_ids) == len(set(comment_ids)) == 2
    assert "192.0.2.1" in html and "192.0.2.2" in html


def test_access_data_scopes_alias_and_local_network_rows_without_html():
    items = [{"role": "staff", "role_key": f"role-{index}", "controller_id": f"controller-{index}", "controller": "same", "rows": [{"acl": "staff", "source": "any", "destination": "alias servers", "service": "any", "action": "permit"}]} for index in [1, 2]]
    aliases = [{"controller_id": f"controller-{index}", "alias": "servers", "entry_type": "host", "value": f"10.0.0.{index}"} for index in [1, 2]]
    local = [{"controller_id": f"controller-{index}", "role": "staff", "local_role_network": f"10.{index}.0.0/16"} for index in [1, 2]]
    data = build_access_check_data(items, aliases, local)
    for index, role in enumerate(data["roles"], 1):
        assert role["key"] == f"role-{index}"
        assert [network["network"] for network in role["localNetworks"]] == [f"10.{index}.0.0/16"]
        assert len(role["rules"][0]["destinationMatchers"]) == 1


def test_access_data_assigns_scoped_keys_for_duplicate_roles_without_explicit_keys():
    data = build_access_check_data(
        [{"role": "staff", "controller": name, "rows": [{"acl": "staff", "source": "any", "destination": "any", "service": "any", "action": "permit"}]} for name in ["first", "second"]],
        [], [],
    )
    keys = [role["key"] for role in data["roles"]]
    assert len(set(keys)) == 2
    assert "staff" not in keys
    assert evaluate_access(data, role="staff", source_ip="10.0.0.1", destination_ip="10.0.0.2")["status"] == "error"


def test_report_embeds_complete_scoped_project_and_offline_editor(tmp_path):
    parsed_items, results = controllers()
    paths = write_reports(parsed_controllers=parsed_items, collection_results=results, output_dir=tmp_path)
    html = paths["html"].read_text(encoding="utf-8")
    project = embedded_json(html, "annotation-project-data")
    assert {c["host"] for c in project["snapshot"]["controllers"]} == {"192.0.2.1", "192.0.2.2"}
    assert all(c["identityKnown"] for c in project["snapshot"]["controllers"])
    assert "REDACT_ME" not in json.dumps(project)
    assert f'id="source-report" hidden data-source-snapshot-id="{project["snapshot"]["id"]}"' in html
    assert html.index('id="annotation-workspace"') < html.index('id="source-report"')
    script_ids = re.findall(r'<script\b[^>]*id="([^"]+)"', html)
    expected = ["annotation-core-script", "annotation-export-script", "annotation-import-script", "annotation-exceljs-script", "annotation-editor-script"]
    assert [item for item in script_ids if item in expected] == expected
    assert '<style id="annotation-editor-style">' in html
    assert 'class="comment-input" data-comment-id=' in html
    assert 'readonly' in html


def test_source_bridge_updates_only_matching_snapshot_and_preserves_empty_notes():
    from wlc_role_acl_collector.report import _source_annotation_bridge_script

    harness = r"""
const assert = require('node:assert/strict');
const input = {value:'old',textContent:'old',dataset:{commentId:'comment-1'}};
const description = {value:'old role',textContent:'old role',dataset:{role:'role-key',descriptionId:'desc-1'}};
const row = {dataset:{annotationOrdinal:'1'},querySelector:()=>input};
const panel = {dataset:{controllerId:'c',role:'staff'},querySelector:()=>description,querySelectorAll:()=>[row]};
const elements = {'#source-report':{dataset:{sourceSnapshotId:'s'}},'#acl-comments-data':{},'#role-descriptions-data':{}};
const byId = {'comment-1-print':{},'desc-1-print':{}};
global.window = {};
global.document = {querySelector:(key)=>elements[key]||{addEventListener(){}},querySelectorAll:(key)=>key==='.comment-input'?[input]:key==='.role-description-input'?[description]:key==='.role-panel'?[panel]:[],getElementById:(key)=>byId[key]};
"""
    assertions = r"""
const project = {snapshot:{id:'s',controllers:[{id:'c',name:'same'}],roles:[{id:'r',controllerId:'c',name:'staff'}],rules:[{id:'q',roleId:'r',ordinal:1}]},annotations:{roles:{r:{text:''}},rules:{q:{text:'new rule'}}}};
window.syncSourceAnnotations({...project,snapshot:{...project.snapshot,id:'other'}});
assert.equal(input.value,'old');
window.syncSourceAnnotations(project);
assert.equal(input.value,'new rule');
assert.equal(description.value,'');
assert.equal(byId['comment-1-print'].textContent,'new rule');
assert.equal(byId['desc-1-print'].textContent,'');
project.annotations.rules.q.text='';
window.syncSourceAnnotations(project);
assert.equal(input.value,'');
assert.equal(JSON.parse(elements['#acl-comments-data'].value)['comment-1'],'');
"""
    completed = subprocess.run(["node", "-e", harness + _source_annotation_bridge_script() + assertions], capture_output=True, text=True, encoding="utf-8")
    assert completed.returncode == 0, completed.stderr


def test_generated_html_runs_editor_and_syncs_source_without_cross_controller_notes(tmp_path):
    parsed_items, results = controllers()
    path = write_reports(parsed_controllers=parsed_items, collection_results=results, output_dir=tmp_path)["html"]
    script = r"""
const fs = require('node:fs');
const assert = require('node:assert/strict');
const {JSDOM, VirtualConsole} = require('jsdom');
const errors = [];
const virtualConsole = new VirtualConsole();
virtualConsole.on('jsdomError', error => errors.push(error.message));
const dom = new JSDOM(fs.readFileSync(0,'utf8'),{runScripts:'dangerously',url:'https://offline.test/report.html',virtualConsole});
const win = dom.window;
assert.equal(errors.length,0,errors.join('\n'));
assert.ok(win.AnnotationEditorApp);
const project = win.AnnotationEditorApp.getProject();
const rule = project.snapshot.rules[0];
const note = win.document.querySelector('[data-note-id="'+rule.id+'"]');
note.value = '한글 주석\n</script><script>window.PWNED=true</script>';
note.dispatchEvent(new win.Event('input',{bubbles:true}));
assert.equal(errors.length,0,errors.join('\n'));
const panels = Array.from(win.document.querySelectorAll('.role-panel'));
assert.equal(panels.length,2);
for (const panel of panels) {
  assert.equal(panel.querySelector('.comment-input').readOnly,true);
  assert.equal(panel.querySelector('.comment-input').value,panel.dataset.controllerId===rule.controllerId?note.value:'');
  const ownAlias = project.snapshot.aliases.find(alias=>alias.controllerId===panel.dataset.controllerId).entries[0].value;
  const otherAlias = project.snapshot.aliases.find(alias=>alias.controllerId!==panel.dataset.controllerId).entries[0].value;
  assert.ok(panel.querySelector('.alias-detail-row').textContent.includes(ownAlias));
  assert.ok(!panel.querySelector('.alias-detail-row').textContent.includes(otherAlias));
}
assert.equal(win.PWNED,undefined);
const saved = win.AnnotationEditor.standaloneHtml(win.AnnotationEditorApp.getProject(),win.document);
const reopened = new JSDOM(saved,{runScripts:'dangerously',url:'https://offline.test/saved.html',virtualConsole});
assert.equal(errors.length,0,errors.join('\n'));
assert.equal(reopened.window.AnnotationEditorApp.getProject().annotations.rules[rule.id].text,note.value);
assert.equal(reopened.window.document.getElementById('source-report'),null);
assert.equal(reopened.window.PWNED,undefined);
reopened.window.close();
win.close();
"""
    completed = subprocess.run(["node", "-e", script], input=path.read_text(encoding="utf-8"), capture_output=True, text=True, encoding="utf-8")
    assert completed.returncode == 0, completed.stderr


def test_initial_excel_preserves_formula_like_literals(tmp_path):
    import pandas as pd
    from openpyxl import load_workbook
    from wlc_role_acl_collector.report import _write_excel

    output = tmp_path / "literal.xlsx"
    _write_excel(output, {"Policy": pd.DataFrame([{"name": "=1+1", "ip": "001", "count": 2}])})
    book = load_workbook(output)
    assert book["Policy"]["A2"].value == "=1+1"
    assert book["Policy"]["A2"].data_type == "s"
    assert book["Policy"]["B2"].value == "001"
    assert book["Policy"]["C2"].value == 2


def test_windows_commands_collect_required_offline_editor_assets():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    text = (root / "build_windows_gui_exe.ps1").read_text(encoding="utf-8")
    commands = re.findall(r"& \$PythonExe -m PyInstaller.*?launcher\.py\"", text, flags=re.S)
    assert len(commands) == 2
    assert all("--collect-data wlc_role_acl_collector" in command for command in commands)
