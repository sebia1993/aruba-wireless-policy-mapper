import hashlib
import runpy
import subprocess
import sys
import zipfile
from pathlib import Path


def _write_fixture_zip(path: Path, entries: list[str]) -> str:
    with zipfile.ZipFile(path, "w") as archive:
        for entry in entries:
            archive.writestr(entry, "fixture")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_validate_script_runs_local_checks():
    script = Path(__file__).parents[1] / "tools" / "validate.ps1"
    text = script.read_text(encoding="utf-8")

    assert '[string]$PythonExe = ""' in text
    assert ".venv\\Scripts\\python.exe" in text
    assert "& $resolvedPythonExe -m pytest -q" in text
    assert "& $resolvedPythonExe -m compileall -q app.py src tests tools" in text
    assert "& $resolvedPythonExe -m pip check" in text
    assert text.count("-m pip_audit") == 2
    assert text.count("--ignore-vuln CVE-2026-44405") == 2
    assert "node --check" in text
    assert "_role_image_export_script" in text
    assert "Path(sys.argv[1]).write_text" in text
    assert "Set-Content -LiteralPath $tempAccessScript" not in text
    assert "Node.js was not found. Skipping JavaScript syntax check." in text


def test_release_zip_includes_guides():
    repo_root = Path(__file__).parents[1]
    script = repo_root / "build_windows_gui_exe.ps1"
    spec = repo_root / "WlcRoleAclCollectorGUI.spec"
    text = script.read_text(encoding="utf-8")
    spec_text = spec.read_text(encoding="utf-8")

    for expected in (
        "WlcRoleAclCollectorGUI",
        "WlcRoleAclCollectorCLI",
        "--collect-data customtkinter",
        ".\\cli_launcher.py",
        "tools\\generate_doc_html.py",
        "docs\\USER_GUIDE_KO.md",
        "docs\\USER_GUIDE_KO.html",
        "docs\\DEVELOPER_GUIDE_KO.md",
        "docs\\DEVELOPER_GUIDE_KO.html",
        "docs\\ERROR_CODES_KO.md",
        "docs\\ERROR_CODES_KO.html",
        "docs\\DIAGNOSTIC_MODE_KO.md",
        "docs\\DIAGNOSTIC_MODE_KO.html",
        "docs\\SECURITY_MODEL_KO.md",
        "docs\\SECURITY_MODEL_KO.html",
        "docs\\DEPENDENCY_AUDIT_EXCEPTIONS_KO.md",
        "docs\\DEPENDENCY_AUDIT_EXCEPTIONS_KO.html",
        "config\\role_networks.example.xlsx",
        "config\\mock_scenarios",
    ):
        assert expected in text

    assert "collect_data_files('customtkinter')" in spec_text
    assert "collect_data_files('wlc_role_acl_collector')" in spec_text


def test_streamlit_portable_build_contract():
    repo_root = Path(__file__).parents[1]
    attributes = (repo_root / ".gitattributes").read_text(encoding="utf-8")
    build_script = (repo_root / "build_windows_streamlit_portable.ps1").read_text(encoding="utf-8")
    verifier = (repo_root / "tools" / "verify_streamlit_portable_package.py").read_text(encoding="utf-8")
    launcher = (repo_root / "packaging" / "streamlit_portable" / "start_webapp.cmd").read_text(encoding="utf-8")
    settings = (repo_root / "packaging" / "streamlit_portable" / "webapp_settings.cmd").read_text(encoding="utf-8")
    guide = (repo_root / "packaging" / "streamlit_portable" / "README_WEBAPP_KO.txt").read_text(
        encoding="utf-8"
    )

    for expected in (
        "python-$EmbeddedPythonVersion-embed-amd64.zip",
        "https://www.python.org/ftp/python/$EmbeddedPythonVersion",
        '"--target", $sitePackages, "-r", "requirements-web-lock.txt"',
        "WlcRoleAclCollectorWeb_v${version}.zip",
        "start_webapp.cmd --smoke",
        "unexpectedSmokeLines",
        "python.exe",
        "compileall",
        "Portable module precompile failed.",
        "app\\app.py",
        "config\\role_networks.example.xlsx",
        "Lib\\site-packages",
        "import site",
    ):
        assert expected in build_script

    assert "*.cmd text eol=crlf" in attributes

    for expected in (
        "start_webapp.cmd",
        "trust_host_key.cmd",
        "webapp_settings.cmd",
        "python/python.exe",
        "python/Lib/site-packages/streamlit/",
        "python/Lib/site-packages/wlc_role_acl_collector/",
        "STREAMLIT_PORTABLE_OK",
        "completed.stderr.strip()",
    ):
        assert expected in verifier
    assert "Get-FileHash" not in verifier

    for expected in (
        "--server.address",
        "--server.port",
        "--server.headless true",
        "--server.fileWatcherType none",
        "--server.runOnSave false",
        "--global.developmentMode false",
        "--client.toolbarMode minimal",
        "--browser.gatherUsageStats false",
        "--smoke",
        "chcp 65001 >nul",
        "STREAMLIT_PORTABLE_OK",
        "python\\python.exe",
    ):
        assert expected in launcher

    assert "WLC_WEB_ADDRESS=127.0.0.1" in launcher
    assert "WLC_WEB_ADDRESS" not in settings
    assert "WLC_WEB_PORT=8763" in settings
    assert "Python을 별도로 설치하지 않고" in guide
    assert "첫 실행" in guide
    assert "start_webapp.cmd" in guide

    for batch_file in (
        repo_root / "packaging" / "streamlit_portable" / "start_webapp.cmd",
        repo_root / "packaging" / "streamlit_portable" / "trust_host_key.cmd",
        repo_root / "packaging" / "streamlit_portable" / "webapp_settings.cmd",
    ):
        data = batch_file.read_bytes()
        assert not data.startswith(b"\xef\xbb\xbf")
        assert all(index > 0 and data[index - 1] == 13 for index, byte in enumerate(data) if byte == 10)


