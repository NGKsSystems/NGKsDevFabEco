param(
  [string]$Target,
  [string]$PfPath,
  [string]$BackupRoot
)

$ErrorActionPreference='Stop'
$invokeCwd = (Get-Location).Path

# =========================
# NGKsDevFabric — E2E Smoke (real)
# Prefers ngk.ps1 build; falls back to phase12_runner.ps1
# =========================

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
if((Get-Location).Path -ne $root){ "hey stupid Fucker, wrong window again"; exit 1 }

if ([string]::IsNullOrWhiteSpace($Target)) {
  $targetResolved = $null
  try {
    $gitTop = (& git -C $invokeCwd rev-parse --show-toplevel 2>$null)
    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($gitTop)) { $targetResolved = $gitTop.Trim() }
  } catch {}
  if ([string]::IsNullOrWhiteSpace($targetResolved)) { $targetResolved = $invokeCwd }
  $Target = $targetResolved
}

if(-not (Test-Path $Target)){ throw "Target path missing: $Target" }
$profile = Join-Path $Target '.ngk\profile.json'
if(-not (Test-Path $profile)){ throw "Missing target profile.json: $profile" }

$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$pf = $null
if (-not [string]::IsNullOrWhiteSpace($PfPath)) {
  $pf = [System.IO.Path]::GetFullPath($PfPath)
} else {
  $backup = if (-not [string]::IsNullOrWhiteSpace($BackupRoot)) { $BackupRoot } else { $env:NGKS_BACKUP_ROOT }
  if ([string]::IsNullOrWhiteSpace($backup)) {
    throw "Missing required -BackupRoot (or NGKS_BACKUP_ROOT) when -PfPath is not provided"
  }
  if (!(Test-Path $backup)) { New-Item -ItemType Directory -Force -Path $backup | Out-Null }
  $repoName = Split-Path -Leaf $Target
  $pf = Join-Path $backup (Join-Path $repoName (Join-Path '_proof' ("fabric_e2e_smoke_"+$ts)))
}
New-Item -ItemType Directory -Force -Path $pf | Out-Null
Set-Content (Join-Path (Join-Path $root '_proof') 'CURRENT_PF_E2E_SMOKE.txt') $pf -Encoding utf8

git status --short --branch | Out-File (Join-Path $pf '01_git_status_pre.txt') -Encoding utf8
git rev-parse HEAD          | Out-File (Join-Path $pf '02_git_head_pre.txt')   -Encoding utf8
git log -1 --oneline        | Out-File (Join-Path $pf '03_git_last_commit.txt') -Encoding utf8

$ngk    = Join-Path $root 'tools\ngk.ps1'
$runner = Join-Path $root 'tools\phase12_runner.ps1'

if(Test-Path $ngk){
  (& $ngk --help 2>&1) | Out-File (Join-Path $pf '10_ngk_help.txt') -Encoding utf8
}else{
  "MISSING: tools\ngk.ps1" | Out-File (Join-Path $pf '10_ngk_help.txt') -Encoding utf8
}

$replayPf = Join-Path $pf 'replay_pf'
New-Item -ItemType Directory -Force -Path $replayPf | Out-Null

$ran = $false
try {
  if(Test-Path $ngk){
    $helpTxt = Get-Content (Join-Path $pf '10_ngk_help.txt') -Raw
    if($helpTxt -match '(?i)\bbuild\b'){
      # Attempt ngk.ps1 build in-process (will only work if ngk.ps1 can accept passthrough args safely)
      $callArgs = @('build','-Target',$Target,'-PfPath',$replayPf)
      (& $ngk @callArgs 2>&1) | Tee-Object -FilePath (Join-Path $pf '20_run_out.txt')
      $ran = $true
    }
  }
} catch {
  "ngk.ps1 invocation failed; falling back. error=$($_.Exception.Message)" |
    Out-File (Join-Path $pf '19_ngk_failed.txt') -Encoding utf8
  $ran = $false
}

if(-not $ran){
  if(-not (Test-Path $runner)){ throw "Missing fallback runner: $runner" }
  powershell -NoProfile -ExecutionPolicy Bypass -File $runner -Target $Target -PfPath $replayPf 2>&1 |
    Tee-Object -FilePath (Join-Path $pf '20_run_out.txt')
}

$ec = $LASTEXITCODE
Set-Content (Join-Path $pf '21_exitcode.txt') ([string]$ec) -Encoding utf8
if($ec -ne 0){ throw "E2E FAIL: exit=$ec (see 20_run_out.txt)" }

$expect = @(
  (Join-Path $replayPf 'probe_report.json'),
  (Join-Path $replayPf 'profile_write_receipt.json'),
  (Join-Path $replayPf 'run_build')
)

$missing=@()
foreach($p in $expect){ if(-not (Test-Path $p)){ $missing += $p } }
$missing | Out-File (Join-Path $pf '30_missing_expected_files.txt') -Encoding utf8
if($missing.Count -gt 0){
  throw ("E2E FAIL: missing expected outputs: " + ($missing -join "; "))
}

@(
  "E2E_SMOKE=PASS"
  ("PF=" + $pf)
  ("exit=" + $ec)
  ("runner=" + ($(if($ran){'ngk.ps1 build'}else{'phase12_runner.ps1'})))
  "NO PUSH performed."
) | Out-File (Join-Path $pf 'E2E_SMOKE_REPORT.txt') -Encoding utf8

Write-Output ("E2E_SMOKE_DONE PF=" + $pf)
Write-Output "NO PUSH performed."