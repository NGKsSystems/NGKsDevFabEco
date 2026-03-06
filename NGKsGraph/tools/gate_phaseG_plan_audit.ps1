param(
  [Parameter(Mandatory=$true)][string]$ProofDir
)

$ErrorActionPreference='Stop'

$root="C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph"
Set-Location $root
if ((Get-Location).Path -ne $root) { "hey stupid Fucker, wrong window again"; exit 1 }

$sample = Join-Path $root "artifacts\phaseA_sample"
if (-not (Test-Path (Join-Path $sample "ngksgraph.toml"))) {
  "sample target missing: $sample" | Set-Content -Path (Join-Path $ProofDir "BLOCKER.txt")
  exit 2
}

"PHASE_G_GATE_START $(Get-Date -Format o)" | Add-Content -Path (Join-Path $ProofDir "commands.txt")
"python -m ngksgraph planaudit --project $sample --profile debug --target hello" | Add-Content -Path (Join-Path $ProofDir "commands.txt")

$stdoutLog = Join-Path $ProofDir "phaseG_planaudit_stdout.log"
$stderrLog = Join-Path $ProofDir "phaseG_planaudit_stderr.log"
$proc = Start-Process -FilePath "python" -ArgumentList @("-m","ngksgraph","planaudit","--project",$sample,"--profile","debug","--target","hello") -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog

if (Test-Path $stdoutLog) { Get-Content -Path $stdoutLog }
if (Test-Path $stderrLog) { Get-Content -Path $stderrLog }

$reportPath = Join-Path $sample "artifacts\plan_audit_report.json"
if (-not (Test-Path $reportPath)) {
  "PHASE_G_GATE=FAIL`nREASON=report_missing" | Set-Content -Path (Join-Path $ProofDir "phaseG_gate.txt")
  exit 1
}

$report = Get-Content -Path $reportPath -Raw | ConvertFrom-Json
$ok = $true
$reason = @()

if ($proc.ExitCode -ne 0) { $ok = $false; $reason += "planaudit_exit_$($proc.ExitCode)" }
if ([int]$report.duplicate_output_paths -ne 0) { $ok = $false; $reason += "duplicate_output_paths_nonzero" }
if ([int]$report.orphan_deps -ne 0) { $ok = $false; $reason += "orphan_deps_nonzero" }

Copy-Item -Force $reportPath (Join-Path $ProofDir "plan_audit_report.json")
$txtPath = Join-Path $sample "artifacts\plan_audit_report.txt"
if (Test-Path $txtPath) { Copy-Item -Force $txtPath (Join-Path $ProofDir "plan_audit_report.txt") }

if ($ok) {
  "PHASE_G_GATE=PASS" | Set-Content -Path (Join-Path $ProofDir "phaseG_gate.txt")
  "PHASE_G_PASS" | Set-Content -Path (Join-Path $ProofDir "phaseG_result.txt")
  Write-Host "PHASE_G_GATE=PASS"
  Write-Host "PHASE_G_PASS"
  exit 0
}

("PHASE_G_GATE=FAIL`nREASON=" + ($reason -join ";")) | Set-Content -Path (Join-Path $ProofDir "phaseG_gate.txt")
Write-Host "PHASE_G_GATE=FAIL"
exit 1
