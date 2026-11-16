"""Exercise real PowerShell packaging behavior on the supported Windows shell."""
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows PowerShell 5.1")
def test_windows_packaging_behavior():
    script = Path(__file__).parents[1] / "tools" / "test_windows_packaging.ps1"
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "WINDOWS_PACKAGING_TESTS_OK" in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows CMD")
def test_host_key_launcher_runs_validation_instead_of_silent_success(tmp_path):
    """Run the shipped CMD with a real Python runtime and an offline input."""
    root = Path(__file__).parents[1]
    shutil.copyfile(root / "packaging" / "streamlit_portable" / "trust_host_key.cmd", tmp_path / "trust_host_key.cmd")
    # A junction preserves Python's adjacent DLLs without copying the runtime.
    runtime = tmp_path / "python"
    linked = subprocess.run(
        ["cmd.exe", "/c", "mklink", "/J", str(runtime), sys.base_prefix],
        capture_output=True, text=True, timeout=10,
    )
    assert linked.returncode == 0, linked.stdout + linked.stderr
    try:
        # The base runtime also needs dependencies installed in pytest's virtualenv.
        package_paths = sysconfig.get_paths()
        python_path = os.pathsep.join(dict.fromkeys([
            str(root / "src"), package_paths["purelib"], package_paths["platlib"],
        ]))
        environment = dict(os.environ, PYTHONPATH=python_path, PYTHONIOENCODING="utf-8")
        completed = subprocess.run(
            ["cmd.exe", "/c", "trust_host_key.cmd", "invalid://host", "22"],
            cwd=tmp_path, env=environment, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        assert completed.returncode == 2, completed.stdout + completed.stderr
        assert "WLC IP" in completed.stderr and "URL" in completed.stderr
    finally:
        os.rmdir(runtime)
