# Offline behavioral regression harness. Run with Windows PowerShell 5.1.
param()
$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0
$repoRoot = Split-Path -Parent $PSScriptRoot
$originalLocation = Get-Location
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("wlc [packaging] space " + [Guid]::NewGuid().ToString("N"))
[System.IO.Directory]::CreateDirectory($testRoot) | Out-Null
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$testState = @{ DownloadCount = 0; DownloadMode = "success"; CopyAttempts = 0; FailCopies = 0; ExeCopyAttempts = 0 }

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "Assertion failed: $Message" }
}
function Assert-Throws([scriptblock]$Action, [string]$Message) {
    $failed = $false
    try { & $Action } catch { $failed = $true }
    Assert-True $failed $Message
}
function Write-FixtureZip([string]$Path, [hashtable]$Entries) {
    if ([System.IO.File]::Exists($Path)) { [System.IO.File]::Delete($Path) }
    $zip = [System.IO.Compression.ZipFile]::Open($Path, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($name in $Entries.Keys) {
            $entry = $zip.CreateEntry($name)
            $stream = $entry.Open()
            try {
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($Entries[$name])
                $stream.Write($bytes, 0, $bytes.Length)
            } finally { $stream.Dispose() }
        }
    } finally { $zip.Dispose() }
}
function Read-ZipEntry([string]$Path, [string]$Name) {
    $zip = [System.IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $entry = $zip.GetEntry($Name)
        if ($null -eq $entry) {
            $available = @($zip.Entries | Select-Object -First 30 | ForEach-Object { $_.FullName }) -join ', '
            throw "ZIP entry missing: $Name. Available entries (up to 30): $available"
        }
        $reader = New-Object System.IO.StreamReader($entry.Open())
        try { return $reader.ReadToEnd() } finally { $reader.Dispose() }
    } finally { $zip.Dispose() }
}

