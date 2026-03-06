param(
    [string]$Root,
    [string]$PfPath
)

$ErrorActionPreference = 'Stop'

if (-not $Root -or [string]::IsNullOrWhiteSpace($Root)) {
    $Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}

Set-Location $Root

if (-not $PfPath -or [string]::IsNullOrWhiteSpace($PfPath)) {
    $PfPath = (Get-Content ".\\_proof\\CURRENT_PF_PHASE11.txt" -Raw).Trim()
}

if (-not (Test-Path $PfPath)) {
    New-Item -ItemType Directory -Force -Path $PfPath | Out-Null
}

$forbidden = ('c' + 'make')
$targets = @('.vscode', 'tools', 'src')

$allHits = @()
foreach ($target in $targets) {
    $targetPath = Join-Path $Root $target
    if (-not (Test-Path $targetPath)) { continue }

    if ($target -eq 'tools') {
        $hits = rg -n -i --glob '!phase11_no_forbidden_buildref_gate.ps1' $forbidden $targetPath
    }
    else {
        $hits = rg -n -i $forbidden $targetPath
    }

    if ($hits) {
        $allHits += $hits
    }
}

$report = Join-Path $PfPath 'phase11_no_forbidden_buildref_gate.txt'
$status = Join-Path $PfPath 'phase11_no_forbidden_buildref_gate.status.txt'

if ($allHits.Count -gt 0) {
    @(
        "GATE=FAIL"
        "TOKEN=$forbidden"
        "TARGETS=$($targets -join ',')"
        "HITS_BEGIN"
    ) | Out-File $report -Encoding utf8

    $allHits | Out-File $report -Append -Encoding utf8
    "HITS_END" | Out-File $report -Append -Encoding utf8
    "FAIL" | Out-File $status -Encoding utf8
    Write-Output "phase11_gate_fail"
    exit 2
}
else {
    @(
        "GATE=PASS"
        "TOKEN=$forbidden"
        "TARGETS=$($targets -join ',')"
        "NO_HITS"
    ) | Out-File $report -Encoding utf8

    "PASS" | Out-File $status -Encoding utf8
    Write-Output "phase11_gate_pass"
    exit 0
}
