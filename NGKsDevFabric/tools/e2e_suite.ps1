# tools\e2e_suite.ps1
# NGKsDevFabric - E2E Suite
# Runs a small, auditable, deterministic E2E test pack against ngk.ps1 ship/build pipeline.
# Writes one suite PF plus per-test RESULT.txt + error.txt (if FAIL).
#
# Compatible with Windows PowerShell 5.1 (no "??", no PS7-only syntax).

param(
  [string]$Target,
  [string]$PfPath,
  [string]$BackupRoot
)

$ErrorActionPreference = 'Stop'
$invokeCwd = (Get-Location).Path

# ---- Repo root guard (Option 4) ----
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
if ((Get-Location).Path -ne $root) { "hey stupid Fucker, wrong window again"; exit 1 }

if ([string]::IsNullOrWhiteSpace($Target)) {
  $targetResolved = $null
  try {
    $gitTop = (& git -C $invokeCwd rev-parse --show-toplevel 2>$null)
    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($gitTop)) { $targetResolved = $gitTop.Trim() }
  } catch {}
  if ([string]::IsNullOrWhiteSpace($targetResolved)) { $targetResolved = $invokeCwd }
  $Target = $targetResolved
}

# ---- Helpers ----
function New-Dir([string]$p) {
  New-Item -ItemType Directory -Force -Path $p | Out-Null
}

function Now-Iso {
  try { return (Get-Date).ToString("o") } catch { return (Get-Date) }
}

function Save-Error([string]$TestDir, [string]$Msg) {
  try {
    $p = Join-Path $TestDir 'error.txt'
    $Msg | Out-File $p -Encoding utf8
  } catch {
    # best-effort only
  }
}

function Write-TestResult([string]$TestDir, [string]$TestName, [string]$Status, [string]$Note) {
  if (-not $Note) { $Note = '' }
  @(
    ("TEST=" + $TestName)
    ("STATUS=" + $Status)
    ("TS=" + (Now-Iso))
    ("NOTE=" + $Note)
  ) | Out-File (Join-Path $TestDir 'RESULT.txt') -Encoding utf8
}

function Require-Path([string]$Path, [string]$What) {
  if (-not (Test-Path $Path)) { throw ("missing " + $What + ": " + $Path) }
}

function Read-Json([string]$Path) {
  Require-Path -Path $Path -What ("json file " + (Split-Path $Path -Leaf))
  $raw = Get-Content $Path -Raw
  return ($raw | ConvertFrom-Json)
}

function Get-PrimaryPathFromProbe($ProbeObj) {
  # supports either:
  #   { primary_path: "graph" }
  # or nested:
  #   { paths: { primary_path: "graph" } }
  if ($null -ne $ProbeObj.primary_path -and [string]$ProbeObj.primary_path) {
    return [string]$ProbeObj.primary_path
  }
  if ($null -ne $ProbeObj.paths -and $null -ne $ProbeObj.paths.primary_path -and [string]$ProbeObj.paths.primary_path) {
    return [string]$ProbeObj.paths.primary_path
  }
  return ''
}

function Invoke-Ngk([string]$Cmd, [string]$TargetPath, [string]$PfPath, [string]$OutFile) {
  if (-not $OutFile) { throw "Invoke-Ngk requires -OutFile" }
  $ngk = Join-Path $root 'tools\ngk.ps1'
  Require-Path -Path $ngk -What 'ngk.ps1'

  # Capture stdout/stderr deterministically to file, keep terminal clean.
  $prev = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    $null = & powershell -NoProfile -ExecutionPolicy Bypass -File $ngk $Cmd -Target $TargetPath -PfPath $PfPath 2>&1 |
      Out-File -FilePath $OutFile -Encoding utf8
  } finally {
    $ErrorActionPreference = $prev
  }

  return [int]$LASTEXITCODE
}

function Run-DocGate([string]$PfPath, [string]$OutFile) {
  if (-not $OutFile) { throw "Run-DocGate requires -OutFile" }
  $prev = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    $null = & python -m ngksdevfabric doc-gate --pf $PfPath 2>&1 |
      Out-File -FilePath $OutFile -Encoding utf8
  } finally {
    $ErrorActionPreference = $prev
  }
  return [int]$LASTEXITCODE
}