def test_combined_release_build_contract():
    repo_root = Path(__file__).parents[1]
    build_script = (repo_root / "build_windows_combined_release.ps1").read_text(encoding="utf-8")
    verifier = (repo_root / "tools" / "verify_combined_release_package.py").read_text(encoding="utf-8")
    readme = (repo_root / "packaging" / "combined_release" / "README_START_HERE_KO.txt").read_text(
        encoding="utf-8"
    )

    for expected in (
        "WlcRoleAclCollectorGUI_*.zip",
        "WlcRoleAclCollectorWeb_*.zip",
        "WlcRoleAclCollectorWindows_v${version}.zip",
        "README_START_HERE_KO.txt",
        '"gui"',
        '"web"',
    ):
        assert expected in build_script

    for expected in (
        "gui/WlcRoleAclCollectorGUI.exe",
        "gui/WlcRoleAclCollectorCLI.exe",
        "web/start_webapp.cmd",
        "web/trust_host_key.cmd",
        "web/python/python.exe",
        "web/python/Lib/site-packages/streamlit/",
        "web/python/Lib/site-packages/wlc_role_acl_collector/",
        "--expected-sha256",
        "STREAMLIT_PORTABLE_OK",
    ):
        assert expected in verifier

    assert "Source code" in readme
    assert "gui\\WlcRoleAclCollectorGUI.exe" in readme
    assert "web\\start_webapp.cmd" in readme


def test_verify_release_package_checks_zip_contents_and_checksum(tmp_path):
    repo_root = Path(__file__).parents[1]
    script = repo_root / "tools" / "verify_release_package.py"
    zip_path = tmp_path / "WlcRoleAclCollectorGUI_v0.1.0.zip"
    entries = [
        "WlcRoleAclCollectorGUI.exe",
        "WlcRoleAclCollectorCLI.exe",
        "USER_GUIDE_KO.md",
        "USER_GUIDE_KO.html",
        "DEVELOPER_GUIDE_KO.md",
        "DEVELOPER_GUIDE_KO.html",
        "ERROR_CODES_KO.md",
        "ERROR_CODES_KO.html",
        "DIAGNOSTIC_MODE_KO.md",
        "DIAGNOSTIC_MODE_KO.html",
        "SECURITY_MODEL_KO.md",
        "SECURITY_MODEL_KO.html",
        "DEPENDENCY_AUDIT_EXCEPTIONS_KO.md",
        "DEPENDENCY_AUDIT_EXCEPTIONS_KO.html",
        "config/role_networks.example.xlsx",
        "config/mock_scenarios/auth_failed.json",
        "config/mock_scenarios/missing_config.json",
        "config/mock_scenarios/permission_denied.json",
        "config/mock_scenarios/success_minimal.json",
    ]
    digest = _write_fixture_zip(zip_path, entries)
    checksum_path = tmp_path / f"{zip_path.name}.sha256"
    checksum_path.write_text(f"{digest}  {zip_path.name}\n", encoding="ascii")

    subprocess.run(
        [sys.executable, str(script), "--zip", str(zip_path), "--sha256", str(checksum_path)],
        check=True,
        cwd=repo_root,
    )


