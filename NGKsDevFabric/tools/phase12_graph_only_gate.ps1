param(
    [string]$Root,
    [string]$PfPath
)

$ErrorActionPreference = 'Stop'

if (-not $Root -or [string]::IsNullOrWhiteSpace($Root)) {
    $Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}
Set-Location $Root

if (-not $PfPath -or [string]::IsNullOrWhiteSpace($PfPath)) {
    $PfPath = (Get-Content ".\_proof\CURRENT_PF_PHASE12.txt" -Raw).Trim()
}

if (-not (Test-Path $PfPath)) {
    New-Item -ItemType Directory -Force -Path $PfPath | Out-Null
}

$targets = @('.vscode', 'tools', 'src')
$tokenA = ('c' + 'make')
$tokenMsbuild = ('ms' + 'build')
$tokenBuilderDirect = 'builder direct'
$tokenSubprocessA = 'subprocess.*' + ('c' + 'make')

$patterns = @(
    @{ Name = 't1'; Query = $tokenA },
    @{ Name = 'msbuild'; Query = $tokenMsbuild },
    @{ Name = 'builder direct'; Query = $tokenBuilderDirect },
    @{ Name = 't4'; Query = $tokenSubprocessA }
)

$hits = @()
foreach ($target in $targets) {
    $targetPath = Join-Path $Root $target
    if (-not (Test-Path $targetPath)) { continue }

    foreach ($pattern in $patterns) {
        $q = [string]$pattern.Query
        $name = [string]$pattern.Name

        if ($target -eq 'tools') {
            $found = rg -n -i -e $q --glob '!phase12_graph_only_gate.ps1' $targetPath
        }
        else {
            $found = rg -n -i -e $q $targetPath
        }

        if ($found) {
            foreach ($line in $found) {
                $hits += "[$name] $line"
            }
        }
    }
}

$report = Join-Path $PfPath 'phase12_graph_only_gate.txt'
$status = Join-Path $PfPath 'phase12_graph_only_gate.status.txt'

if ($hits.Count -gt 0) {
    @(
        "GATE=FAIL"
        "TARGETS=$($targets -join ',')"
        "PATTERNS=$($patterns.Name -join ',')"
        "HITS_BEGIN"
    ) | Out-File $report -Encoding utf8
    $hits | Out-File $report -Append -Encoding utf8
    "HITS_END" | Out-File $report -Append -Encoding utf8
    "FAIL" | Out-File $status -Encoding utf8
    Write-Output 'phase12_gate_fail'
    exit 2
}

@(
    "GATE=PASS"
    "TARGETS=$($targets -join ',')"
    "PATTERNS=$($patterns.Name -join ',')"
    "NO_HITS"
) | Out-File $report -Encoding utf8
"PASS" | Out-File $status -Encoding utf8
Write-Output 'phase12_gate_pass'
exit 0
