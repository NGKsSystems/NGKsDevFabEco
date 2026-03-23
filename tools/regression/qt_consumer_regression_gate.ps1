param(
    [string]$ProjectRoot = "C:\Users\suppo\Desktop\NGKsSystems\NGKs_Content_Curator",
    [string]$PythonExe = "C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_validation_venv\Scripts\python.exe",
    [string]$ProofDir = "",
    [string]$ResultJsonName = "31_pass_results.json",
    [string]$InjectRegressionCapability = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$repoRoot = "C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco"
if (-not (Test-Path $repoRoot)) {
    throw "Repo root not found: $repoRoot"
}

if ([string]::IsNullOrWhiteSpace($ProofDir)) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $ProofDir = Join-Path $repoRoot ("_proof\qt_consumer_regression_gate_" + $stamp)
}
New-Item -ItemType Directory -Force -Path $ProofDir | Out-Null

$env:PYTHONPATH = @(
    (Join-Path $repoRoot "NGKsGraph"),
    (Join-Path $repoRoot "NGKsDevFabric"),
    (Join-Path $repoRoot "NGKsBuildCore"),
    (Join-Path $repoRoot "NGKsEnvCapsule"),
    (Join-Path $repoRoot "NGKsLibrary")
) -join ";"

$forbiddenCaps = @("qt.cored", "qt.guid", "qt.widgetsd")

function Find-ForbiddenHits {
    param(
        [string]$Text,
        [string[]]$Tokens
    )
    $hits = @()
    foreach ($token in $Tokens) {
        if ($Text -match [Regex]::Escape($token)) {
            $hits += $token
        }
    }
    return @($hits | Sort-Object -Unique)
}

function Run-PythonCommand {
    param(
        [string]$Name,
        [string[]]$Arguments,
        [string]$OutputFile
    )
    $code = 0
    $stderrFile = $OutputFile + ".stderr"
    try {
        $proc = Start-Process -FilePath $PythonExe -ArgumentList $Arguments -NoNewWindow -Wait -PassThru -RedirectStandardOutput $OutputFile -RedirectStandardError $stderrFile
        $code = [int]$proc.ExitCode
        if (Test-Path $stderrFile) {
            $stderrText = Get-Content -Path $stderrFile -Raw
            if (-not [string]::IsNullOrWhiteSpace($stderrText)) {
                Add-Content -Path $OutputFile -Value $stderrText
            }
            Remove-Item -Path $stderrFile -Force
        }
        if (Test-Path $OutputFile) {
            Get-Content -Path $OutputFile | Out-Host
        }
    }
    catch {
        $_ | Out-String | Set-Content -Path $OutputFile
        $code = 1
    }
    return [ordered]@{
        name = $Name
        output_file = $OutputFile
        exit_code = [int]$code
    }
}

$graphOut = Join-Path $ProofDir "graph_path.raw.txt"
$wrapperOut = Join-Path $ProofDir "wrapper_path.raw.txt"
$directOut = Join-Path $ProofDir "direct_path.raw.txt"
$directJsonPath = Join-Path $ProofDir "direct_path.results.json"

$graphRun = Run-PythonCommand -Name "graph_path" -OutputFile $graphOut -Arguments @(
    "-m", "ngksgraph", "build", "--project", $ProjectRoot, "--profile", "debug", "--clear-cache"
)

$wrapperRun = Run-PythonCommand -Name "wrapper_devfabric_path" -OutputFile $wrapperOut -Arguments @(
    "-m", "ngksdevfabric", "build", $ProjectRoot, "--mode", "debug"
)

$directScriptPath = Join-Path $ProofDir "direct_path_probe.py"
@'
import json
import re
import sys
from pathlib import Path

from ngksgraph.config import load_config
from ngksgraph.graph import build_graph_from_project
from ngksgraph.targetspec.target_spec_loader import load_or_derive_target_spec
from ngksgraph.capability.capability_inventory import build_capability_inventory
from ngksgraph.resolver.target_resolution_engine import resolve_target_capabilities
from ngksgraph.repo_classifier import _collect_text_signals, _infer_qt_modules

