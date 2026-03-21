param(
    [string]$SourceExePath = "C:\Users\suppo\Desktop\NGKsSystems\NGKsUI Runtime\build\debug\bin\widget_sandbox.exe",
    [string]$ArtifactRoot = "C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_artifacts\widget_sandbox_clean",
    [string]$BuildContext = "local_build",
    [string]$ExpectedCleanHash = "",
    [Nullable[long]]$ExpectedCleanSize = $null,
    [switch]$RequireBaselineMatch,
    [string]$LogPath = ""
)

$ErrorActionPreference = "Stop"

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    if ($LogPath) {
        Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
    }
}

try {
    Write-Log "CAPTURE_START"
    Write-Log "SOURCE_EXE=$SourceExePath"
    Write-Log "ARTIFACT_ROOT=$ArtifactRoot"

    if (-not (Test-Path -LiteralPath $SourceExePath)) {
        Write-Log "FAIL_CLOSED: source exe missing"
        exit 1
    }

    New-Item -ItemType Directory -Path $ArtifactRoot -Force | Out-Null
    $latestDir = Join-Path $ArtifactRoot "latest"
    New-Item -ItemType Directory -Path $latestDir -Force | Out-Null

    $src = Get-Item -LiteralPath $SourceExePath
    $hash = (Get-FileHash -LiteralPath $SourceExePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $size = [int64]$src.Length
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"

    $versionDir = Join-Path $ArtifactRoot ("capture_" + $stamp)
    New-Item -ItemType Directory -Path $versionDir -Force | Out-Null

    $artifactName = "widget_sandbox_clean_{0}.exe" -f $stamp
    $versionExe = Join-Path $versionDir $artifactName
    $latestExe = Join-Path $latestDir "widget_sandbox_clean_latest.exe"

    Copy-Item -LiteralPath $SourceExePath -Destination $versionExe -Force
    Copy-Item -LiteralPath $SourceExePath -Destination $latestExe -Force

    $baselineHashMatch = $false
    $baselineSizeMatch = $false

    if ($ExpectedCleanHash) {
        $baselineHashMatch = ($hash -eq $ExpectedCleanHash.ToLowerInvariant())
    }
    if ($null -ne $ExpectedCleanSize) {
        $baselineSizeMatch = ($size -eq $ExpectedCleanSize)
    }

    if ($RequireBaselineMatch) {
        if ($ExpectedCleanHash -and -not $baselineHashMatch) {
            Write-Log "FAIL_CLOSED: baseline hash mismatch"
            exit 1
        }
        if (($null -ne $ExpectedCleanSize) -and -not $baselineSizeMatch) {
            Write-Log "FAIL_CLOSED: baseline size mismatch"
            exit 1
        }
    }

    $meta = [ordered]@{
        artifact_type = "widget_sandbox_clean_restore_source"
        captured_utc = (Get-Date -AsUTC -Format o)
        source_exe = $SourceExePath
        source_size = $size
        source_sha256 = $hash
        build_context = $BuildContext
        expected_clean_hash = $ExpectedCleanHash
        expected_clean_size = $ExpectedCleanSize
        baseline_hash_match = $baselineHashMatch
        baseline_size_match = $baselineSizeMatch
        require_baseline_match = [bool]$RequireBaselineMatch
        note = "Capture script preserves executable artifact; clean-status is only true when baseline matches."
    }

    $metaJson = $meta | ConvertTo-Json -Depth 6
    $versionMeta = Join-Path $versionDir "metadata.json"
    $latestMeta = Join-Path $latestDir "metadata.json"

    $metaJson | Set-Content -LiteralPath $versionMeta -Encoding UTF8
    $metaJson | Set-Content -LiteralPath $latestMeta -Encoding UTF8

    Write-Log "CAPTURE_OK"
    Write-Log "VERSION_EXE=$versionExe"
    Write-Log "LATEST_EXE=$latestExe"
    Write-Log "SHA256=$hash"
    Write-Log "SIZE=$size"
    Write-Log "BASELINE_HASH_MATCH=$baselineHashMatch"
    Write-Log "BASELINE_SIZE_MATCH=$baselineSizeMatch"
    exit 0
}
catch {
    Write-Log ("FAIL_CLOSED: exception: " + $_.Exception.Message)
    exit 1
}