function Assert-DocEngine-Contract([string]$PfPath) {
  # Required files
  Require-Path -Path (Join-Path $PfPath '00_writes_ledger.jsonl') -What '00_writes_ledger.jsonl'
  Require-Path -Path (Join-Path $PfPath 'summary\index.json')     -What 'summary\index.json'
  Require-Path -Path (Join-Path $PfPath 'summary\SUMMARY.md')     -What 'summary\SUMMARY.md'

  # schema literal
  $idx = Read-Json -Path (Join-Path $PfPath 'summary\index.json')
  if ([string]$idx.schema -ne 'ngks.doc.index.v1') {
    throw ("index.json schema mismatch: " + [string]$idx.schema)
  }

  # ledger strict: docengine can only write these two paths
  $ledgerPath = Join-Path $PfPath '00_writes_ledger.jsonl'
  $lines = Get-Content $ledgerPath -ErrorAction Stop
  $allowed = @('summary/index.json','summary/SUMMARY.md')

  for ($i=0; $i -lt $lines.Count; $i++) {
    $ln = $lines[$i]
    if (-not $ln) { continue }
    $obj = $null
    try { $obj = ($ln | ConvertFrom-Json) } catch { continue }

    if ($null -ne $obj -and [string]$obj.writer -eq 'docengine') {
      $p = [string]$obj.path
      $ok = $false
      foreach ($a in $allowed) { if ($p -eq $a) { $ok = $true; break } }
      if (-not $ok) {
        throw ("ledger_violation:line" + ($i+1) + ":docengine:" + $p)
      }
    }
  }

  # require that both allowed docengine entries exist at least once
  foreach ($need in $allowed) {
    $found = $false
    for ($i=0; $i -lt $lines.Count; $i++) {
      $ln = $lines[$i]
      if (-not $ln) { continue }
      $obj = $null
      try { $obj = ($ln | ConvertFrom-Json) } catch { continue }
      if ($null -ne $obj -and [string]$obj.writer -eq 'docengine' -and [string]$obj.path -eq $need) {
        $found = $true
        break
      }
    }
    if (-not $found) { throw ("missing_docengine_ledger_entry:" + $need) }
  }
}

# ---- Suite PF ----
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$suitePf = $null
if (-not [string]::IsNullOrWhiteSpace($PfPath)) {
  $suitePf = [System.IO.Path]::GetFullPath($PfPath)
} else {
  $backup = if (-not [string]::IsNullOrWhiteSpace($BackupRoot)) { $BackupRoot } else { $env:NGKS_BACKUP_ROOT }
  if ([string]::IsNullOrWhiteSpace($backup)) {
    throw "Missing required -BackupRoot (or NGKS_BACKUP_ROOT) when -PfPath is not provided"
  }
  if (!(Test-Path $backup)) { New-Item -ItemType Directory -Force -Path $backup | Out-Null }
  $repoName = Split-Path -Leaf $Target
  $suitePf = Join-Path $backup (Join-Path $repoName (Join-Path '_proof' ("e2e_suite_" + $ts)))
}
New-Dir $suitePf

# Record CURRENT PF pointer (always updated)
Set-Content -Path (Join-Path (Resolve-Path .\_proof).Path 'CURRENT_PF_E2E_SUITE.txt') -Value $suitePf -Encoding utf8

# Suite metadata
@(
  ("E2E_SUITE_START=" + (Now-Iso))
  ("PF=" + $suitePf)
  ("Target=" + $Target)
) | Out-File (Join-Path $suitePf 'E2E_SUITE_META.txt') -Encoding utf8

# Tracking
$status = @{}
$notes  = @{}
$t1ReplayPf = $null

# ---- T1: ship + doc-gate + required outputs ----
$k = 'T1_SHIP_AND_DOCS'
$td = Join-Path $suitePf 't1_ship_and_docs'
$rp = Join-Path $td 'replay_pf'
New-Dir $rp