FORBIDDEN = {"qt.cored", "qt.guid", "qt.widgetsd"}
FALLBACK_BASELINE = {"Core", "Gui", "Widgets"}


def _collect_real_qt_signals(repo: Path) -> set[str]:
    modules: set[str] = set()
    patterns = ["*.cpp", "*.cc", "*.cxx", "*.h", "*.hpp", "*.hh", "CMakeLists.txt", "*.cmake", "ngksgraph.toml"]
    include_rx = re.compile(r"#\s*include\s*<Qt(?P<mod>[A-Za-z0-9_]+)/")
    ns_rx = re.compile(r"Qt6::(?P<mod>[A-Za-z0-9_]+)")
    lib_rx = re.compile(r"\bQt(?:5|6)(?P<mod>[A-Za-z0-9_]+?)d?\.lib\b", re.IGNORECASE)
    cmake_rx = re.compile(r"find_package\(\s*Qt(?:5|6)\s+COMPONENTS\s+(?P<body>[^\)]+)\)", re.IGNORECASE | re.MULTILINE)

    seen_files = set()
    for pat in patterns:
        for path in repo.rglob(pat):
            if not path.is_file():
                continue
            if path in seen_files:
                continue
            seen_files.add(path)
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for m in include_rx.finditer(text):
                modules.add(m.group("mod"))
            for m in ns_rx.finditer(text):
                modules.add(m.group("mod"))
            for m in lib_rx.finditer(text):
                modules.add(m.group("mod"))
            for m in cmake_rx.finditer(text):
                body = m.group("body")
                for token in re.split(r"\s+", body):
                    t = token.strip()
                    if t:
                        modules.add(t)
    return modules


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: direct_path_probe.py <project_root> <json_out>")

    project_root = Path(sys.argv[1]).resolve()
    json_out = Path(sys.argv[2]).resolve()

    config = load_config(project_root / "ngksgraph.toml")
    graph = build_graph_from_project(config, source_map={}, msvc_auto=False)
    selected_target = config.default_target_name()
    spec, spec_source, spec_path = load_or_derive_target_spec(
        repo_root=project_root,
        config=config,
        graph=graph,
        selected_target=selected_target,
        profile="debug",
    )
    target = graph.targets[selected_target]
    inventory = build_capability_inventory(config=config, target=target)
    report = resolve_target_capabilities(target_spec=spec, inventory=inventory)

    required = list(spec.required_capabilities)
    qt_required = sorted([c for c in required if c.startswith("qt.")])
    qt_inventory = sorted([
        r.capability_name for r in inventory.records if r.capability_name.startswith("qt.") and r.status == "available"
    ])
    forbidden_in_required = sorted([c for c in required if c in FORBIDDEN])
    leaked_suffix_debug = sorted([c for c in required if c.startswith("qt.") and c.endswith("d")])

    signals = _collect_text_signals(project_root)
    inferred_modules = _infer_qt_modules(signals)
    real_qt_signals = sorted(_collect_real_qt_signals(project_root))
    fallback_only_inference = bool(real_qt_signals) and set(inferred_modules) == FALLBACK_BASELINE

    printsupport_ok = False
    for row in report.resolved:
        if row.capability == "qt.printsupport":
            module_dir = str((row.metadata or {}).get("module_dir", ""))
            if "QtPrintSupport" in module_dir:
                printsupport_ok = True
            break

    out = {
        "project_root": str(project_root),
        "selected_target": selected_target,
        "spec_source": spec_source,
        "spec_path": spec_path,
        "required_capabilities": required,
        "qt_required": qt_required,
        "qt_inventory": qt_inventory,
        "missing": [r.capability for r in report.missing],
        "build_allowed": report.build_allowed,
        "forbidden_required_hits": forbidden_in_required,
        "qt_debug_suffix_leaks": leaked_suffix_debug,
        "inferred_modules": inferred_modules,
        "real_qt_signals": real_qt_signals,
        "fallback_only_inference": fallback_only_inference,
        "multiword_casing_ok": printsupport_ok,
    }
    json_out.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@ | Set-Content -Path $directScriptPath -Encoding UTF8

$directRun = Run-PythonCommand -Name "direct_devfabeco_path" -OutputFile $directOut -Arguments @(
    $directScriptPath, $ProjectRoot, $directJsonPath
)

