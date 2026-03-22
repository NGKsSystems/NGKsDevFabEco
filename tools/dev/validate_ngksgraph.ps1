# Developer workflow entrypoint for NGKsGraph baseline regression validation.

param(
    [string]$BaselinePath = "",
    [string]$GatePath = "",
    [string]$InjectRegressionCapability = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = "C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco"
$workflow = Join-Path $repoRoot "tools\regression\run_ngksgraph_regression_gate.ps1"

if (-not (Test-Path $workflow)) {
    Write-Error "WORKFLOW_ENTRY_MISSING: $workflow"
    exit 1
}

if ($InjectRegressionCapability) {
    & $workflow -RepoRoot $repoRoot -BaselinePath $BaselinePath -GatePath $GatePath -InjectRegressionCapability $InjectRegressionCapability
}
else {
    & $workflow -RepoRoot $repoRoot -BaselinePath $BaselinePath -GatePath $GatePath
}

exit $LASTEXITCODE