try {
    . (Join-Path $PSScriptRoot "windows_packaging.ps1")
    $dist = Join-Path $testRoot "dist"
    [System.IO.Directory]::CreateDirectory($dist) | Out-Null
    $version = "9.8.7"
    $guiZip = Join-Path $dist "WlcRoleAclCollectorGUI_v$version.zip"
    $webZip = Join-Path $dist "WlcRoleAclCollectorWeb_v$version.zip"
    Write-FixtureZip $guiZip @{ "current.txt" = "current gui" }
    Write-FixtureZip $webZip @{ "current.txt" = "current web" }
    foreach ($kind in @("GUI", "Web")) {
        $stale = Join-Path $dist "WlcRoleAclCollector${kind}_v0.0.1.zip"
        Write-FixtureZip $stale @{ "stale.txt" = "wrong version" }
        [System.IO.File]::SetLastWriteTime($stale, [DateTime]::Now.AddDays(1))
    }
    $selected = Get-CurrentReleasePackages -DistDirectory $dist -Version $version
    Assert-True ($selected.Gui -eq $guiZip -and $selected.Web -eq $webZip) "exact version wins over newer mtime"
    [System.IO.File]::Delete($webZip)
    Assert-Throws { Get-CurrentReleasePackages -DistDirectory $dist -Version $version } "missing exact Web must fail rather than use stale ZIP"
    Write-FixtureZip $webZip @{ "current.txt" = "current web" }
    [System.IO.File]::Delete($guiZip)
    Assert-Throws { Get-CurrentReleasePackages -DistDirectory $dist -Version $version } "missing exact GUI must fail rather than use stale ZIP"
    Write-FixtureZip $guiZip @{ "current.txt" = "current gui" }
    Write-Host "PASS exact-version package selection"

    # Round-trip real nested files through literal ZIP destinations and overwrite.
    $archiveSource = Join-Path $testRoot "source [tree]"
    $nested = Join-Path $archiveSource "nested [entry]"
    [System.IO.Directory]::CreateDirectory($nested) | Out-Null
    [System.IO.Directory]::CreateDirectory((Join-Path $archiveSource "empty [entry]")) | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $nested "payload.txt"), "round trip bytes")
    $roundTripZip = Join-Path $testRoot "round trip [archive].zip"
    Compress-ArchiveWithRetry -DirectoryPath $archiveSource -DestinationPath $roundTripZip
    Assert-True ((Read-ZipEntry $roundTripZip "nested [entry]/payload.txt") -eq "round trip bytes") "nested ZIP entry uses forward slashes"
    Assert-True ((Read-ZipEntry $roundTripZip "empty [entry]/") -eq "") "empty directory ZIP entry preserved with forward slash"
    $archiveDestination = Join-Path $testRoot "expanded [tree]"
    Expand-LiteralArchive -LiteralPath $roundTripZip -DestinationPath $archiveDestination
    $expandedFile = Join-Path $archiveDestination "nested [entry]\payload.txt"
    Assert-True ([System.IO.File]::ReadAllText($expandedFile) -eq "round trip bytes") "literal nested paths and archive root layout preserved"
    [System.IO.File]::WriteAllText($expandedFile, "old bytes")
    Expand-LiteralArchive -LiteralPath $roundTripZip -DestinationPath $archiveDestination
    Assert-True ([System.IO.File]::ReadAllText($expandedFile) -eq "round trip bytes") "existing extraction files overwritten"
    $outsideZip = Join-Path $testRoot "outside-entry.zip"
    Write-FixtureZip $outsideZip @{ "../escaped.txt" = "must not extract" }
    Assert-Throws { Expand-LiteralArchive -LiteralPath $outsideZip -DestinationPath $archiveDestination } "entry outside destination rejected"
    Assert-True (-not [System.IO.File]::Exists((Join-Path $testRoot "escaped.txt"))) "extraction stays within destination"
    Write-Host "PASS literal ZIP round trip, extraction overwrite and destination containment"

    $runtimeFixture = Join-Path $testRoot "runtime.zip"
    Write-FixtureZip $runtimeFixture @{
        "python.exe" = "synthetic executable"; "python311.dll" = "synthetic DLL"
        "python311.zip" = "synthetic library"; "python311._pth" = "python311.zip"
    }
    $cache = Join-Path $testRoot "cache [runtime].zip"
    $testState.DownloadCount = 0
    $testState.DownloadMode = "success"
    function Invoke-WebRequest {
        param($Uri, $OutFile, [switch]$UseBasicParsing, $ErrorAction)
        $testState.DownloadCount++
        if ($testState.DownloadMode -eq "interrupted") {
            [System.IO.File]::WriteAllText($OutFile, "partial download")
            throw "injected interrupted download"
        }
        if ($testState.DownloadMode -eq "invalid") {
            [System.IO.File]::WriteAllText($OutFile, "invalid response")
            return
        }
        [System.IO.File]::Copy($runtimeFixture, $OutFile, $true)
    }
    [System.IO.File]::WriteAllText($cache, "old interrupted cache")
    Get-EmbeddedPythonArchive -Path $cache -Uri "https://fixture.invalid/runtime" -PythonTag "311"
    Assert-True ($testState.DownloadCount -eq 1) "corrupt cache downloads replacement"
    Assert-True (Test-EmbeddedPythonArchive -Path $cache -PythonTag "311") "replacement cache is valid"
    Get-EmbeddedPythonArchive -Path $cache -Uri "https://fixture.invalid/runtime" -PythonTag "311"
    Assert-True ($testState.DownloadCount -eq 1) "valid cache performs no download"
    [System.IO.File]::Delete($cache)
    foreach ($mode in @("interrupted", "invalid")) {
        $testState.DownloadMode = $mode
        Assert-Throws { Get-EmbeddedPythonArchive -Path $cache -Uri "https://fixture.invalid/runtime" -PythonTag "311" } "$mode download must fail"
        Assert-True (-not [System.IO.File]::Exists($cache)) "$mode download is never promoted"
        $partials = @(Get-ChildItem -LiteralPath $testRoot -Filter "*.partial")
        Assert-True ($partials.Count -eq 0) "$mode download temporary file cleaned"
    }
    $testState.DownloadMode = "success"
    Get-EmbeddedPythonArchive -Path $cache -Uri "https://fixture.invalid/runtime" -PythonTag "311"
    $wrongRuntime = Join-Path $testRoot "wrong-runtime.zip"
    Write-FixtureZip $wrongRuntime @{ "python.exe" = "wrong runtime" }
    Assert-True (-not (Test-EmbeddedPythonArchive -Path $wrongRuntime -PythonTag "311")) "ZIP missing versioned runtime files rejected"
    Assert-True (-not (Test-EmbeddedPythonArchive -Path $cache -PythonTag "312")) "wrong Python runtime tag rejected"
    Write-Host "PASS runtime cache validation, reuse and interrupted/invalid download cleanup"

    # Override only the OS copy boundary; copy still operates on real fixture files.
    $testState.CopyAttempts = 0
    $testState.FailCopies = 1
    function Copy-Item {
        [CmdletBinding()]
        param([string]$LiteralPath, [string]$Destination, [switch]$Force, [switch]$Recurse)
        $testState.CopyAttempts++
        if ($testState.FailCopies -gt 0) {
            $testState.FailCopies--
            throw "injected transient sharing violation"
        }
        Microsoft.PowerShell.Management\Copy-Item -LiteralPath $LiteralPath -Destination $Destination -Force:$Force -Recurse:$Recurse
    }
    $exe = Join-Path $testRoot "GUI [fixture].exe"
    $copied = Join-Path $testRoot "copied [fixture].exe"
    [System.IO.File]::WriteAllText($exe, "synthetic executable bytes")
    Copy-ReadableFileWithRetry -LiteralPath $exe -Destination $copied -Attempts 3 -DelayMilliseconds 1
    Assert-True ($testState.CopyAttempts -eq 2) "initial EXE copy retries a transient failure"
    Assert-True ([System.IO.File]::ReadAllText($copied) -eq "synthetic executable bytes") "retried copy preserves bytes"
    $testState.FailCopies = 9
    Assert-Throws { Copy-ReadableFileWithRetry -LiteralPath $exe -Destination $copied -Attempts 2 -DelayMilliseconds 1 } "copy failure has bounded attempts"
    Assert-True ($testState.CopyAttempts -eq 4) "copy exhausted after requested attempts"
    $testState.FailCopies = 0
    $locked = [System.IO.File]::Open($exe, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    try {
        Assert-Throws { Copy-ReadableFileWithRetry -LiteralPath $exe -Destination $copied -Attempts 1 -DelayMilliseconds 1 } "unreadable EXE fails before copy"
        Assert-True ($testState.CopyAttempts -eq 4) "readability checked before initial copy"
    } finally { $locked.Dispose() }
    Remove-Item Function:\Copy-Item
    Write-Host "PASS initial EXE readability and bounded copy retry"

    # Exercise GUI and portable orchestration with synthetic build/runtime processes.
    # The no-op runtime checks path/packaging behavior, not real dependency execution.
    $fixtureRepo = Join-Path $testRoot "repository [literal]"
    foreach ($directory in @("tools", "docs", "config\mock_scenarios", "packaging\streamlit_portable")) {
        [System.IO.Directory]::CreateDirectory((Join-Path $fixtureRepo $directory)) | Out-Null
    }
    foreach ($builder in @("gui_exe", "streamlit_portable")) {
        Copy-Item -LiteralPath (Join-Path $repoRoot "build_windows_$builder.ps1") -Destination $fixtureRepo
    }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "windows_packaging.ps1") -Destination (Join-Path $fixtureRepo "tools")
    foreach ($guide in @("USER_GUIDE_KO", "DEVELOPER_GUIDE_KO", "ERROR_CODES_KO", "DIAGNOSTIC_MODE_KO", "SECURITY_MODEL_KO", "DEPENDENCY_AUDIT_EXCEPTIONS_KO")) {
        foreach ($extension in @("md", "html")) {
            [System.IO.File]::WriteAllText((Join-Path $fixtureRepo "docs\$guide.$extension"), "synthetic guide")
        }
    }
    [System.IO.File]::WriteAllText((Join-Path $fixtureRepo "config\role_networks.example.xlsx"), "synthetic template")
    [System.IO.File]::WriteAllText((Join-Path $fixtureRepo "config\mock_scenarios\sample.json"), "{}")
    [System.IO.File]::WriteAllText((Join-Path $fixtureRepo "app.py"), "# synthetic app")
    foreach ($template in @("webapp_settings.cmd", "README_WEBAPP_KO.txt")) {
        [System.IO.File]::WriteAllText((Join-Path $fixtureRepo "packaging\streamlit_portable\$template"), "synthetic template")
    }
    [System.IO.File]::WriteAllText((Join-Path $fixtureRepo "packaging\streamlit_portable\start_webapp.cmd"), "@echo off`r`necho STREAMLIT_PORTABLE_OK`r`n")
    function Invoke-FixturePython {
        $global:LASTEXITCODE = 0
        if ($args[0] -eq "-c") { return "9.8.7" }
        if ($args.Count -gt 1 -and $args[1] -eq "PyInstaller") {
            $nameIndex = [Array]::IndexOf($args, "--name")
            $distIndex = [Array]::IndexOf($args, "--distpath")
            [System.IO.File]::WriteAllText((Join-Path $args[$distIndex + 1] ($args[$nameIndex + 1] + ".exe")), "synthetic executable")
        }
    }
    $testState.ExeCopyAttempts = 0
    function Copy-Item {
        [CmdletBinding()]
        param([string]$LiteralPath, [string]$Destination, [switch]$Force, [switch]$Recurse)
        if ($LiteralPath.EndsWith(".exe") -and (Split-Path -Leaf (Split-Path -Parent $LiteralPath)) -eq "dist") {
            $testState.ExeCopyAttempts++
            if ($testState.ExeCopyAttempts -eq 1) { throw "injected first GUI copy failure" }
        }
        Microsoft.PowerShell.Management\Copy-Item -LiteralPath $LiteralPath -Destination $Destination -Force:$Force -Recurse:$Recurse
    }
    & (Join-Path $fixtureRepo "build_windows_gui_exe.ps1") -PythonExe "Invoke-FixturePython"
    Remove-Item Function:\Copy-Item
    Assert-True ($testState.ExeCopyAttempts -eq 2) "GUI builder retries the initial copy once"
    $builtGuiZip = Join-Path $fixtureRepo "dist\WlcRoleAclCollectorGUI_v$version.zip"
    Assert-True ((Read-ZipEntry $builtGuiZip "WlcRoleAclCollectorGUI.exe") -eq "synthetic executable") "GUI root layout preserved"
    Assert-True ((Read-ZipEntry $builtGuiZip "config/mock_scenarios/sample.json") -eq "{}") "GUI nested config preserved"
    Write-Host "PASS GUI builder in literal bracketed path and injected initial copy failure"

    $runtimeDirectory = Join-Path $testRoot "runtime files"
    [System.IO.Directory]::CreateDirectory($runtimeDirectory) | Out-Null
    # Add-Type wildcard-resolves its output path on Windows PowerShell 5.1.
    # Stage compilation separately; all builder/runtime fixture paths stay bracketed.
    $compileDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("wlc_compile_" + [Guid]::NewGuid().ToString("N"))
    [System.IO.Directory]::CreateDirectory($compileDirectory) | Out-Null
    try {
        $compiledExe = Join-Path $compileDirectory "python.exe"
        Add-Type -TypeDefinition 'public class PackagingFixtureRuntime { public static int Main(string[] args) { return 0; } }' -OutputAssembly $compiledExe -OutputType ConsoleApplication
        [System.IO.File]::Move($compiledExe, (Join-Path $runtimeDirectory "python.exe"))
    } finally { Remove-Item -LiteralPath $compileDirectory -Recurse -Force }
    foreach ($name in @("python311.dll", "python311.zip", "python311._pth")) {
        [System.IO.File]::WriteAllText((Join-Path $runtimeDirectory $name), "synthetic runtime")
    }
    $runtimeFixture = Join-Path $testRoot "executable-runtime.zip"
    [System.IO.Compression.ZipFile]::CreateFromDirectory($runtimeDirectory, $runtimeFixture)
    $portableCacheDir = Join-Path $fixtureRepo ".streamlit_portable_build\cache"
    [System.IO.Directory]::CreateDirectory($portableCacheDir) | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $portableCacheDir "python-3.11.9-embed-amd64.zip"), "interrupted cache")
    $downloadsBeforeBuild = $testState.DownloadCount
    & (Join-Path $fixtureRepo "build_windows_streamlit_portable.ps1") -PythonExe "Invoke-FixturePython" -EmbeddedPythonVersion "3.11.9"
    Assert-True ($testState.DownloadCount -eq ($downloadsBeforeBuild + 1)) "portable builder replaces corrupt cached runtime"
    $builtWebZip = Join-Path $fixtureRepo "dist\WlcRoleAclCollectorWeb_v$version.zip"
    Assert-True ((Read-ZipEntry $builtWebZip "app/app.py") -eq "# synthetic app") "portable app layout preserved"
    Assert-True ((Read-ZipEntry $builtWebZip "python/python311._pth").Contains("import site")) "portable runtime configuration preserved"
    Write-Host "PASS portable builder in literal bracketed path and corrupt cache recovery"

    # Execute the complete combined builder in a path containing spaces/brackets.
    $fixtureRepo = Join-Path $testRoot "repository [literal]"
    [System.IO.Directory]::CreateDirectory((Join-Path $fixtureRepo "tools")) | Out-Null
    [System.IO.Directory]::CreateDirectory((Join-Path $fixtureRepo "packaging\combined_release")) | Out-Null
    Copy-Item -LiteralPath (Join-Path $repoRoot "build_windows_combined_release.ps1") -Destination $fixtureRepo
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "windows_packaging.ps1") -Destination (Join-Path $fixtureRepo "tools")
    Copy-Item -LiteralPath (Join-Path $repoRoot "packaging\combined_release\README_START_HERE_KO.txt") -Destination (Join-Path $fixtureRepo "packaging\combined_release")
    Get-ChildItem -LiteralPath $dist | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $fixtureRepo "dist") -Force
    }
    & (Join-Path $fixtureRepo "build_windows_combined_release.ps1") -PythonExe "Invoke-FixturePython"
    $combined = Join-Path $fixtureRepo "dist\WlcRoleAclCollectorWindows_v$version.zip"
    Assert-True ((Read-ZipEntry $combined "gui/current.txt") -eq "current gui") "GUI content and layout preserved"
    Assert-True ((Read-ZipEntry $combined "web/current.txt") -eq "current web") "Web content and layout preserved"
    Assert-True ((Read-ZipEntry $combined "README_START_HERE_KO.txt").Length -gt 0) "root README preserved"
    Write-Host "PASS combined builder in literal bracketed path and ZIP layout"
    Write-Host "WINDOWS_PACKAGING_TESTS_OK"
} finally {
    Set-Location -LiteralPath $originalLocation.Path
    Remove-Item -LiteralPath $testRoot -Recurse -Force
}
