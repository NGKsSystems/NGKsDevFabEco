$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$proofRoot = Join-Path $repoRoot '_proof'
$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$pf = Join-Path $proofRoot ("fabric_phase7_smartterm_" + $ts)
New-Item -ItemType Directory -Force -Path $pf | Out-Null
Set-Content -Path (Join-Path $proofRoot 'CURRENT_PF_PHASE7.txt') -Value $pf -Encoding UTF8

Push-Location $repoRoot
try {
    git status --short --branch | Out-File -FilePath (Join-Path $pf '01_git_status.txt') -Encoding utf8
    git rev-parse HEAD | Out-File -FilePath (Join-Path $pf '02_git_head.txt') -Encoding utf8
    @('python','pwsh','cmd','dotnet') | ForEach-Object {
        "### $_" | Out-File -FilePath (Join-Path $pf '03_where_tools.txt') -Append -Encoding utf8
        (Get-Command $_ -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue) | Out-File -FilePath (Join-Path $pf '03_where_tools.txt') -Append -Encoding utf8
        '' | Out-File -FilePath (Join-Path $pf '03_where_tools.txt') -Append -Encoding utf8
    }
}
finally {
    Pop-Location
}

$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) { $pythonExe = 'python' }

$commandsPath = Join-Path $pf 'PHASE7_COMMANDS.txt'
if (Test-Path $commandsPath) { Remove-Item $commandsPath -Force }

function Add-CommandLog {
    param([string]$Line)
    Add-Content -Path $commandsPath -Value $Line
}

function Invoke-Term {
    param(
        [string]$Label,
        [string]$CommandText,
        [string]$SmartMode,
        [bool]$UseDisableEnv
    )

    $args = @('-m','ngk_fabric.main','term','run',$CommandText,'--pf',$pf)
    if ($SmartMode) { $args += @('--smart-terminal',$SmartMode) }

    $line = "$pythonExe " + ($args -join ' ')
    if ($UseDisableEnv) {
        $line = 'NGK_SMART_TERMINAL=0 ' + $line
    }
    Add-CommandLog $line

    Push-Location $repoRoot
    try {
        if ($UseDisableEnv) {
            $env:NGK_SMART_TERMINAL = '0'
        } else {
            Remove-Item Env:NGK_SMART_TERMINAL -ErrorAction SilentlyContinue
        }

        & $pythonExe @args | Tee-Object -FilePath (Join-Path $pf ($Label + '_cli.txt')) | Out-Host
        $code = $LASTEXITCODE
        Set-Content -Path (Join-Path $pf ($Label + '_exit.txt')) -Value ([string]$code)
        if ($code -ne 0) {
            throw "Command failed: $Label (exit=$code)"
        }
    }
    finally {
        Remove-Item Env:NGK_SMART_TERMINAL -ErrorAction SilentlyContinue
        Pop-Location
    }

    $lastRunPath = Join-Path $pf 'run_smartterm\last_run_dir.txt'
    $runDir = (Get-Content $lastRunPath -Raw).Trim()
    if (-not (Test-Path $runDir)) {
        throw ("Missing SmartTerm run directory for {0}: {1}" -f $Label, $runDir)
    }
    Copy-Item $runDir (Join-Path $pf ('smartterm_' + $Label)) -Recurse -Force
    return (Join-Path $pf ('smartterm_' + $Label))
}

$r1 = Invoke-Term -Label 'v1_ps' -CommandText 'ps: Write-Output hello' -SmartMode '' -UseDisableEnv $false
$r2 = Invoke-Term -Label 'v2_cmd' -CommandText 'cmd: echo hi' -SmartMode '' -UseDisableEnv $false
$r3 = Invoke-Term -Label 'v3_auto' -CommandText 'Get-ChildItem .' -SmartMode '' -UseDisableEnv $false
$r4 = Invoke-Term -Label 'v4_disabled' -CommandText 'echo disabled' -SmartMode '' -UseDisableEnv $true

