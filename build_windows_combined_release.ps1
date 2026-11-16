param(
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
. (Join-Path $PSScriptRoot "tools\windows_packaging.ps1")

$version = (& $PythonExe -c "from wlc_role_acl_collector import __version__; print(__version__)").Trim()
if ($LASTEXITCODE -ne 0 -or -not $version) {
    throw "Failed to read project version."
}

$distDir = Join-Path $PSScriptRoot "dist"
$buildRoot = Join-Path $PSScriptRoot ".combined_release_build"
$buildDir = Join-Path $buildRoot ([DateTime]::Now.ToString("yyyyMMdd_HHmmss"))
$guiExtractDir = Join-Path $buildDir "gui_source"
$webExtractDir = Join-Path $buildDir "web_source"
$releaseRoot = Join-Path $buildDir "release"
$combinedZip = Join-Path $distDir "WlcRoleAclCollectorWindows_v${version}.zip"
$readmeTemplate = Join-Path $PSScriptRoot "packaging\combined_release\README_START_HERE_KO.txt"

$packages = Get-CurrentReleasePackages -DistDirectory $distDir -Version $version
$guiZip = $packages.Gui
$webZip = $packages.Web

[System.IO.Directory]::CreateDirectory($guiExtractDir) | Out-Null
[System.IO.Directory]::CreateDirectory($webExtractDir) | Out-Null
[System.IO.Directory]::CreateDirectory((Join-Path $releaseRoot "gui")) | Out-Null
[System.IO.Directory]::CreateDirectory((Join-Path $releaseRoot "web")) | Out-Null

Write-Host "Extracting GUI/CLI ZIP: $guiZip"
Expand-LiteralArchive -LiteralPath $guiZip -DestinationPath $guiExtractDir

Write-Host "Extracting Streamlit portable ZIP: $webZip"
Expand-LiteralArchive -LiteralPath $webZip -DestinationPath $webExtractDir

Copy-Item -LiteralPath $readmeTemplate -Destination (Join-Path $releaseRoot "README_START_HERE_KO.txt") -Force
Get-ChildItem -LiteralPath $guiExtractDir | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $releaseRoot "gui") -Recurse -Force
}
Get-ChildItem -LiteralPath $webExtractDir | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $releaseRoot "web") -Recurse -Force
}

Write-Host "Creating combined Windows release ZIP..."
Get-ChildItem -LiteralPath $releaseRoot -Recurse -File | ForEach-Object {
    Wait-ForReadableFile -Path $_.FullName
}
Compress-ArchiveWithRetry -DirectoryPath $releaseRoot -DestinationPath $combinedZip

Write-Host ""
Write-Host "Combined release build completed."
Write-Host "Build work directory: $buildDir"
Write-Host "Combined release ZIP: $combinedZip"
