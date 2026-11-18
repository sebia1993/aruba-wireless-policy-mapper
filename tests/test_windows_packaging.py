"""Exercise real PowerShell packaging behavior on the supported Windows shell."""
import subprocess
import sys
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
