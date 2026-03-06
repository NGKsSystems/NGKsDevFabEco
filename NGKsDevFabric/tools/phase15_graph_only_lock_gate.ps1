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
    $PfPath = ([string](Get-Content ".\_proof\CURRENT_PF_PHASE15.txt" -Raw)).Trim()
}

if (-not (Test-Path $PfPath)) {
    New-Item -ItemType Directory -Force -Path $PfPath | Out-Null
}

$targets = @('.vscode', 'tools', 'src')
$tokenA = ('c' + 'make')
$tokenB = ('c' + 'maketools')
$tokenC = ('C' + 'Make Tools')

$patterns = @(
    @{ Name = 'p1'; Query = $tokenA },
    @{ Name = 'p2'; Query = $tokenB },
    @{ Name = 'p3'; Query = $tokenC }
)

$hits = @()
foreach ($target in $targets) {
    $targetPath = Join-Path $Root $target
    if (-not (Test-Path $targetPath)) { continue }

    foreach ($pattern in $patterns) {
        $query = [string]$pattern.Query
        $name = [string]$pattern.Name

        if ($target -eq 'tools') {
            $found = rg -n -i -e $query --glob '!phase15_graph_only_lock_gate.ps1' --glob '!_proof/**' $targetPath
        }
        else {
            $found = rg -n -i -e $query --glob '!_proof/**' $targetPath
        }

        if ($found) {
            foreach ($line in $found) {
                $hits += "[$name] $line"
            }
        }
    }
}

$statusPath = Join-Path $PfPath 'phase15_gate.status.txt'
$hitsPath = Join-Path $PfPath 'phase15_gate_hits.txt'

if ($hits.Count -gt 0) {
    'FAIL' | Out-File $statusPath -Encoding utf8
    $hits | Out-File $hitsPath -Encoding utf8
    Write-Output 'phase15_gate_fail'
    exit 2
}

'PASS' | Out-File $statusPath -Encoding utf8
'NO_HITS' | Out-File $hitsPath -Encoding utf8
Write-Output 'phase15_gate_pass'
exit 0
