$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$proofRoot = Join-Path $repoRoot "_proof"

if (-not (Test-Path $proofRoot)) {
    Write-Output "proof_root_missing=$proofRoot"
    exit 0
}

$reports = Get-ChildItem -Path $proofRoot -Recurse -File -Filter "12_final_contract_report.txt"
$updated = 0

foreach ($report in $reports) {
    $packetFolder = $report.Directory.FullName
    $canonical = (Resolve-Path -Path $packetFolder).Path

    $lines = Get-Content -Path $report.FullName -Encoding UTF8
    $out = New-Object System.Collections.Generic.List[string]
    $seenProofFolder = $false

    foreach ($line in $lines) {
        if ($line -match '^proof_folder=') {
            if (-not $seenProofFolder) {
                $out.Add("proof_folder=$canonical")
                $seenProofFolder = $true
            }
            continue
        }
        if ($line -match '^proof_folder_canonical=') {
            continue
        }
        $out.Add($line)
    }

    if (-not $seenProofFolder) {
        $out.Add("proof_folder=$canonical")
    }

    [System.IO.File]::WriteAllLines($report.FullName, $out, [System.Text.Encoding]::UTF8)
    $updated += 1
}

Write-Output "proof_reports_found=$($reports.Count)"
Write-Output "proof_reports_updated=$updated"