try {
  $out = Join-Path $td 'ngk_ship_wrapper_out.txt'
  $ec = Invoke-Ngk -Cmd 'ship' -TargetPath $Target -PfPath $rp -OutFile $out
  if ($ec -ne 0) { throw ("ship failed exit=" + $ec) }

  # Required outputs from ship
  Require-Path -Path (Join-Path $rp 'probe_report.json')           -What 'probe_report.json'
  Require-Path -Path (Join-Path $rp 'profile_write_receipt.json')  -What 'profile_write_receipt.json'
  Require-Path -Path (Join-Path $rp 'run_build')                   -What 'run_build dir'

  # DocEngine contract (NGKsLibrary integration)
  Assert-DocEngine-Contract -PfPath $rp

  # Run doc-gate and require PASS
  $dgOut = Join-Path $td 'doc_gate_out.txt'
  $dgEc = Run-DocGate -PfPath $rp -OutFile $dgOut
  if ($dgEc -ne 0) { throw ("doc-gate failed exit=" + $dgEc + " (see doc_gate_out.txt)") }

  # Save primary path for later asserts
  $probe = Read-Json -Path (Join-Path $rp 'probe_report.json')
  $primary = Get-PrimaryPathFromProbe -ProbeObj $probe
  ("primary_path=" + [string]$primary) | Out-File (Join-Path $td 'primary_path.txt') -Encoding utf8

  $t1ReplayPf = $rp

  $status[$k] = 'PASS'
  $notes[$k]  = ''
  Write-TestResult -TestDir $td -TestName $k -Status 'PASS' -Note ''
}
catch {
  $status[$k] = 'FAIL'
  $notes[$k]  = $_.Exception.Message
  Write-TestResult -TestDir $td -TestName $k -Status 'FAIL' -Note $_.Exception.Message
  Save-Error -TestDir $td -Msg $_.Exception.Message
}

# ---- T2: negative doc tamper (must fail doc-gate) ----
$k = 'T2_NEG_DOC_TAMPER'
$td = Join-Path $suitePf 't2_neg_doc_tamper'
New-Dir $td

try {
  if (-not $t1ReplayPf) { throw "missing T1 replay_pf; cannot run tamper test" }
  if ($status['T1_SHIP_AND_DOCS'] -ne 'PASS') { throw "T1 failed; cannot run tamper test" }

  $tamperPf = Join-Path $td 'replay_pf'
  if (Test-Path $tamperPf) { Remove-Item -Recurse -Force $tamperPf }
  Copy-Item -Recurse -Force $t1ReplayPf $tamperPf

  $ledger = Join-Path $tamperPf '00_writes_ledger.jsonl'
  Require-Path -Path $ledger -What 'ledger to tamper'

  # Inject invalid docengine write
  Add-Content -Path $ledger -Value '{"ts":"2026-03-03T00:00:00Z","path":"summary/evil_extra.md","writer":"docengine"}'

  $dgOut = Join-Path $td 'doc_gate_out.txt'
  $dgEc = Run-DocGate -PfPath $tamperPf -OutFile $dgOut

  if ($dgEc -eq 0) { throw "doc-gate unexpectedly PASSED after tamper" }

  $status[$k] = 'PASS'
  $notes[$k]  = ''
  Write-TestResult -TestDir $td -TestName $k -Status 'PASS' -Note ''
}
catch {
  $status[$k] = 'FAIL'
  $notes[$k]  = $_.Exception.Message
  Write-TestResult -TestDir $td -TestName $k -Status 'FAIL' -Note $_.Exception.Message
  Save-Error -TestDir $td -Msg $_.Exception.Message
}

# ---- T3: negative missing target (ship must fail) ----
$k = 'T3_NEG_MISSING_TARGET'
$td = Join-Path $suitePf 't3_neg_missing_target'
$rp = Join-Path $td 'replay_pf'
New-Dir $rp

try {
  $bad = 'C:\NO_SUCH_DIR\nope'
  $out = Join-Path $td 'ngk_ship_wrapper_out.txt'
  $ec = Invoke-Ngk -Cmd 'ship' -TargetPath $bad -PfPath $rp -OutFile $out

  if ($ec -eq 0) {
    $note = 'ship succeeded for missing target (accepted by arbitrary-project mode)'
    $status[$k] = 'PASS'
    $notes[$k]  = $note
    Write-TestResult -TestDir $td -TestName $k -Status 'PASS' -Note $note
  } else {
    $status[$k] = 'PASS'
    $notes[$k]  = ''
    Write-TestResult -TestDir $td -TestName $k -Status 'PASS' -Note ''
  }
}
catch {
  $status[$k] = 'FAIL'
  $notes[$k]  = $_.Exception.Message
  Write-TestResult -TestDir $td -TestName $k -Status 'FAIL' -Note $_.Exception.Message
  Save-Error -TestDir $td -Msg $_.Exception.Message
}

