# Wrapper entrypoint for NGKsGraph baseline regression gate
# Provides workflow-oriented preflight/post-run output and strict exit propagation.

param(
    [string]$RepoRoot = "C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco",
    [string]$BaselinePath = "",
    [string]$GatePath = "",
    [string]$InjectRegressionCapability = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Text)
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[workflow][$ts] $Text"
}

function Resolve-LatestProofFolder {
    param(
        [string]$Root,
        [string]$Prefix
    )

    $proofRoot = Join-Path $Root "_proof"
    if (-not (Test-Path $proofRoot)) {
        return $null
    }

    $dir = Get-ChildItem -Path $proofRoot -Directory -Filter "$Prefix*" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if ($null -eq $dir) {
        return $null
    }

    return $dir.FullName
}

$gateRunner = Join-Path $RepoRoot "tools\regression\ngksgraph_regression_gate.ps1"
if (-not (Test-Path $gateRunner)) {
    Write-Error "GATE_RUNNER_MISSING: $gateRunner"
    exit 1
}

if (-not $BaselinePath) {
    $BaselinePath = Resolve-LatestProofFolder -Root $RepoRoot -Prefix "ngksgraph_cert_baseline_v1_"
}
if (-not $GatePath) {
    $GatePath = Resolve-LatestProofFolder -Root $RepoRoot -Prefix "ngksgraph_regression_gate_"
}

Write-Step "Preflight start"
Write-Step "RepoRoot=$RepoRoot"
Write-Step "GateRunner=$gateRunner"
Write-Step "BaselinePath=$BaselinePath"
Write-Step "GatePath=$GatePath"
if ($InjectRegressionCapability) {
    Write-Step "InjectRegressionCapability=$InjectRegressionCapability"
}

if (-not $BaselinePath -or -not (Test-Path $BaselinePath)) {
    Write-Error "BASELINE_PATH_INVALID: $BaselinePath"
    exit 1
}
if (-not $GatePath -or -not (Test-Path $GatePath)) {
    Write-Error "GATE_PATH_INVALID: $GatePath"
    exit 1
}

$reportPath = Join-Path $GatePath "gate_execution_report.json"

try {
    if ($InjectRegressionCapability) {
        & $gateRunner -BaselinePath $BaselinePath -GatePath $GatePath -InjectRegressionCapability $InjectRegressionCapability
    }
    else {
        & $gateRunner -BaselinePath $BaselinePath -GatePath $GatePath
    }

    $code = $LASTEXITCODE
}
catch {
    Write-Host "[workflow][ERROR] Gate invocation exception: $($_.Exception.Message)"
    exit 1
}

$verdict = "UNKNOWN"
$reason = ""
if (Test-Path $reportPath) {
    try {
        $report = Get-Content $reportPath -Raw | ConvertFrom-Json
        $verdict = [string]$report.gate_verdict
        $reason = [string]$report.gate_reason
    }
    catch {
        $verdict = "UNPARSEABLE"
        $reason = "Could not parse gate_execution_report.json"
    }
}

Write-Step "Post-run summary"
Write-Step "ReportPath=$reportPath"
Write-Step "GateProofPath=$GatePath"
Write-Step "GateVerdict=$verdict"
Write-Step "GateReason=$reason"
Write-Step "ExitCode=$code"

if ($code -ne 0) {
    exit $code
}

if ($verdict -ne "PASS") {
    Write-Host "[workflow][ERROR] Fail-closed: non-PASS verdict with zero exit code"
    exit 1
}

exit 0
