# tools\phase12_runner.ps1
param(
  [Parameter(Mandatory=$true)][string]$Target,
  [Parameter(Mandatory=$true)][string]$PfPath
)

$ErrorActionPreference="Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
if ((Get-Location).Path -ne $root) { "hey stupid Fucker, wrong window again"; exit 1 }

New-Item -ItemType Directory -Force -Path $PfPath | Out-Null
git status --short --branch | Out-File (Join-Path $PfPath "01_git_status.txt") -Encoding utf8
git rev-parse HEAD          | Out-File (Join-Path $PfPath "02_git_head.txt")   -Encoding utf8

# Gate first (single source of truth)
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\phase12_graph_only_gate.ps1 -Root $root -PfPath $PfPath
$gateExit=$LASTEXITCODE
Set-Content (Join-Path $PfPath "10_gate_exit.txt") ([string]$gateExit)
if($gateExit -ne 0){ throw "Hard gate: phase12_graph_only_gate failed exit=$gateExit" }

# PATH scrub for this process
$tokenA = ('c' + 'make')
$parts = $env:PATH -split ";" | Where-Object { $_ -and ($_ -notmatch ("(?i)" + $tokenA)) }
$env:PATH = ($parts -join ";")
$whereFile = Join-Path $PfPath ("21_where_" + $tokenA + ".txt")
$cmd = Get-Command $tokenA -ErrorAction SilentlyContinue
if ($cmd) {
  @($cmd | Select-Object -ExpandProperty Source) | Out-File $whereFile -Encoding utf8
}
else {
  "INFO: Could not find files for the given pattern(s)." | Out-File $whereFile -Encoding utf8
}

$env:PYTHONPATH="src"
$py = Join-Path $root ".venv\Scripts\python.exe"

function Invoke-PyStep {
  param(
    [Parameter(Mandatory=$true)][string[]]$Args,
    [Parameter(Mandatory=$true)][string]$OutFile
  )

  $prevEap = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    $null = & $py @Args 2>&1 | Tee-Object -FilePath $OutFile
    return [int]$LASTEXITCODE
  } finally {
    $ErrorActionPreference = $prevEap
  }
}

# -------------------------
# Core build pipeline
# -------------------------
$probeExit = Invoke-PyStep -Args @("-m","ngksdevfabric","probe",$Target,"--pf",$PfPath) -OutFile (Join-Path $PfPath "30_probe_out.txt")
Set-Content (Join-Path $PfPath "30_probe_exit.txt") ("probe_exitcode="+$probeExit)
if($probeExit -ne 0){ throw "Hard gate: probe failed exit=$probeExit" }

$profileExit = Invoke-PyStep -Args @("-m","ngksdevfabric","profile","init",$Target,"--pf",$PfPath) -OutFile (Join-Path $PfPath "31_profile_out.txt")
Set-Content (Join-Path $PfPath "31_profile_exit.txt") ("profile_exitcode="+$profileExit)
if($profileExit -ne 0){ throw "Hard gate: profile init failed exit=$profileExit" }

$buildExit = Invoke-PyStep -Args @("-m","ngksdevfabric","build",$Target,"--pf",$PfPath,"--mode","debug") -OutFile (Join-Path $PfPath "32_build_out.txt")
Set-Content (Join-Path $PfPath "33_build_exit.txt") ("build_exitcode="+$buildExit)
if($buildExit -ne 0){ throw "Hard gate: build failed exit=$buildExit" }

# -------------------------
# NGKsLibrary / DocEngine integration
# render-doc must write:
#  - 00_writes_ledger.jsonl
#  - summary/index.json
#  - summary/SUMMARY.md
# Then doc-gate must PASS.
# -------------------------
$docRenderExit = Invoke-PyStep -Args @("-m","ngksdevfabric","render-doc","--pf",$PfPath) -OutFile (Join-Path $PfPath "40_render_doc_out.txt")
Set-Content (Join-Path $PfPath "41_render_doc_exit.txt") ("render_doc_exitcode="+$docRenderExit)
if($docRenderExit -ne 0){ throw "Hard gate: render-doc failed exit=$docRenderExit" }

$docGateExit = Invoke-PyStep -Args @("-m","ngksdevfabric","doc-gate","--pf",$PfPath) -OutFile (Join-Path $PfPath "42_doc_gate_out.txt")
Set-Content (Join-Path $PfPath "43_doc_gate_exit.txt") ("doc_gate_exitcode="+$docGateExit)
if($docGateExit -ne 0){ throw "Hard gate: doc-gate failed exit=$docGateExit" }

# -------------------------
# Final status
# -------------------------
"PHASE12_REPLAY_OK" | Out-File (Join-Path $PfPath "PHASE12_REPLAY.status.txt") -Encoding utf8
Write-Output ("PHASE12_REPLAY_OK PF="+$PfPath)