def test_verify_release_package_auto_selects_only_gui_zip(tmp_path):
    script = Path(__file__).parents[1] / "tools" / "verify_release_package.py"
    gui_zip = tmp_path / "WlcRoleAclCollectorGUI_v0.1.0.zip"
    combined_zip = tmp_path / "WlcRoleAclCollectorWindows_v0.1.0.zip"
    gui_zip.write_bytes(b"gui")
    combined_zip.write_bytes(b"newer combined")

    namespace = runpy.run_path(str(script))
    assert namespace["_find_latest_zip"](tmp_path) == gui_zip


def test_verify_streamlit_portable_package_checks_zip_contents_and_checksum(tmp_path):
    repo_root = Path(__file__).parents[1]
    script = repo_root / "tools" / "verify_streamlit_portable_package.py"
    zip_path = tmp_path / "WlcRoleAclCollectorWeb_v0.1.0.zip"
    entries = [
        "start_webapp.cmd",
        "trust_host_key.cmd",
        "webapp_settings.cmd",
        "README_WEBAPP_KO.txt",
        "python/python.exe",
        "python/Lib/site-packages/streamlit/__init__.py",
        "python/Lib/site-packages/wlc_role_acl_collector/__init__.py",
        "app/app.py",
        "config/role_networks.example.xlsx",
    ]
    digest = _write_fixture_zip(zip_path, entries)
    checksum_path = tmp_path / f"{zip_path.name}.sha256"
    checksum_path.write_text(f"{digest}  {zip_path.name}\n", encoding="ascii")

    subprocess.run(
        [sys.executable, str(script), "--zip", str(zip_path), "--sha256", str(checksum_path)],
        check=True,
        cwd=repo_root,
    )


def test_verify_combined_release_package_checks_zip_contents_and_checksum(tmp_path):
    repo_root = Path(__file__).parents[1]
    script = repo_root / "tools" / "verify_combined_release_package.py"
    zip_path = tmp_path / "WlcRoleAclCollectorWindows_v0.1.0.zip"
    entries = [
        "README_START_HERE_KO.txt",
        "gui/WlcRoleAclCollectorGUI.exe",
        "gui/WlcRoleAclCollectorCLI.exe",
        "gui/USER_GUIDE_KO.md",
        "gui/USER_GUIDE_KO.html",
        "gui/DEVELOPER_GUIDE_KO.md",
        "gui/DEVELOPER_GUIDE_KO.html",
        "gui/ERROR_CODES_KO.md",
        "gui/ERROR_CODES_KO.html",
        "gui/DIAGNOSTIC_MODE_KO.md",
        "gui/DIAGNOSTIC_MODE_KO.html",
        "gui/SECURITY_MODEL_KO.md",
        "gui/SECURITY_MODEL_KO.html",
        "gui/DEPENDENCY_AUDIT_EXCEPTIONS_KO.md",
        "gui/DEPENDENCY_AUDIT_EXCEPTIONS_KO.html",
        "gui/config/role_networks.example.xlsx",
        "gui/config/mock_scenarios/auth_failed.json",
        "gui/config/mock_scenarios/missing_config.json",
        "gui/config/mock_scenarios/permission_denied.json",
        "gui/config/mock_scenarios/success_minimal.json",
        "web/start_webapp.cmd",
        "web/trust_host_key.cmd",
        "web/webapp_settings.cmd",
        "web/README_WEBAPP_KO.txt",
        "web/python/python.exe",
        "web/python/Lib/site-packages/streamlit/__init__.py",
        "web/python/Lib/site-packages/wlc_role_acl_collector/__init__.py",
        "web/app/app.py",
        "web/config/role_networks.example.xlsx",
    ]
    digest = _write_fixture_zip(zip_path, entries)

    subprocess.run(
        [sys.executable, str(script), "--zip", str(zip_path), "--expected-sha256", digest],
        check=True,
        cwd=repo_root,
    )


