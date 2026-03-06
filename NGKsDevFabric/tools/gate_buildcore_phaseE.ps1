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

$runDir = Join-Path $ProofDir "run_phaseE"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

"PHASE_E_GATE_START $(Get-Date -Format o)" | Add-Content -Path (Join-Path $ProofDir "commands.txt") -Encoding utf8
"python -m ngksdevfabric build --backend buildcore --target hello --pf $ProofDir" | Add-Content -Path (Join-Path $ProofDir "commands.txt") -Encoding utf8

foreach ($name in @("NGKS_BUILDCORE_PY","NGKS_GRAPH_EXE","NGKS_GRAPH_PROJECT","NGKS_BUILD_JOBS")) {
  Remove-Item "Env:$name" -ErrorAction SilentlyContinue
}
$env:NGKS_REQUIRE_DIRECT_MSVC_CAPTURE='1'

$stdoutLog = Join-Path $ProofDir "phaseE_devfabric_stdout.log"
$stderrLog = Join-Path $ProofDir "phaseE_devfabric_stderr.log"

$proc = Start-Process -FilePath "python" -ArgumentList @("-m","ngksdevfabric","build","--backend","buildcore","--target","hello","--pf",$ProofDir) -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog

if (Test-Path $stdoutLog) { Get-Content -Path $stdoutLog -Encoding utf8 }
if (Test-Path $stderrLog) { Get-Content -Path $stderrLog -Encoding utf8 }

$gatePath = Join-Path $ProofDir "gate_summary.txt"
$bootstrapPath = Join-Path $ProofDir "msvc_bootstrap.txt"
$captureCmdPath = Join-Path $ProofDir "msvc_capture_env.cmd"
$captureOutPath = Join-Path $ProofDir "msvc_capture_stdout.txt"
$wherePath = Join-Path $ProofDir "where_cl.txt"

$ok = $true
$reason = @()

if ($proc.ExitCode -ne 0) { $ok = $false; $reason += "devfabric_exit_$($proc.ExitCode)" }
if (-not (Test-Path $gatePath)) { $ok = $false; $reason += "gate_summary_missing" }
if (-not (Test-Path $bootstrapPath)) { $ok = $false; $reason += "msvc_bootstrap_missing" }
if (-not (Test-Path $captureCmdPath)) { $ok = $false; $reason += "msvc_capture_env_cmd_missing" }
if (-not (Test-Path $captureOutPath)) { $ok = $false; $reason += "msvc_capture_stdout_missing" }
if (-not (Test-Path $wherePath)) { $ok = $false; $reason += "where_cl_missing" }

if ($ok) {
  $gateText = Get-Content -Path $gatePath -Raw -Encoding utf8
  $bootText = Get-Content -Path $bootstrapPath -Raw -Encoding utf8
  $whereText = Get-Content -Path $wherePath -Raw -Encoding utf8

  if ($gateText -notmatch "status=PASS") { $ok = $false; $reason += "gate_not_pass" }
  if ($bootText -notmatch "direct_capture=YES") { $ok = $false; $reason += "direct_capture_not_yes" }
  if ($bootText -notmatch "fallback_used=NO") { $ok = $false; $reason += "fallback_not_no" }
  if ($whereText -notmatch "(?i)cl\.exe") { $ok = $false; $reason += "where_cl_missing_cl_exe" }
}

if ($ok) {
  "PHASE_E_GATE=PASS" | Set-Content -Path (Join-Path $ProofDir "phaseE_gate.txt") -Encoding utf8
  "PHASE_E_PASS" | Set-Content -Path (Join-Path $ProofDir "phaseE_result.txt") -Encoding utf8
  Write-Host "PHASE_E_GATE=PASS"
  Write-Host "PHASE_E_PASS"
  exit 0
}

("PHASE_E_GATE=FAIL`nREASON=" + ($reason -join ";")) | Set-Content -Path (Join-Path $ProofDir "phaseE_gate.txt") -Encoding utf8
Write-Host "PHASE_E_GATE=FAIL"
exit 1
