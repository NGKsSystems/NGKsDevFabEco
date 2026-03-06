$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$example = Join-Path $root "examples/qt_msvc_real"
$proofRoot = Join-Path $root "proof"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$proof = Join-Path $proofRoot ("phase11b_painkiller_" + $stamp)
$py = Join-Path $root ".venv/Scripts/python.exe"
if (-not (Test-Path $py)) { $py = "python" }
New-Item -ItemType Directory -Path $proof -Force | Out-Null

function Run-Step {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string]$OutFile,
        [switch]$AllowFail
    )

    $outfilePath = Join-Path $proof $OutFile
    Push-Location $root
    try {
        $wrapped = 'set "PYTHONPATH=' + $root + '" && ' + $Command
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $result = & cmd.exe /d /s /c $wrapped 2>&1
        }
        finally {
            $ErrorActionPreference = $prevEap
        }
        $exitCode = $LASTEXITCODE
        "# CMD: $Command" | Out-File -FilePath $outfilePath -Encoding utf8
        "# EXIT: $exitCode" | Out-File -FilePath $outfilePath -Append -Encoding utf8
        $result | Out-File -FilePath $outfilePath -Append -Encoding utf8
        if (-not $AllowFail -and $exitCode -ne 0) {
            throw "Step '$Name' failed with exit code $exitCode"
        }
    }
    finally {
        Pop-Location
    }
}

$zipPath = Join-Path $proofRoot ("phase11b_painkiller_" + $stamp + ".zip")
$gate = "FAIL"
try {
    Run-Step -Name "git_status" -Command "git status" -OutFile "01_git_status.txt" -AllowFail
    Run-Step -Name "git_log" -Command "git log -1 --oneline" -OutFile "02_git_log.txt" -AllowFail
    Run-Step -Name "pytest_full" -Command ('"' + $py + '" -m pytest -q') -OutFile "03_pytest_full.txt"

    Run-Step -Name "run_debug" -Command ('"' + $py + '" -m ngksgraph run --project examples/qt_msvc_real --profile debug --clear-cache') -OutFile "04_run_debug.txt"
    Run-Step -Name "run_release" -Command ('"' + $py + '" -m ngksgraph run --project examples/qt_msvc_real --profile release --clear-cache') -OutFile "05_run_release.txt"

    Run-Step -Name "doctor_compdb" -Command ('"' + $py + '" -m ngksgraph doctor --project examples/qt_msvc_real --compdb --profile debug') -OutFile "06_doctor_compdb_debug.txt"
    Run-Step -Name "doctor_graph" -Command ('"' + $py + '" -m ngksgraph doctor --project examples/qt_msvc_real --graph --profile debug') -OutFile "07_doctor_graph_debug.txt"
    Run-Step -Name "doctor_profiles" -Command ('"' + $py + '" -m ngksgraph doctor --project examples/qt_msvc_real --profiles') -OutFile "08_doctor_profiles.txt"

    $debugReport = Join-Path $example "build/debug/ngksgraph_build_report.json"
    $releaseReport = Join-Path $example "build/release/ngksgraph_build_report.json"
    if (-not (Test-Path $debugReport)) { throw "Missing $debugReport" }
    if (-not (Test-Path $releaseReport)) { throw "Missing $releaseReport" }

    Copy-Item $debugReport (Join-Path $proof "09_report_debug.json") -Force
    Copy-Item $releaseReport (Join-Path $proof "10_report_release.json") -Force

    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
    Compress-Archive -Path (Join-Path $proof "*") -DestinationPath $zipPath -Force
    $gate = "PASS"
}
catch {
    Write-Host $_
    throw
}
finally {
    if (Test-Path (Join-Path $proof "*")) {
        if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
        Compress-Archive -Path (Join-Path $proof "*") -DestinationPath $zipPath -Force
    }
    Write-Host "PF=$proof"
    Write-Host "ZIP=$zipPath"
    Write-Host "GATE=$gate"
}