def test_release_documentation_describes_current_package_contract():
    repo_root = Path(__file__).parents[1]
    app = (repo_root / "app.py").read_text(encoding="utf-8")
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    release_notes = (repo_root / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    changelog = (repo_root / "CHANGELOG.md").read_text(encoding="utf-8")
    development = (repo_root / "DEVELOPMENT.md").read_text(encoding="utf-8")
    validation_report = (repo_root / "docs" / "VALIDATION_REPORT.md").read_text(encoding="utf-8")
    requirements = (repo_root / "requirements.txt").read_text(encoding="utf-8")
    requirements_lock = (repo_root / "requirements-lock.txt").read_text(encoding="utf-8")
    web_lock = (repo_root / "requirements-web-lock.txt").read_text(encoding="utf-8")

    for text in (readme, release_notes):
        assert "wlc-role-acl-collector_v0.2.0_windows.zip" in text
        assert "WlcRoleAclCollectorGUI.exe" in text
        assert "WlcRoleAclCollectorCLI.exe" in text
        assert "start_webapp.cmd" in text
        assert "trust_host_key.cmd" in text
        assert "README_START_HERE_KO.txt" in text
        assert "Source code (zip)" in text

    assert "wlc-role-acl-collector_v0.2.0_windows.zip.sha256" in release_notes
    assert "wlc-role-acl-collector_v0.2.0_sbom.cdx.json" in release_notes

    assert "SSID → AAA Profile → 기본 Role → ACL → Alias" in readme
    assert "Access Check" in readme
    assert "http://127.0.0.1:8763" in readme
    assert "DEVELOPMENT.md" in readme
    assert "VALIDATION_REPORT.md" in readme
    assert "config/mock_scenarios" in development
    assert "python .\\tools\\verify_release_package.py --dist .\\dist --smoke-cli" in development
    assert "python .\\tools\\verify_streamlit_portable_package.py --dist .\\dist --smoke" in development
    assert "python .\\tools\\verify_combined_release_package.py --dist .\\dist --smoke" in development
    assert "GitHub Actions" in development and "Windows" in development
    assert "60 Role / 1,200 ACL" in validation_report
    assert "100 Role / 4,000 ACL" in validation_report
    assert "실제 운영 환경 검증" in validation_report
    assert "ClearPass/RADIUS 서버의 동적 Role 직접 조회" in changelog
    assert "코드서명 / installer / MSIX" in changelog
    assert "--require-hashes" in requirements
    assert "-r requirements-lock.txt" in requirements
    assert "--hash=sha256:" in requirements_lock
    assert "--hash=sha256:" in web_lock
    assert "st.file_uploader" in app
    assert "st.download_button" in app


def test_generate_doc_html_outputs_browser_files(tmp_path):
    repo_root = Path(__file__).parents[1]
    script = repo_root / "tools" / "generate_doc_html.py"

    subprocess.run(
        [sys.executable, str(script), "--source-dir", str(repo_root / "docs"), "--output-dir", str(tmp_path)],
        check=True,
        cwd=repo_root,
    )

    user_html = (tmp_path / "USER_GUIDE_KO.html").read_text(encoding="utf-8")
    developer_html = (tmp_path / "DEVELOPER_GUIDE_KO.html").read_text(encoding="utf-8")
    error_codes_html = (tmp_path / "ERROR_CODES_KO.html").read_text(encoding="utf-8")
    diagnostic_html = (tmp_path / "DIAGNOSTIC_MODE_KO.html").read_text(encoding="utf-8")
    security_html = (tmp_path / "SECURITY_MODEL_KO.html").read_text(encoding="utf-8")
    dependency_audit_html = (tmp_path / "DEPENDENCY_AUDIT_EXCEPTIONS_KO.html").read_text(encoding="utf-8")

    assert user_html == (repo_root / "docs" / "USER_GUIDE_KO.html").read_text(encoding="utf-8")
    assert developer_html == (repo_root / "docs" / "DEVELOPER_GUIDE_KO.html").read_text(encoding="utf-8")
    assert error_codes_html == (repo_root / "docs" / "ERROR_CODES_KO.html").read_text(encoding="utf-8")
    assert diagnostic_html == (repo_root / "docs" / "DIAGNOSTIC_MODE_KO.html").read_text(encoding="utf-8")
    assert security_html == (repo_root / "docs" / "SECURITY_MODEL_KO.html").read_text(encoding="utf-8")
    assert dependency_audit_html == (repo_root / "docs" / "DEPENDENCY_AUDIT_EXCEPTIONS_KO.html").read_text(
        encoding="utf-8"
    )
    assert "<!doctype html>" in user_html
    assert '<html lang="ko">' in user_html
    assert "WLC Role ACL Collector 사용자 설명서" in user_html
    assert "<table>" in user_html
    assert 'class="table-scroll" role="region" tabindex="0"' in user_html
    assert "overflow-wrap: anywhere;" in user_html
    assert "@media (max-width: 600px)" in user_html
    assert "WLC Role ACL Collector 개발자 설명서" in developer_html
    assert "WLC Role ACL Collector 오류 코드" in error_codes_html
    assert "WLC Role ACL Collector 진단 모드" in diagnostic_html
    assert "WLC Role ACL Collector 보안 모델" in security_html
    assert "WLC Role ACL Collector 의존성 감사 예외" in dependency_audit_html
    assert "Generated from Markdown for browser viewing." in developer_html


def test_github_actions_validate_main_and_publish_versioned_release():
    repo_root = Path(__file__).parents[1]
    pr_workflow = (repo_root / ".github" / "workflows" / "pr-validation.yml").read_text(encoding="utf-8")
    release_workflow = (repo_root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    validation_command = "powershell -NoProfile -ExecutionPolicy Bypass -File .\\tools\\validate.ps1"
    build_command = "powershell -NoProfile -ExecutionPolicy Bypass -File .\\build_windows_gui_exe.ps1"
    web_build_command = "powershell -NoProfile -ExecutionPolicy Bypass -File .\\build_windows_streamlit_portable.ps1"
    web_verify_command = "python .\\tools\\verify_streamlit_portable_package.py --dist .\\dist --smoke"
    combined_build_command = "powershell -NoProfile -ExecutionPolicy Bypass -File .\\build_windows_combined_release.ps1"
    combined_verify_command = "python .\\tools\\verify_combined_release_package.py --dist .\\dist --smoke"

    assert "pull_request:" in pr_workflow
    assert "push:" in pr_workflow
    assert "branches: [main]" in pr_workflow
    assert "contents: read" in pr_workflow
    assert "--require-hashes -r requirements-lock.txt" in pr_workflow
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in pr_workflow
    assert "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" in pr_workflow
    assert validation_command in pr_workflow
    assert build_command in pr_workflow
    assert "python .\\tools\\verify_release_package.py --dist .\\dist --smoke-cli" in pr_workflow
    assert web_build_command in pr_workflow
    assert web_verify_command in pr_workflow
    assert combined_build_command in pr_workflow
    assert combined_verify_command in pr_workflow
    assert "gh release" not in pr_workflow

    assert "workflow_dispatch:" in release_workflow
    assert "push:" not in release_workflow
    assert "pull_request:" not in release_workflow
    assert "github.ref == 'refs/heads/main'" in release_workflow
    assert "permissions:\n  contents: read" in release_workflow
    assert "contents: write" in release_workflow
    assert "attestations: write" in release_workflow
    assert "id-token: write" in release_workflow
    assert "Korea Standard Time" not in release_workflow
    assert "['project']['version']" in release_workflow
    assert "Tag already exists and will not be replaced" in release_workflow
    assert validation_command in release_workflow
    assert build_command in release_workflow
    assert web_build_command in release_workflow
    assert combined_build_command in release_workflow
    assert "python .\\tools\\verify_release_package.py --dist .\\dist --smoke-cli" in release_workflow
    assert web_verify_command in release_workflow
    assert combined_verify_command in release_workflow
    assert "WlcRoleAclCollectorWindows_v${{ steps.metadata.outputs.version }}.zip" in release_workflow
    assert "Get-FileHash -Algorithm SHA256" in release_workflow
    assert "cyclonedx-py requirements requirements-web-lock.txt" in release_workflow
    assert "actions/attest-build-provenance@4d101475d8b20a2381f78447822ac1eab6504dd8" in release_workflow
    assert "git tag -a" in release_workflow
    assert 'git push origin "refs/tags/' in release_workflow
    assert "gh release create" in release_workflow
    assert "--verify-tag" in release_workflow
    assert 'git push origin ":refs/tags/' in release_workflow

    assert "## 이번 릴리즈" in release_workflow
    assert "## 운영 영향" in release_workflow
    assert "## 검증 결과" in release_workflow
    assert "- 기준 커밋: ${{ github.sha }}" in release_workflow
    assert "## 다운로드" in release_workflow
    assert "checksum_name" in release_workflow
    assert "sbom_name" in release_workflow
    assert "## 알려진 범위" in release_workflow


def test_runtime_dependencies_include_customtkinter():
    repo_root = Path(__file__).parents[1]
    pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    renderer = repo_root / "src" / "wlc_role_acl_collector" / "static" / "html2canvas.min.js"
    license_file = repo_root / "src" / "wlc_role_acl_collector" / "static" / "LICENSE.html2canvas.txt"

    assert '"customtkinter>=5.2"' in pyproject
    assert '"streamlit>=1.36"' in pyproject
    assert "[tool.setuptools.package-data]" in pyproject
    assert '"static/*.js"' in pyproject
    assert '"static/*.txt"' in pyproject
    assert renderer.stat().st_size > 190_000
    assert "Permission is hereby granted, free of charge" in license_file.read_text(encoding="utf-8")
