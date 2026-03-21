param(
    [string]$ArtifactRoot = "C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_artifacts\widget_sandbox_clean",
    [string]$ArtifactExePath = "",
    [string]$MetadataPath = "",
    [int]$RequireFreshWithinHours = 168,
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
    Write-Log "VERIFY_START"
    Write-Log "ARTIFACT_ROOT=$ArtifactRoot"

    if (-not (Test-Path -LiteralPath $ArtifactRoot)) {
        Write-Log "FAIL_CLOSED: artifact root missing"
        exit 1
    }

    if (-not $ArtifactExePath) {
        $ArtifactExePath = Join-Path $ArtifactRoot "latest\widget_sandbox_clean_latest.exe"
    }
    if (-not $MetadataPath) {
        $MetadataPath = Join-Path $ArtifactRoot "latest\metadata.json"
    }

    Write-Log "ARTIFACT_EXE=$ArtifactExePath"
    Write-Log "METADATA=$MetadataPath"

    if (-not (Test-Path -LiteralPath $ArtifactExePath)) {
        Write-Log "FAIL_CLOSED: artifact exe missing"
        exit 1
    }
    if (-not (Test-Path -LiteralPath $MetadataPath)) {
        Write-Log "FAIL_CLOSED: metadata missing"
        exit 1
    }

    $meta = Get-Content -LiteralPath $MetadataPath -Raw | ConvertFrom-Json

    $actualSize = [int64](Get-Item -LiteralPath $ArtifactExePath).Length
    $actualHash = (Get-FileHash -LiteralPath $ArtifactExePath -Algorithm SHA256).Hash.ToLowerInvariant()

    if ($actualHash -ne ([string]$meta.source_sha256).ToLowerInvariant()) {
        Write-Log "FAIL_CLOSED: metadata hash mismatch"
        exit 1
    }
    if ($actualSize -ne [int64]$meta.source_size) {
        Write-Log "FAIL_CLOSED: metadata size mismatch"
        exit 1
    }

    $capturedUtc = [datetime]$meta.captured_utc
    $ageHours = ((Get-Date).ToUniversalTime() - $capturedUtc).TotalHours
    Write-Log ("ARTIFACT_AGE_HOURS={0:N2}" -f $ageHours)

    if ($ageHours -gt $RequireFreshWithinHours) {
        Write-Log "FAIL_CLOSED: artifact stale"
        exit 1
    }

    if ($RequireBaselineMatch) {
        if (-not [bool]$meta.baseline_hash_match) {
            Write-Log "FAIL_CLOSED: baseline_hash_match=false"
            exit 1
        }
        if (($null -ne $meta.expected_clean_size) -and -not [bool]$meta.baseline_size_match) {
            Write-Log "FAIL_CLOSED: baseline_size_match=false"
            exit 1
        }
    }

    Write-Log "VERIFY_OK"
    Write-Log "SHA256=$actualHash"
    Write-Log "SIZE=$actualSize"
    Write-Log "BASELINE_HASH_MATCH=$($meta.baseline_hash_match)"
    Write-Log "BASELINE_SIZE_MATCH=$($meta.baseline_size_match)"
    exit 0
}
catch {
    Write-Log ("FAIL_CLOSED: exception: " + $_.Exception.Message)
    exit 1
}
