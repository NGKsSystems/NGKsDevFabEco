$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repoRoot
if ((Get-Location).Path -ne $repoRoot) {
    throw 'G1 hard guard failed: wrong repo root.'
}

$pointerPath = Join-Path $repoRoot '_proof\CURRENT_PF_PHASE8.txt'
if (-not (Test-Path $pointerPath)) {
    throw 'Missing CURRENT_PF_PHASE8 pointer.'
}
$pf = (Get-Content $pointerPath -Raw).Trim()
if (-not (Test-Path $pf)) {
    throw "PF not found: $pf"
}

$commandsPath = Join-Path $pf 'PHASE8_COMMANDS.txt'
if (Test-Path $commandsPath) { Remove-Item $commandsPath -Force }

function Add-CommandLog {
    param([string]$line)
    Add-Content -Path $commandsPath -Value $line
}

function Invoke-Logged {
    param(
        [string]$label,
        [string[]]$command
    )

    Add-CommandLog ($command -join ' ')
    $outPath = Join-Path $pf ($label + '_stdout.txt')
    $errPath = Join-Path $pf ($label + '_stderr.txt')
    & $command[0] @($command[1..($command.Count-1)]) 1> $outPath 2> $errPath
    $code = $LASTEXITCODE
    if ($null -eq $code) { $code = 0 }
    Set-Content -Path (Join-Path $pf ($label + '_exit.txt')) -Value ([string]$code)
    return [int]$code
}

$g1 = ((Get-Location).Path -eq $repoRoot)

$pycFiles = Get-ChildItem -Path $repoRoot -Recurse -File -Filter *.pyc | ForEach-Object { $_.FullName }
$pycacheDirs = Get-ChildItem -Path $repoRoot -Recurse -Directory | Where-Object { $_.Name -eq '__pycache__' } | ForEach-Object { $_.FullName }
$g2 = (($pycFiles.Count -eq 0) -and ($pycacheDirs.Count -eq 0))

$diffFiles = @()
Push-Location $repoRoot
try {
    Add-CommandLog 'git diff --name-only'
    $diffFiles = git diff --name-only | Where-Object { $_ -and $_.Trim() -ne '' }
}
finally {
    Pop-Location
}
$badDiff = @($diffFiles | Where-Object { $_ -match '\.pyc$|(^|/)__pycache__(/|$)|(^|/)pycache(/|$)|(^|/)changes\.log$|(^|/)activity_log\.txt$' })
$g3 = ($badDiff.Count -eq 0)

$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) { $pythonExe = 'python' }

$codePs = Invoke-Logged -label 'g4_ps' -command @($pythonExe, '-m', 'ngk_fabric.main', 'term', 'run', 'ps: Write-Output ok', '--pf', $pf)
$lastPsDir = (Get-Content (Join-Path $pf 'run_smartterm\last_run_dir.txt') -Raw).Trim()
Copy-Item $lastPsDir (Join-Path $pf 'gate_g4_ps') -Recurse -Force
$psOut = (Get-Content (Join-Path $pf 'gate_g4_ps\10_stdout.txt') -Raw).Trim()

$codeCmd = Invoke-Logged -label 'g4_cmd' -command @($pythonExe, '-m', 'ngk_fabric.main', 'term', 'run', 'cmd: echo ok', '--pf', $pf)
$lastCmdDir = (Get-Content (Join-Path $pf 'run_smartterm\last_run_dir.txt') -Raw).Trim()
Copy-Item $lastCmdDir (Join-Path $pf 'gate_g4_cmd') -Recurse -Force
$cmdOut = (Get-Content (Join-Path $pf 'gate_g4_cmd\10_stdout.txt') -Raw).Trim()

$g4 = ($codePs -eq 0 -and $psOut -match 'ok' -and $codeCmd -eq 0 -and $cmdOut -match 'ok')

$docPath = Join-Path $repoRoot '_artifacts\runtime\README.txt'
$docText = if (Test-Path $docPath) { Get-Content $docPath -Raw } else { '' }
$hasPrecedence = $docText -match 'CLI flag\s*>\s*env\s*`NGK_SMART_TERMINAL`\s*>\s*default ON'
$hasPs = $docText -match 'ps:'
$hasCmd = $docText -match 'cmd:'
$hasAuto = $docText -match 'auto-detect'
$g5 = ($hasPrecedence -and $hasPs -and $hasCmd -and $hasAuto)

$gates = @(
    @{ Name='G1 repo guard path correct'; Pass=$g1 },
    @{ Name='G2 no *.pyc or __pycache__ under repo'; Pass=$g2 },
    @{ Name='G3 git diff has no transient artifact files'; Pass=$g3 },
    @{ Name='G4 SmartTerm sanity (ps/cmd)'; Pass=$g4 },
    @{ Name='G5 doc includes precedence + ps/cmd/auto examples'; Pass=$g5 }
)

$lines = @()
foreach($g in $gates){
    $lines += ("{0}: {1}" -f $g.Name, $(if($g.Pass){'PASS'}else{'FAIL'}))
}
if($badDiff.Count -gt 0){
    $lines += 'BAD_DIFF_FILES:'
    $lines += $badDiff
}
if($pycFiles.Count -gt 0 -or $pycacheDirs.Count -gt 0){
    $lines += 'ARTIFACT_OFFENDERS:'
    if($pycFiles.Count -gt 0){ $lines += $pycFiles }
    if($pycacheDirs.Count -gt 0){ $lines += $pycacheDirs }
}
$overall = ($gates | Where-Object { -not $_.Pass }).Count -eq 0
$lines += ("OVERALL: {0}" -f $(if($overall){'PASS'}else{'FAIL'}))
Set-Content -Path (Join-Path $pf 'PHASE8_GATES.txt') -Value $lines -Encoding utf8

if($overall){ exit 0 }
exit 1
