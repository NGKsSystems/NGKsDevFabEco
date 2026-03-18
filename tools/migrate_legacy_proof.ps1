param(
    [Parameter(Mandatory = $true)]
    [string]$TargetProofDir,

    [string]$LogPath,

    [switch]$Preview
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Log {
    param([string]$Message)

    $line = ('[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message)
    Write-Output $line
    if ($script:LogPathValue) {
        Add-Content -Path $script:LogPathValue -Value $line
    }
}

function Test-ZipReadable {
    param([string]$ZipPath)

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $null = $archive.Entries.Count
        return $true
    }
    finally {
        $archive.Dispose()
    }
}

function New-ZipFromDirectory {
    param(
        [string]$SourceDir,
        [string]$ZipPath
    )

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $tempZip = $ZipPath + '.tmp'
    if (Test-Path $tempZip) {
        Remove-Item $tempZip -Force
    }
    [System.IO.Compression.ZipFile]::CreateFromDirectory($SourceDir, $tempZip, [System.IO.Compression.CompressionLevel]::Optimal, $false)
    Move-Item -Path $tempZip -Destination $ZipPath -Force
}

function New-ZipFromFile {
    param(
        [string]$SourceFile,
        [string]$ZipPath
    )

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $tempZip = $ZipPath + '.tmp'
    if (Test-Path $tempZip) {
        Remove-Item $tempZip -Force
    }

    $fs = [System.IO.File]::Open($tempZip, [System.IO.FileMode]::CreateNew)
    try {
        $archive = New-Object System.IO.Compression.ZipArchive($fs, [System.IO.Compression.ZipArchiveMode]::Create, $false)
        try {
            $entryName = [System.IO.Path]::GetFileName($SourceFile)
            $entry = $archive.CreateEntry($entryName, [System.IO.Compression.CompressionLevel]::Optimal)
            $entryStream = $entry.Open()
            try {
                $sourceStream = [System.IO.File]::OpenRead($SourceFile)
                try {
                    $sourceStream.CopyTo($entryStream)
                }
                finally {
                    $sourceStream.Dispose()
                }
            }
            finally {
                $entryStream.Dispose()
            }
        }
        finally {
            $archive.Dispose()
        }
    }
    finally {
        $fs.Dispose()
    }

    Move-Item -Path $tempZip -Destination $ZipPath -Force
}

function Move-ToQuarantine {
    param(
        [string]$ItemPath,
        [string]$QuarantineRoot
    )

    $name = Split-Path -Path $ItemPath -Leaf
    $destination = Join-Path $QuarantineRoot $name
    $suffix = 1
    while (Test-Path $destination) {
        $destination = Join-Path $QuarantineRoot ('{0}_{1:00}' -f $name, $suffix)
        $suffix += 1
    }
    Move-Item -Path $ItemPath -Destination $destination
    return $destination
}

function Remove-TempZipIfPresent {
    param([string]$ZipPath)

    $tempZip = $ZipPath + '.tmp'
    if (Test-Path $tempZip) {
        Remove-Item -LiteralPath $tempZip -Force -ErrorAction SilentlyContinue
    }
}

$resolvedTarget = (Resolve-Path $TargetProofDir).Path
$targetParent = Split-Path -Path $resolvedTarget -Parent
$script:LogPathValue = $null
if ($LogPath) {
    $script:LogPathValue = $LogPath
    if (Test-Path $LogPath) {
        Remove-Item $LogPath -Force
    }
}

$quarantineRoot = Join-Path $targetParent '_proof_quarantine_failed_migration'

$items = Get-ChildItem -LiteralPath $resolvedTarget -Force | Sort-Object Name
$candidateDirs = @($items | Where-Object { $_.PSIsContainer -and $_.Name -ne '_QUARANTINE_FAILED_MIGRATION' })
$candidateFiles = @($items | Where-Object { -not $_.PSIsContainer -and $_.Extension -ne '.zip' })

$summary = [ordered]@{
    target_proof_dir = $resolvedTarget
    preview = [bool]$Preview
    directory_candidates = $candidateDirs.Count
    file_candidates = $candidateFiles.Count
    directories_converted = 0
    files_converted = 0
    directories_removed_via_existing_zip = 0
    files_removed_via_existing_zip = 0
    quarantined = 0
    skipped = 0
    unverifiable = 0
}

Write-Log ('TARGET_PROOF_DIR={0}' -f $resolvedTarget)
Write-Log ('PREVIEW={0}' -f ([bool]$Preview))
Write-Log ('DIRECTORY_CANDIDATES={0}' -f $candidateDirs.Count)
Write-Log ('FILE_CANDIDATES={0}' -f $candidateFiles.Count)

foreach ($dir in $candidateDirs) {
    $zipPath = Join-Path $resolvedTarget ($dir.Name + '.zip')
    Write-Log ('DIRECTORY {0} -> {1}' -f $dir.FullName, $zipPath)

    if ($Preview) {
        if (Test-Path $zipPath) {
            Write-Log 'PLAN=VERIFY_EXISTING_ZIP_THEN_REMOVE_DIRECTORY'
        }
        else {
            Write-Log 'PLAN=CREATE_ZIP_VERIFY_REMOVE_DIRECTORY'
        }
        continue
    }

    try {
        if (Test-Path $zipPath) {
            if (Test-ZipReadable -ZipPath $zipPath) {
                Remove-Item -LiteralPath $dir.FullName -Recurse -Force
                $summary.directories_removed_via_existing_zip += 1
                Write-Log 'ACTION=REMOVED_DIRECTORY_AFTER_EXISTING_ZIP_VERIFIED'
            }
            else {
                $summary.unverifiable += 1
                Write-Log 'ACTION=LEFT_DIRECTORY_EXISTING_ZIP_NOT_READABLE'
            }
            continue
        }

        New-ZipFromDirectory -SourceDir $dir.FullName -ZipPath $zipPath
        if (-not (Test-ZipReadable -ZipPath $zipPath)) {
            throw 'ZIP_VERIFICATION_FAILED'
        }
        Remove-Item -LiteralPath $dir.FullName -Recurse -Force
        $summary.directories_converted += 1
        Write-Log 'ACTION=CREATED_ZIP_VERIFIED_AND_REMOVED_DIRECTORY'
    }
    catch {
        $summary.unverifiable += 1
        Write-Log ('ERROR={0}' -f $_.Exception.Message)
        Remove-TempZipIfPresent -ZipPath $zipPath
        try {
            if (-not (Test-Path $quarantineRoot)) {
                New-Item -ItemType Directory -Path $quarantineRoot | Out-Null
            }
            $moved = Move-ToQuarantine -ItemPath $dir.FullName -QuarantineRoot $quarantineRoot
            $summary.quarantined += 1
            Write-Log ('ACTION=QUARANTINED {0}' -f $moved)
        }
        catch {
            Write-Log ('ACTION=LEFT_DIRECTORY_IN_PLACE {0}' -f $dir.FullName)
            Write-Log ('QUARANTINE_ERROR={0}' -f $_.Exception.Message)
        }
    }
}

foreach ($file in $candidateFiles) {
    $zipPath = Join-Path $resolvedTarget ($file.Name + '.zip')
    Write-Log ('FILE {0} -> {1}' -f $file.FullName, $zipPath)

    if ($Preview) {
        if (Test-Path $zipPath) {
            Write-Log 'PLAN=VERIFY_EXISTING_ZIP_THEN_REMOVE_FILE'
        }
        else {
            Write-Log 'PLAN=CREATE_ZIP_VERIFY_REMOVE_FILE'
        }
        continue
    }

    try {
        if (Test-Path $zipPath) {
            if (Test-ZipReadable -ZipPath $zipPath) {
                Remove-Item -LiteralPath $file.FullName -Force
                $summary.files_removed_via_existing_zip += 1
                Write-Log 'ACTION=REMOVED_FILE_AFTER_EXISTING_ZIP_VERIFIED'
            }
            else {
                $summary.unverifiable += 1
                Write-Log 'ACTION=LEFT_FILE_EXISTING_ZIP_NOT_READABLE'
            }
            continue
        }

        New-ZipFromFile -SourceFile $file.FullName -ZipPath $zipPath
        if (-not (Test-ZipReadable -ZipPath $zipPath)) {
            throw 'ZIP_VERIFICATION_FAILED'
        }
        Remove-Item -LiteralPath $file.FullName -Force
        $summary.files_converted += 1
        Write-Log 'ACTION=CREATED_ZIP_VERIFIED_AND_REMOVED_FILE'
    }
    catch {
        $summary.unverifiable += 1
        Write-Log ('ERROR={0}' -f $_.Exception.Message)
        Remove-TempZipIfPresent -ZipPath $zipPath
        try {
            if (-not (Test-Path $quarantineRoot)) {
                New-Item -ItemType Directory -Path $quarantineRoot | Out-Null
            }
            $moved = Move-ToQuarantine -ItemPath $file.FullName -QuarantineRoot $quarantineRoot
            $summary.quarantined += 1
            Write-Log ('ACTION=QUARANTINED {0}' -f $moved)
        }
        catch {
            Write-Log ('ACTION=LEFT_FILE_IN_PLACE {0}' -f $file.FullName)
            Write-Log ('QUARANTINE_ERROR={0}' -f $_.Exception.Message)
        }
    }
}

$summaryJson = $summary | ConvertTo-Json -Depth 4
Write-Log ('SUMMARY={0}' -f $summaryJson)