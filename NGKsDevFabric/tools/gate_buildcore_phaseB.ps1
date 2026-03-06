param(
  [Parameter(Mandatory=$true)][string]$ProofDir
)

$ErrorActionPreference='Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
if ((Get-Location).Path -ne $root) { "hey stupid Fucker, wrong window again"; exit 1 }

if (-not $env:NGKS_BUILDCORE_PY) {
  $siblingBuildCorePy = Join-Path (Split-Path $root -Parent) 'NGKsBuildCore\.venv\Scripts\python.exe'
  if (Test-Path $siblingBuildCorePy) {
    $env:NGKS_BUILDCORE_PY = $siblingBuildCorePy
  }
}

if (-not $env:NGKS_GRAPH_EXE) {
  $env:NGKS_GRAPH_EXE = "python -m ngksgraph"
}

if (-not $env:NGKS_GRAPH_PROJECT) {
  $siblingGraphProject = Join-Path (Split-Path $root -Parent) 'NGKsGraph\artifacts\phaseA_sample'
  if (Test-Path (Join-Path $siblingGraphProject "ngksgraph.toml")) {
    $env:NGKS_GRAPH_PROJECT = $siblingGraphProject
  }
}

if (-not $env:NGKS_BUILD_JOBS) {
  $env:NGKS_BUILD_JOBS = "8"
}

$argsList = @("-m", "ngksdevfabric", "build", "--backend", "buildcore", "--target", "hello", "--pf", $ProofDir)
$cmd = "python " + (($argsList | ForEach-Object { if ($_ -match "\s") { '"' + $_ + '"' } else { $_ } }) -join " ")
Set-Content -Path (Join-Path $ProofDir "commands.txt") -Value ($cmd + "`n") -Encoding utf8

$stdoutLog = Join-Path $ProofDir "devfabric_command.log"
$stderrLog = Join-Path $ProofDir "devfabric_command.err.log"
$proc = Start-Process -FilePath "python" -ArgumentList $argsList -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog

if (Test-Path $stdoutLog) { Get-Content -Path $stdoutLog -Encoding utf8 }
if (Test-Path $stderrLog) { Get-Content -Path $stderrLog -Encoding utf8 }
if ($proc.ExitCode -ne 0) { exit $proc.ExitCode }

$status = "FAIL"
$runDir = Join-Path $ProofDir "run_buildcore"
$gatePath = Join-Path $ProofDir "gate_summary.txt"
if (Test-Path $gatePath) {
  $gateText = Get-Content -Path $gatePath -Raw -Encoding utf8
  if ($gateText -match "status=PASS") {
    $status = "PASS"
  }
}

Set-Content -Path (Join-Path $ProofDir "phaseB_gate.txt") -Value ("status=" + $status + "`nrun_dir=" + $runDir) -Encoding utf8

if ($status -ne "PASS") {
  exit 1
}

Write-Host "DEVFABRIC_PHASE_B_GATE=PASS"