$d1 = Get-Content (Join-Path $r1 '02_detected_shell.json') -Raw | ConvertFrom-Json
$d2 = Get-Content (Join-Path $r2 '02_detected_shell.json') -Raw | ConvertFrom-Json
$d3 = Get-Content (Join-Path $r3 '02_detected_shell.json') -Raw | ConvertFrom-Json
$d4 = Get-Content (Join-Path $r4 '02_detected_shell.json') -Raw | ConvertFrom-Json

$o1 = (Get-Content (Join-Path $r1 '10_stdout.txt') -Raw).Trim()
$o2 = (Get-Content (Join-Path $r2 '10_stdout.txt') -Raw).Trim()

$e1 = (Get-Content (Join-Path $r1 '99_exitcode.txt') -Raw).Trim()
$e2 = (Get-Content (Join-Path $r2 '99_exitcode.txt') -Raw).Trim()
$e3 = (Get-Content (Join-Path $r3 '99_exitcode.txt') -Raw).Trim()
$e4 = (Get-Content (Join-Path $r4 '99_exitcode.txt') -Raw).Trim()

$g1 = ($d1.shell -eq 'powershell' -and $e1 -eq '0' -and $o1 -match 'hello')
$g2 = ($d2.shell -eq 'cmd' -and $e2 -eq '0' -and $o2 -match 'hi')
$g3 = ($d3.shell -eq 'powershell' -and [double]$d3.confidence -ge 0.9 -and $e3 -eq '0')
$g4 = ($d4.bypass_enabled -eq $true -and $e4 -eq '0')

$gates = @(
    @{ Name = 'G1 ps prefix routes to powershell and succeeds'; Pass = $g1 },
    @{ Name = 'G2 cmd prefix routes to cmd and succeeds'; Pass = $g2 },
    @{ Name = 'G3 auto-detect powershell confidence >= 0.9'; Pass = $g3 },
    @{ Name = 'G4 smart terminal disabled path logs bypass and succeeds'; Pass = $g4 }
)

$gateLines = @()
foreach ($gate in $gates) {
    $gateLines += ("{0}: {1}" -f $gate.Name, $(if ($gate.Pass) { 'PASS' } else { 'FAIL' }))
}
$overallPass = ($gates | Where-Object { -not $_.Pass }).Count -eq 0
$gateLines += ("OVERALL: {0}" -f $(if ($overallPass) { 'PASS' } else { 'FAIL' }))
$gateLines += ("EXITCODES: v1={0}, v2={1}, v3={2}, v4={3}" -f $e1, $e2, $e3, $e4)
Set-Content -Path (Join-Path $pf 'PHASE7_GATES.txt') -Value $gateLines -Encoding utf8

$changed = @()
Push-Location $repoRoot
try {
    $changed = git diff --name-only | Where-Object { $_ -and $_.Trim() -ne '' }
}
finally {
    Pop-Location
}

$reportLines = @()
$reportLines += '<!-- markdownlint-disable -->'
$reportLines += '# PHASE7 Smart Terminal Integration Report'
$reportLines += ''
$reportLines += '## PF Path'
$reportLines += $pf
$reportLines += ''
$reportLines += '## Validation Commands'
Get-Content $commandsPath | ForEach-Object { $reportLines += ('- `' + $_ + '`') }
$reportLines += ''
$reportLines += '## Gate Results'
$gateLines | ForEach-Object { $reportLines += ('- ' + $_) }
$reportLines += ''
$reportLines += '## SmartTerm Wiring'
$reportLines += '- CLI entry: `python -m ngk_fabric.main term run ...`'
$reportLines += '- Execution module: `src/ngk_fabric/smart_terminal.py`'
$reportLines += '- Config precedence: CLI flag `--smart-terminal` > env `NGK_SMART_TERMINAL` > default ON'
$reportLines += ''
$reportLines += '## Changed Files (git diff --name-only)'
$changed | ForEach-Object { $reportLines += ('- ' + $_) }
Set-Content -Path (Join-Path $pf 'PHASE7_REPORT.md') -Value $reportLines -Encoding utf8

if ($overallPass) { exit 0 }
exit 1