$result = [ordered]@{
    gate_name = "qt_consumer_regression_gate"
    proof_dir = $ProofDir
    project_root = $ProjectRoot
    python_exe = $PythonExe
    repo_root = $repoRoot
    reference_commit = "4340485"
    required_paths = @("graph_path", "wrapper_devfabric_path", "direct_devfabeco_path")
    forbidden_capabilities = $forbiddenCaps
    path_runs = @($graphRun, $wrapperRun, $directRun)
    checks = [ordered]@{}
    pass = $false
}

$graphResolutionDir = Join-Path $ProjectRoot "build_graph\debug\resolution"
$graphReportPath = Join-Path $graphResolutionDir "14_resolution_report.json"
$graphSummaryPath = Join-Path $graphResolutionDir "17_resolution_summary.md"

$graphReportExists = Test-Path $graphReportPath
$graphSummaryExists = Test-Path $graphSummaryPath
$graphReportText = ""
$graphReport = $null
if ($graphReportExists) {
    $graphReportText = Get-Content -Path $graphReportPath -Raw
    try { $graphReport = $graphReportText | ConvertFrom-Json } catch { $graphReport = $null }
}

$wrapperText = if (Test-Path $wrapperOut) { Get-Content -Path $wrapperOut -Raw } else { "" }
$directText = if (Test-Path $directOut) { Get-Content -Path $directOut -Raw } else { "" }
$directObj = $null
if (Test-Path $directJsonPath) {
    try { $directObj = (Get-Content -Path $directJsonPath -Raw | ConvertFrom-Json) } catch { $directObj = $null }
}

$forbiddenHits = @()
$forbiddenHits += Find-ForbiddenHits -Text $graphReportText -Tokens $forbiddenCaps
$forbiddenHits += Find-ForbiddenHits -Text $wrapperText -Tokens $forbiddenCaps
$forbiddenHits += Find-ForbiddenHits -Text $directText -Tokens $forbiddenCaps

if (-not [string]::IsNullOrWhiteSpace($InjectRegressionCapability)) {
    $forbiddenHits += $InjectRegressionCapability.Trim()
}
$forbiddenHits = @($forbiddenHits | Sort-Object -Unique)

$graphPass = (
    ($graphRun.exit_code -eq 0) -and
    $graphReportExists -and
    ($null -ne $graphReport) -and
    ($graphReport.build_allowed -eq $true) -and
    ($graphReport.summary.missing_count -eq 0)
)

$wrapperPass = (
    ($wrapperRun.exit_code -eq 0) -and
    ($wrapperText -match "validation_policy_gate=PASS") -and
    ($wrapperText -match "exit_code=0")
)

$directPass = (
    ($directRun.exit_code -eq 0) -and
    ($null -ne $directObj) -and
    ($directObj.build_allowed -eq $true) -and
    (($directObj.missing | Measure-Object).Count -eq 0) -and
    (($directObj.forbidden_required_hits | Measure-Object).Count -eq 0) -and
    (($directObj.qt_debug_suffix_leaks | Measure-Object).Count -eq 0) -and
    ($directObj.fallback_only_inference -eq $false) -and
    ($directObj.multiword_casing_ok -eq $true)
)

$result.checks = [ordered]@{
    graph_path = $graphPass
    wrapper_devfabric_path = $wrapperPass
    direct_devfabeco_path = $directPass
    graph_resolution_report_exists = $graphReportExists
    graph_resolution_summary_exists = $graphSummaryExists
    forbidden_capability_hits = $forbiddenHits
    injected_regression_capability = $InjectRegressionCapability
}

$result.pass = ($graphPass -and $wrapperPass -and $directPass -and (($forbiddenHits | Measure-Object).Count -eq 0))

$resultPath = Join-Path $ProofDir $ResultJsonName
($result | ConvertTo-Json -Depth 8) | Set-Content -Path $resultPath -Encoding UTF8
Write-Output ("RESULT_JSON=" + $resultPath)
Write-Output ("GATE=" + $(if ($result.pass) { "PASS" } else { "FAIL" }))

if (-not $result.pass) {
    exit 2
}
exit 0
