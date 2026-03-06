# tools\e2e_all.ps1
# Runs:
#   1) e2e_smoke.ps1
#   2) e2e_suite.ps1
# Writes a combined summary under _proof\e2e_all_<ts>

param(
    [string]$Target,
    [string]$PfPath,
    [string]$BackupRoot
)

$ErrorActionPreference = 'Stop'
$invokeCwd = (Get-Location).Path

# ----- Guard -----
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
if ((Get-Location).Path -ne $repoRoot) { "hey stupid Fucker, wrong window again"; exit 1 }

if ([string]::IsNullOrWhiteSpace($Target)) {
    $targetResolved = $null
    try {
        $gitTop = (& git -C $invokeCwd rev-parse --show-toplevel 2>$null)
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($gitTop)) { $targetResolved = $gitTop.Trim() }
    } catch {}
    if ([string]::IsNullOrWhiteSpace($targetResolved)) { $targetResolved = $invokeCwd }
    $Target = $targetResolved
}

$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$pf = $null
if (-not [string]::IsNullOrWhiteSpace($PfPath)) {
    $pf = [System.IO.Path]::GetFullPath($PfPath)
} else {
    $backup = if (-not [string]::IsNullOrWhiteSpace($BackupRoot)) { $BackupRoot } else { $env:NGKS_BACKUP_ROOT }
    if ([string]::IsNullOrWhiteSpace($backup)) {
        throw "Missing required -BackupRoot (or NGKS_BACKUP_ROOT) when -PfPath is not provided"
    }
    if (!(Test-Path $backup)) { New-Item -ItemType Directory -Force -Path $backup | Out-Null }
    $repoName = Split-Path -Leaf $Target
    $pf = Join-Path $backup (Join-Path $repoName (Join-Path '_proof' ("e2e_all_" + $ts)))
}
New-Item -ItemType Directory -Force -Path $pf | Out-Null

# record environment
@(
    "TS=$(Get-Date -Format o)"
    "REPO=$repoRoot"
    "TARGET=$Target"
    "PF=$pf"
) | Out-File (Join-Path $pf '00_env.txt') -Encoding utf8

function Invoke-Test {
    param(
        [string]$ScriptName,
        [string]$Label
    )

    $scriptPath = Join-Path $repoRoot ("tools\" + $ScriptName)
    if (-not (Test-Path $scriptPath)) {
        return @{
            name = $Label
            pass = $false
            note = "missing script: $ScriptName"
        }
    }

    $subPf = Join-Path $pf $Label
    New-Item -ItemType Directory -Force -Path $subPf | Out-Null

    $null = & powershell -NoProfile -ExecutionPolicy Bypass `
        -File $scriptPath `
        -Target $Target `
        -PfPath $subPf `
        -BackupRoot $BackupRoot

    $ec = [int]$LASTEXITCODE

    return @{
        name = $Label
        pass = ($ec -eq 0)
        note = "exit=$ec"
    }
}

$results = @()

$results += Invoke-Test -ScriptName 'e2e_smoke.ps1' -Label 'SMOKE'
$results += Invoke-Test -ScriptName 'e2e_suite.ps1' -Label 'SUITE'

$fail = ($results | Where-Object { -not $_.pass }).Count
$pass = ($results | Where-Object { $_.pass }).Count

# ----- Combined Summary -----
"NGKsDevFabric E2E ALL" | Out-File (Join-Path $pf 'SUMMARY.txt') -Encoding utf8
("TS=" + (Get-Date -Format o)) | Out-File (Join-Path $pf 'SUMMARY.txt') -Append -Encoding utf8
("TARGET=" + $Target) | Out-File (Join-Path $pf 'SUMMARY.txt') -Append -Encoding utf8
("PASS=" + $pass) | Out-File (Join-Path $pf 'SUMMARY.txt') -Append -Encoding utf8
("FAIL=" + $fail) | Out-File (Join-Path $pf 'SUMMARY.txt') -Append -Encoding utf8
"" | Out-File (Join-Path $pf 'SUMMARY.txt') -Append -Encoding utf8

foreach ($r in $results) {
    ("{0} pass={1} note={2}" -f $r.name, $r.pass, $r.note) |
        Out-File (Join-Path $pf 'SUMMARY.txt') -Append -Encoding utf8
}

Write-Output ("E2E_ALL_DONE PF=" + $pf)

if ($fail -gt 0) { exit 1 }
exit 0