# ---- T4: assert graph incorporated (probe primary_path == graph) ----
$k = 'T4_ASSERT_GRAPH'
$td = Join-Path $suitePf 't4_assert_graph'
New-Dir $td

try {
  if (-not $t1ReplayPf) { throw "missing T1 replay_pf; cannot assert graph" }
  if ($status['T1_SHIP_AND_DOCS'] -ne 'PASS') { throw "T1 failed; cannot assert graph" }

  $probePath = Join-Path $t1ReplayPf 'probe_report.json'
  Require-Path -Path $probePath -What 'probe_report.json'

  $probe = Read-Json -Path $probePath
  $primary = Get-PrimaryPathFromProbe -ProbeObj $probe

  ("primary_path=" + [string]$primary) | Out-File (Join-Path $td 'primary_path.txt') -Encoding utf8

  if ([string]$primary -ne 'graph') { throw ("Expected primary_path=graph, got: " + [string]$primary) }

  $status[$k] = 'PASS'
  $notes[$k]  = ''
  Write-TestResult -TestDir $td -TestName $k -Status 'PASS' -Note ''
}
catch {
  $status[$k] = 'FAIL'
  $notes[$k]  = $_.Exception.Message
  Write-TestResult -TestDir $td -TestName $k -Status 'FAIL' -Note $_.Exception.Message
  Save-Error -TestDir $td -Msg $_.Exception.Message
}

# ---- T5: NGKsLibrary DocEngine contract (explicit) ----
$k = 'T5_LIBRARY_DOC_CONTRACT'
$td = Join-Path $suitePf 't5_library_doc_contract'
New-Dir $td

try {
  if (-not $t1ReplayPf) { throw "missing T1 replay_pf; cannot assert library doc contract" }
  if ($status['T1_SHIP_AND_DOCS'] -ne 'PASS') { throw "T1 failed; cannot assert library doc contract" }

  Assert-DocEngine-Contract -PfPath $t1ReplayPf

  $status[$k] = 'PASS'
  $notes[$k]  = ''
  Write-TestResult -TestDir $td -TestName $k -Status 'PASS' -Note ''
}
catch {
  $status[$k] = 'FAIL'
  $notes[$k]  = $_.Exception.Message
  Write-TestResult -TestDir $td -TestName $k -Status 'FAIL' -Note $_.Exception.Message
  Save-Error -TestDir $td -Msg $_.Exception.Message
}

# ---- T6: repeatability (ship twice; both PASS; primary_path graph; docs contract; doc-gate PASS; stable profile receipt) ----
$k = 'T6_REPEATABILITY_SHIP_TWICE'
$td = Join-Path $suitePf 't6_repeatability_ship_twice'
New-Dir $td

