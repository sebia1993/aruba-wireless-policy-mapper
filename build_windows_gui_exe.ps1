param(
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
. (Join-Path $PSScriptRoot "tools\windows_packaging.ps1")

Write-Host "Installing runtime and build dependencies..."
& $PythonExe -m pip install --require-hashes -r requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw "Locked dependency installation failed." }
& $PythonExe -m pip install --no-deps --no-build-isolation -e .
if ($LASTEXITCODE -ne 0) { throw "Project installation failed." }

Write-Host "Generating HTML guide documents..."
& $PythonExe ".\tools\generate_doc_html.py"

$version = & $PythonExe -c "from wlc_role_acl_collector import __version__; print(__version__)"
$guiExeName = "WlcRoleAclCollectorGUI"
$distDir = Join-Path $PSScriptRoot "dist"
$buildRoot = Join-Path $PSScriptRoot ".pyinstaller_build"
$buildDir = Join-Path $buildRoot ([DateTime]::Now.ToString("yyyyMMdd_HHmmss"))
$specDir = Join-Path $buildDir "spec"
$releaseRoot = Join-Path $buildDir "release"
$distGuiExe = Join-Path $distDir "$guiExeName.exe"
$deprecatedCliExe = Join-Path $distDir "WlcRoleAclCollectorCLI.exe"
$releaseZip = Join-Path $distDir "${guiExeName}_v${version}.zip"
$roleNetworkTemplate = Join-Path $PSScriptRoot "config\role_networks.example.xlsx"
$userGuide = Join-Path $PSScriptRoot "docs\USER_GUIDE_KO.md"
$userGuideHtml = Join-Path $PSScriptRoot "docs\USER_GUIDE_KO.html"
$developerGuide = Join-Path $PSScriptRoot "docs\DEVELOPER_GUIDE_KO.md"
$developerGuideHtml = Join-Path $PSScriptRoot "docs\DEVELOPER_GUIDE_KO.html"
$errorCodesGuide = Join-Path $PSScriptRoot "docs\ERROR_CODES_KO.md"
$errorCodesGuideHtml = Join-Path $PSScriptRoot "docs\ERROR_CODES_KO.html"
$diagnosticModeGuide = Join-Path $PSScriptRoot "docs\DIAGNOSTIC_MODE_KO.md"
$diagnosticModeGuideHtml = Join-Path $PSScriptRoot "docs\DIAGNOSTIC_MODE_KO.html"
$securityModelGuide = Join-Path $PSScriptRoot "docs\SECURITY_MODEL_KO.md"
$securityModelGuideHtml = Join-Path $PSScriptRoot "docs\SECURITY_MODEL_KO.html"
$dependencyAuditGuide = Join-Path $PSScriptRoot "docs\DEPENDENCY_AUDIT_EXCEPTIONS_KO.md"
$dependencyAuditGuideHtml = Join-Path $PSScriptRoot "docs\DEPENDENCY_AUDIT_EXCEPTIONS_KO.html"
$mockScenarioDir = Join-Path $PSScriptRoot "config\mock_scenarios"

[System.IO.Directory]::CreateDirectory($distDir) | Out-Null
[System.IO.Directory]::CreateDirectory($specDir) | Out-Null
[System.IO.Directory]::CreateDirectory($releaseRoot) | Out-Null

if (Test-Path -LiteralPath $distGuiExe) {
    Remove-Item -LiteralPath $distGuiExe -Force
}
# Remove an executable left behind by an older CLI-enabled build.
if (Test-Path -LiteralPath $deprecatedCliExe) {
    Remove-Item -LiteralPath $deprecatedCliExe -Force
}
if (Test-Path -LiteralPath $releaseZip) {
    Remove-Item -LiteralPath $releaseZip -Force
}

Write-Host "Building Windows GUI executable..."
& $PythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name $guiExeName `
    --distpath $distDir `
    --workpath $buildDir `
    --specpath $specDir `
    --collect-data customtkinter `
    --collect-data wlc_role_acl_collector `
    --paths ".\src" `
    ".\gui_launcher.py"

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

Write-Host "Creating release zip..."
Copy-ReadableFileWithRetry -LiteralPath $distGuiExe -Destination $releaseRoot
Copy-Item -LiteralPath $userGuide -Destination (Join-Path $releaseRoot "USER_GUIDE_KO.md") -Force
Copy-Item -LiteralPath $userGuideHtml -Destination (Join-Path $releaseRoot "USER_GUIDE_KO.html") -Force
Copy-Item -LiteralPath $developerGuide -Destination (Join-Path $releaseRoot "DEVELOPER_GUIDE_KO.md") -Force
Copy-Item -LiteralPath $developerGuideHtml -Destination (Join-Path $releaseRoot "DEVELOPER_GUIDE_KO.html") -Force
Copy-Item -LiteralPath $errorCodesGuide -Destination (Join-Path $releaseRoot "ERROR_CODES_KO.md") -Force
Copy-Item -LiteralPath $errorCodesGuideHtml -Destination (Join-Path $releaseRoot "ERROR_CODES_KO.html") -Force
Copy-Item -LiteralPath $diagnosticModeGuide -Destination (Join-Path $releaseRoot "DIAGNOSTIC_MODE_KO.md") -Force
Copy-Item -LiteralPath $diagnosticModeGuideHtml -Destination (Join-Path $releaseRoot "DIAGNOSTIC_MODE_KO.html") -Force
Copy-Item -LiteralPath $securityModelGuide -Destination (Join-Path $releaseRoot "SECURITY_MODEL_KO.md") -Force
Copy-Item -LiteralPath $securityModelGuideHtml -Destination (Join-Path $releaseRoot "SECURITY_MODEL_KO.html") -Force
Copy-Item -LiteralPath $dependencyAuditGuide -Destination (Join-Path $releaseRoot "DEPENDENCY_AUDIT_EXCEPTIONS_KO.md") -Force
Copy-Item -LiteralPath $dependencyAuditGuideHtml -Destination (Join-Path $releaseRoot "DEPENDENCY_AUDIT_EXCEPTIONS_KO.html") -Force
[System.IO.Directory]::CreateDirectory((Join-Path $releaseRoot "config")) | Out-Null
Copy-Item -LiteralPath $roleNetworkTemplate -Destination (Join-Path $releaseRoot "config") -Force
Copy-Item -LiteralPath $mockScenarioDir -Destination (Join-Path $releaseRoot "config") -Recurse -Force
Get-ChildItem -LiteralPath $releaseRoot -Recurse -File | ForEach-Object {
    Wait-ForReadableFile -Path $_.FullName
}
Compress-ArchiveWithRetry -DirectoryPath $releaseRoot -DestinationPath $releaseZip

Write-Host ""
Write-Host "Build completed."
Write-Host "Build work directory: $buildDir"
Write-Host "GUI executable: $distGuiExe"
Write-Host "Release zip: $releaseZip"
