param(
  [Parameter(Mandatory=$true)][string]$Root,
  [Parameter(Mandatory=$true)][string]$PfPath
)

$ErrorActionPreference="Stop"
Set-Location $Root
$tokenA = ('c' + 'make')

function ReadRaw([string]$p){
  if(-not (Test-Path $p)){ return "" }
  $v = Get-Content $p -Raw -ErrorAction SilentlyContinue
  if($null -eq $v){ return "" }
  return [string]$v
}

$gateStatus = (ReadRaw (Join-Path $PfPath "phase12_graph_only_gate.status.txt")).Trim()
$buildExit  = (ReadRaw (Join-Path $PfPath "phase12_build_exit.txt")).Trim()
$whereTool = (ReadRaw (Join-Path $PfPath ("phase12_where_" + $tokenA + ".txt"))).Trim()
$pathHits  = (ReadRaw (Join-Path $PfPath ("phase12_path_" + $tokenA + "_hits.txt"))).Trim()

if([string]::IsNullOrWhiteSpace($whereTool)){
  $whereTool = "INFO: Could not find files for the given pattern(s)."
}

$pathConfirm = if([string]::IsNullOrWhiteSpace($pathHits)){
  ("no " + $tokenA + " segments in PATH after scrub")
}else{
  ($tokenA + " segments still present in PATH after scrub")
}

# These JSONs must exist if build ran; still guard them
$strategyJson = ReadRaw (Join-Path $PfPath "run_build\00_strategy_resolution.json")
$receiptJson  = ReadRaw (Join-Path $PfPath "run_build\build_receipt.json")

$strategy_resolved = ""
$selected_backend  = ""
$plan_id           = ""

if(-not [string]::IsNullOrWhiteSpace($strategyJson)){
  try {
    $s = $strategyJson | ConvertFrom-Json
    $strategy_resolved = [string]$s.resolved_strategy
    $selected_backend  = [string]$s.selected_backend
  } catch {}
}
if(-not [string]::IsNullOrWhiteSpace($receiptJson)){
  try {
    $r = $receiptJson | ConvertFrom-Json
    $plan_id = [string]$r.plan_id
  } catch {}
}

$lines=@()
$lines += "PHASE12_GRAPH_ONLY_STATUS"
$lines += ("PF=" + $PfPath)
$lines += ("gate_result=" + $gateStatus)
$lines += ("build_exit=" + $buildExit)
$lines += ("strategy_resolved=" + $strategy_resolved)
$lines += ("selected_backend=" + $selected_backend)
$lines += ("plan_id=" + $plan_id)
$lines += (($tokenA + "_path_check=") + $pathConfirm)
$lines += ("where_" + $tokenA + "_output_begin")
$lines += $whereTool
$lines += ("where_" + $tokenA + "_output_end")

$report = Join-Path $PfPath "PHASE12_GRAPH_ONLY_REPORT.txt"
$lines | Out-File $report -Encoding utf8
Write-Output ("report_written=" + $report)