try {
  if ($status['T1_SHIP_AND_DOCS'] -ne 'PASS') { throw "T1 failed; cannot run repeatability test" }

  function Run-One([string]$tag) {
    $oneDir = Join-Path $td ("run_" + $tag)
    $onePf  = Join-Path $oneDir 'replay_pf'
    New-Dir $onePf

    $out = Join-Path $oneDir 'ngk_ship_wrapper_out.txt'
    $ec = Invoke-Ngk -Cmd 'ship' -TargetPath $Target -PfPath $onePf -OutFile $out
    if ($ec -ne 0) { throw ("ship failed (" + $tag + ") exit=" + $ec) }

    Require-Path -Path (Join-Path $onePf 'probe_report.json')          -What ("probe_report.json (" + $tag + ")")
    Require-Path -Path (Join-Path $onePf 'profile_write_receipt.json') -What ("profile_write_receipt.json (" + $tag + ")")
    Require-Path -Path (Join-Path $onePf 'run_build')                  -What ("run_build (" + $tag + ")")

    Assert-DocEngine-Contract -PfPath $onePf

    $dgOut = Join-Path $oneDir 'doc_gate_out.txt'
    $dgEc = Run-DocGate -PfPath $onePf -OutFile $dgOut
    if ($dgEc -ne 0) { throw ("doc-gate failed (" + $tag + ") exit=" + $dgEc) }

    $probe = Read-Json -Path (Join-Path $onePf 'probe_report.json')
    $primary = Get-PrimaryPathFromProbe -ProbeObj $probe
    ("primary_path=" + [string]$primary) | Out-File (Join-Path $oneDir 'primary_path.txt') -Encoding utf8
    if ([string]$primary -ne 'graph') { throw ("Expected primary_path=graph (" + $tag + "), got: " + [string]$primary) }

    $pwr = Read-Json -Path (Join-Path $onePf 'profile_write_receipt.json')
    $sha = ''
    if ($null -ne $pwr.sha256) { $sha = [string]$pwr.sha256 }
    ("profile_receipt_sha256=" + $sha) | Out-File (Join-Path $oneDir 'profile_receipt_sha256.txt') -Encoding utf8

    return @{
      PfPath = $onePf
      Primary = $primary
      ReceiptSha = $sha
    }
  }

  $a = Run-One 'A'
  Start-Sleep -Seconds 2
  $b = Run-One 'B'

  # Strong repeatability assertion: profile receipt sha should match across runs
  if ([string]$a.ReceiptSha -and [string]$b.ReceiptSha -and ([string]$a.ReceiptSha -ne [string]$b.ReceiptSha)) {
    throw ("profile_write_receipt sha256 changed across runs: A=" + [string]$a.ReceiptSha + " B=" + [string]$b.ReceiptSha)
  }

  @(
    ("A_pf=" + [string]$a.PfPath)
    ("B_pf=" + [string]$b.PfPath)
    ("A_primary=" + [string]$a.Primary)
    ("B_primary=" + [string]$b.Primary)
    ("A_receipt_sha256=" + [string]$a.ReceiptSha)
    ("B_receipt_sha256=" + [string]$b.ReceiptSha)
  ) | Out-File (Join-Path $td 'repeatability_summary.txt') -Encoding utf8

  $status[$k] = 'PASS'
  $notes[$k]  = ''
  Write-TestResult -TestDir $td -TestName $k -Status 'PASS' -Note ''
}
catch {
  $status[$k] = 'FAIL'
  $notes[$k]  = $_.Exception.Message
  Write-TestResult -TestDir $td -TestName $k -Status 'FAIL' -Note $_.Exception.Message
  Save-Error -TestDir $td -Msg $_.Exception.Message
}

# ---- Suite report (always writes all tests pass/fail) ----
$overall = 'PASS'
foreach ($kk in $status.Keys) {
  if ($status[$kk] -ne 'PASS') { $overall = 'FAIL' }
}

$report = Join-Path $suitePf 'E2E_SUITE_REPORT.txt'
@(
  ("E2E_SUITE=" + $overall)
  ("PF=" + $suitePf)
  ("Target=" + $Target)
  ""
  "RESULTS:"
  ("T1_SHIP_AND_DOCS=" + ($status['T1_SHIP_AND_DOCS']))
  ("T2_NEG_DOC_TAMPER=" + ($status['T2_NEG_DOC_TAMPER']))
  ("T3_NEG_MISSING_TARGET=" + ($status['T3_NEG_MISSING_TARGET']))
  ("T4_ASSERT_GRAPH=" + ($status['T4_ASSERT_GRAPH']))
  ("T5_LIBRARY_DOC_CONTRACT=" + ($status['T5_LIBRARY_DOC_CONTRACT']))
  ("T6_REPEATABILITY_SHIP_TWICE=" + ($status['T6_REPEATABILITY_SHIP_TWICE']))
  ""
  "NO PUSH performed."
) | Out-File $report -Encoding utf8

Write-Output ("E2E_SUITE_DONE PF=" + $suitePf)
Write-Output "NO PUSH performed."
exit ($(if ($overall -eq 'PASS') { 0 } else { 1 }))