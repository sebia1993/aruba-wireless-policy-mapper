# Shared Windows PowerShell 5.1 packaging operations. Filesystem inputs are literal.
function Wait-ForReadableFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [ValidateRange(1, 1000)][int]$Attempts = 20,
        [ValidateRange(0, 60000)][int]$DelayMilliseconds = 500
    )
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
            $stream.Dispose()
            return
        } catch {
            if ($attempt -eq $Attempts) { throw "File is not ready for reading: $Path`n$($_.Exception.Message)" }
            Start-Sleep -Milliseconds $DelayMilliseconds
        }
    }
}

function Copy-ReadableFileWithRetry {
    param(
        [Parameter(Mandatory = $true)][string]$LiteralPath,
        [Parameter(Mandatory = $true)][string]$Destination,
        [ValidateRange(1, 1000)][int]$Attempts = 20,
        [ValidateRange(0, 60000)][int]$DelayMilliseconds = 500
    )
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            Wait-ForReadableFile -Path $LiteralPath -Attempts 1
            Copy-Item -LiteralPath $LiteralPath -Destination $Destination -Force -ErrorAction Stop
            return
        } catch {
            if ($attempt -eq $Attempts) { throw }
            Start-Sleep -Milliseconds $DelayMilliseconds
        }
    }
}

function Compress-ArchiveWithRetry {
    param(
        [Parameter(Mandatory = $true)][string]$DirectoryPath,
        [Parameter(Mandatory = $true)][string]$DestinationPath,
        [ValidateRange(1, 1000)][int]$Attempts = 5
    )
    # Archive cmdlets on Windows PowerShell wildcard-resolve destination parents
    # even with -LiteralPath. The .NET API keeps both sides literal.
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $contents = @(Get-ChildItem -LiteralPath $DirectoryPath | ForEach-Object { $_.FullName })
    if ($contents.Count -eq 0) { throw "Cannot package an empty directory: $DirectoryPath" }
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            if (Test-Path -LiteralPath $DestinationPath) { Remove-Item -LiteralPath $DestinationPath -Force }
            $root = [System.IO.Path]::GetFullPath($DirectoryPath).TrimEnd([char[]]"\/") + [System.IO.Path]::DirectorySeparatorChar
            $archive = [System.IO.Compression.ZipFile]::Open($DestinationPath, [System.IO.Compression.ZipArchiveMode]::Create)
            try {
                # CreateFromDirectory can emit backslashes under PowerShell 5.1's
                # legacy Framework target. Explicit names keep the ZIP portable.
                foreach ($file in [System.IO.Directory]::EnumerateFiles($root, "*", [System.IO.SearchOption]::AllDirectories)) {
                    $name = $file.Substring($root.Length).Replace('\', '/')
                    [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                        $archive, $file, $name, [System.IO.Compression.CompressionLevel]::Optimal
                    ) | Out-Null
                }
                foreach ($directory in [System.IO.Directory]::EnumerateDirectories($root, "*", [System.IO.SearchOption]::AllDirectories)) {
                    if (@([System.IO.Directory]::EnumerateFileSystemEntries($directory)).Count -eq 0) {
                        $name = $directory.Substring($root.Length).Replace('\', '/') + '/'
                        $entry = $archive.CreateEntry($name)
                        $entry.LastWriteTime = [System.IO.Directory]::GetLastWriteTime($directory)
                    }
                }
            } finally { $archive.Dispose() }
            return
        } catch {
            if ($attempt -eq $Attempts) { throw }
            Start-Sleep -Seconds 1
        }
    }
}

function Expand-LiteralArchive {
    param(
        [Parameter(Mandatory = $true)][string]$LiteralPath,
        [Parameter(Mandatory = $true)][string]$DestinationPath
    )
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $root = [System.IO.Path]::GetFullPath($DestinationPath).TrimEnd([char[]]"\/") + [System.IO.Path]::DirectorySeparatorChar
    [System.IO.Directory]::CreateDirectory($root) | Out-Null
    $archive = [System.IO.Compression.ZipFile]::OpenRead($LiteralPath)
    try {
        foreach ($entry in $archive.Entries) {
            $target = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($root, $entry.FullName))
            if (-not $target.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "ZIP entry is outside the extraction directory: $($entry.FullName)"
            }
            if ($entry.Name -eq "") {
                [System.IO.Directory]::CreateDirectory($target) | Out-Null
            } else {
                [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($target)) | Out-Null
                # Preserve the builders' existing -Force overwrite behavior.
                [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $true)
            }
        }
    } finally { $archive.Dispose() }
}

function Get-CurrentReleasePackages {
    param(
        [Parameter(Mandatory = $true)][string]$DistDirectory,
        [Parameter(Mandatory = $true)][string]$Version
    )
    $gui = Join-Path $DistDirectory "WlcRoleAclCollectorGUI_v${Version}.zip"
    $web = Join-Path $DistDirectory "WlcRoleAclCollectorWeb_v${Version}.zip"
    foreach ($path in @($gui, $web)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Required current-version Windows package was not found: $path"
        }
    }
    return @{ Gui = $gui; Web = $web }
}

function Test-EmbeddedPythonArchive {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$PythonTag
    )
    $archive = $null
    try {
        Add-Type -AssemblyName System.IO.Compression
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $archive = [System.IO.Compression.ZipFile]::OpenRead($Path)
        foreach ($name in @("python.exe", "python${PythonTag}.dll", "python${PythonTag}.zip", "python${PythonTag}._pth")) {
            $entry = $archive.GetEntry($name)
            if ($null -eq $entry -or $entry.Length -eq 0) { return $false }
        }
        # Read every entry, detecting truncated/corrupt compressed data before cache reuse.
        $buffer = New-Object byte[] 65536
        foreach ($entry in $archive.Entries) {
            $stream = $entry.Open()
            try {
                $length = 0L
                while (($count = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) { $length += $count }
                if ($length -ne $entry.Length) { return $false }
            } finally { $stream.Dispose() }
        }
        return $true
    } catch {
        return $false
    } finally {
        if ($null -ne $archive) { $archive.Dispose() }
    }
}

function Get-EmbeddedPythonArchive {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$PythonTag
    )
    if (Test-EmbeddedPythonArchive -Path $Path -PythonTag $PythonTag) { return }
    if (Test-Path -LiteralPath $Path) { Remove-Item -LiteralPath $Path -Force }
    $temporaryPath = "$Path.$([Guid]::NewGuid().ToString('N')).partial"
    try {
        Write-Host "Downloading Python embeddable runtime: $Uri"
        Invoke-WebRequest -Uri $Uri -OutFile $temporaryPath -UseBasicParsing -ErrorAction Stop
        if (-not (Test-EmbeddedPythonArchive -Path $temporaryPath -PythonTag $PythonTag)) {
            throw "Downloaded Python embeddable runtime is invalid: $Uri"
        }
        # Same-directory rename publishes only a complete validated download.
        [System.IO.File]::Move($temporaryPath, $Path)
    } finally {
        if (Test-Path -LiteralPath $temporaryPath) { Remove-Item -LiteralPath $temporaryPath -Force }
    }
}
