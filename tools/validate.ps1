param(
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
Push-Location $repoRoot

try {
    if ($PythonExe) {
        if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
            throw "Python executable was not found: $PythonExe"
        }
        $resolvedPythonExe = (Resolve-Path -LiteralPath $PythonExe).Path
    } else {
        $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
        if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
            $resolvedPythonExe = (Resolve-Path -LiteralPath $venvPython).Path
        } else {
            $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
            if (-not $pythonCommand) {
                throw "Python was not found. Create .venv or pass -PythonExe."
            }
            $resolvedPythonExe = $pythonCommand.Source
        }
    }

    $srcPath = Join-Path $repoRoot "src"
    if ($env:PYTHONPATH) {
        $env:PYTHONPATH = "$srcPath;$env:PYTHONPATH"
    } else {
        $env:PYTHONPATH = "$srcPath"
    }

    Write-Host "Python: $resolvedPythonExe"
    Write-Host "[1/4] pytest"
    & $resolvedPythonExe -m pytest -q
    if ($LASTEXITCODE -ne 0) {
        throw "pytest failed with exit code $LASTEXITCODE."
    }

    Write-Host "[2/4] compileall"
    & $resolvedPythonExe -m compileall -q app.py src tests tools
    if ($LASTEXITCODE -ne 0) {
        throw "compileall failed with exit code $LASTEXITCODE."
    }

    Write-Host "[3/4] Access Check JavaScript syntax"
    $node = Get-Command node -ErrorAction SilentlyContinue
    if ($node) {
        $tempAccessScript = Join-Path ([System.IO.Path]::GetTempPath()) "wlc_access_check_script.js"
        $tempRoleImageScript = Join-Path ([System.IO.Path]::GetTempPath()) "wlc_role_image_export_script.js"
        try {
            & $resolvedPythonExe -c "from pathlib import Path; import sys; from wlc_role_acl_collector.report import _access_check_script; Path(sys.argv[1]).write_text(_access_check_script(), encoding='utf-8')" $tempAccessScript
            if ($LASTEXITCODE -ne 0) {
                throw "Access Check JavaScript extraction failed with exit code $LASTEXITCODE."
            }
            node --check $tempAccessScript
            if ($LASTEXITCODE -ne 0) {
                throw "Access Check JavaScript syntax check failed with exit code $LASTEXITCODE."
            }

            Write-Host "[4/4] Role PNG JavaScript syntax"
            & $resolvedPythonExe -c "from pathlib import Path; import sys; from wlc_role_acl_collector.report import _role_image_export_script; Path(sys.argv[1]).write_text(_role_image_export_script(), encoding='utf-8')" $tempRoleImageScript
            if ($LASTEXITCODE -ne 0) {
                throw "Role PNG JavaScript extraction failed with exit code $LASTEXITCODE."
            }
            node --check $tempRoleImageScript
            if ($LASTEXITCODE -ne 0) {
                throw "Role PNG JavaScript syntax check failed with exit code $LASTEXITCODE."
            }
        } finally {
            foreach ($tempScript in @($tempAccessScript, $tempRoleImageScript)) {
                if (Test-Path -LiteralPath $tempScript) {
                    Remove-Item -LiteralPath $tempScript -Force
                }
            }
        }
    } else {
        Write-Host "[4/4] Role PNG JavaScript syntax"
        Write-Warning "Node.js was not found. Skipping JavaScript syntax check."
    }

    Write-Host "Validation completed."
} finally {
    Pop-Location
}
