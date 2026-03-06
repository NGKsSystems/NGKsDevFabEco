param(
  [Parameter(Mandatory=$true)][string]$ProofDir
)

$ErrorActionPreference='Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
if ((Get-Location).Path -ne $root) { "hey stupid Fucker, wrong window again"; exit 1 }

if (-not (Test-Path $ProofDir)) {
  New-Item -ItemType Directory -Force -Path $ProofDir | Out-Null
}

$runDir = Join-Path $ProofDir "run_phaseD"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

"PHASE_D_GATE_START $(Get-Date -Format o)" | Add-Content -Path (Join-Path $ProofDir "commands.txt") -Encoding utf8
"python -m ngksdevfabric build --backend buildcore --target hello --pf $ProofDir" | Add-Content -Path (Join-Path $ProofDir "commands.txt") -Encoding utf8

foreach ($name in @("NGKS_BUILDCORE_PY","NGKS_GRAPH_EXE","NGKS_GRAPH_PROJECT","NGKS_BUILD_JOBS")) {
  Remove-Item "Env:$name" -ErrorAction SilentlyContinue
}

$stdoutLog = Join-Path $ProofDir "phaseD_devfabric_stdout.log"
$stderrLog = Join-Path $ProofDir "phaseD_devfabric_stderr.log"

$proc = Start-Process -FilePath "python" -ArgumentList @("-m","ngksdevfabric","build","--backend","buildcore","--target","hello","--pf",$ProofDir) -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog

if (Test-Path $stdoutLog) { Get-Content -Path $stdoutLog -Encoding utf8 }
if (Test-Path $stderrLog) { Get-Content -Path $stderrLog -Encoding utf8 }

$gatePath = Join-Path $ProofDir "gate_summary.txt"
$msvcLog = Join-Path $ProofDir "msvc_bootstrap.txt"
$whereLog = Join-Path $ProofDir "where_cl.txt"
$planValidation = Join-Path $ProofDir "plan_validation.txt"

$ok = $true
$reason = @()

if ($proc.ExitCode -ne 0) { $ok = $false; $reason += "devfabric_exit_$($proc.ExitCode)" }
if (-not (Test-Path $gatePath)) { $ok = $false; $reason += "gate_summary_missing" }
if (-not (Test-Path $msvcLog)) { $ok = $false; $reason += "msvc_bootstrap_missing" }
if (-not (Test-Path $whereLog)) { $ok = $false; $reason += "where_cl_missing" }
if (-not (Test-Path $planValidation)) { $ok = $false; $reason += "plan_validation_missing" }

if ($ok) {
  $gateText = Get-Content -Path $gatePath -Raw -Encoding utf8
  if ($gateText -notmatch "status=PASS") { $ok = $false; $reason += "gate_not_pass" }

  $planText = Get-Content -Path $planValidation -Raw -Encoding utf8
  if ($planText -notmatch "status=PASS") { $ok = $false; $reason += "plan_validation_not_pass" }
}

if ($ok) {
  "PHASE_D_GATE=PASS" | Set-Content -Path (Join-Path $ProofDir "phaseD_gate.txt") -Encoding utf8
  "PHASE_D_PASS" | Set-Content -Path (Join-Path $ProofDir "phaseD_result.txt") -Encoding utf8
  Write-Host "PHASE_D_GATE=PASS"
  Write-Host "PHASE_D_PASS"
  exit 0
}

("PHASE_D_GATE=FAIL`nREASON=" + ($reason -join ";")) | Set-Content -Path (Join-Path $ProofDir "phaseD_gate.txt") -Encoding utf8
Write-Host "PHASE_D_GATE=FAIL"
exit 1
