param(
  [Parameter(Mandatory=$true)][string]$ProofDir
)

$ErrorActionPreference='Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
if ((Get-Location).Path -ne $root) { "hey stupid Fucker, wrong window again"; exit 1 }

"PHASE_F_GATE_START $(Get-Date -Format o)" | Add-Content -Path (Join-Path $ProofDir "commands.txt")
"python -m ngksdevfabric doctor --pf $ProofDir" | Add-Content -Path (Join-Path $ProofDir "commands.txt")

foreach ($name in @("NGKS_BUILDCORE_PY","NGKS_GRAPH_EXE","NGKS_GRAPH_PROJECT","NGKS_BUILD_JOBS","NGKS_REQUIRE_DIRECT_MSVC_CAPTURE")) {
  Remove-Item "Env:$name" -ErrorAction SilentlyContinue
}

$stdoutLog = Join-Path $ProofDir "phaseF_doctor_stdout.log"
$stderrLog = Join-Path $ProofDir "phaseF_doctor_stderr.log"
$proc = Start-Process -FilePath "python" -ArgumentList @("-m","ngksdevfabric","doctor","--pf",$ProofDir) -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog

if (Test-Path $stdoutLog) { Get-Content -Path $stdoutLog }
if (Test-Path $stderrLog) { Get-Content -Path $stderrLog }

$reportPath = Join-Path $ProofDir "toolchain_report.json"
$ok = $true
$reason = @()

if ($proc.ExitCode -ne 0) { $ok = $false; $reason += "doctor_exit_$($proc.ExitCode)" }
if (-not (Test-Path $reportPath)) { $ok = $false; $reason += "report_missing" }

if ($ok) {
  $report = Get-Content -Path $reportPath -Raw | ConvertFrom-Json
  if ([string]::IsNullOrWhiteSpace($report.cl_path)) { $ok = $false; $reason += "cl_path_empty" }
  if ([string]::IsNullOrWhiteSpace($report.graph_entrypoint)) { $ok = $false; $reason += "graph_entrypoint_empty" }
  if ([string]::IsNullOrWhiteSpace($report.buildcore_entrypoint)) { $ok = $false; $reason += "buildcore_entrypoint_empty" }
}

if ($ok) {
  "PHASE_F_GATE=PASS" | Set-Content -Path (Join-Path $ProofDir "phaseF_gate.txt")
  "PHASE_F_PASS" | Set-Content -Path (Join-Path $ProofDir "phaseF_result.txt")
  Write-Host "PHASE_F_GATE=PASS"
  Write-Host "PHASE_F_PASS"
  exit 0
}

("PHASE_F_GATE=FAIL`nREASON=" + ($reason -join ";")) | Set-Content -Path (Join-Path $ProofDir "phaseF_gate.txt")
Write-Host "PHASE_F_GATE=FAIL"
exit 1
