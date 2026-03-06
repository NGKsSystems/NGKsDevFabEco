param(
    [Parameter(Mandatory=$true)][string]$Target
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pointerPath = Join-Path $repoRoot '_proof\CURRENT_PF_PHASE5.txt'
if (-not (Test-Path $pointerPath)) {
    throw "Missing pointer file: $pointerPath"
}

$pf = (Get-Content $pointerPath -Raw).Trim()
if (-not $pf) {
    throw 'CURRENT_PF_PHASE5.txt is empty.'
}
if (-not (Test-Path $pf)) {
    throw "PF directory does not exist: $pf"
}

$slnPath = Join-Path $target 'CSharpAvaloniaOfficeSuite.sln'
$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) {
    $pythonExe = 'python'
}

$commandsPath = Join-Path $pf 'PHASE5_COMMANDS.txt'
if (Test-Path $commandsPath) {
    Remove-Item $commandsPath -Force
}

function Add-CommandLog {
    param([string]$CommandLine)
    Add-Content -Path $commandsPath -Value $CommandLine
}

function Invoke-AndLog {
    param(
        [string]$StepName,
        [string[]]$Command
    )

    $stdoutPath = Join-Path $pf ("{0}_stdout.txt" -f $StepName)
    $stderrPath = Join-Path $pf ("{0}_stderr.txt" -f $StepName)
    $exitPath = Join-Path $pf ("{0}_exit.txt" -f $StepName)

    Add-CommandLog ($Command -join ' ')

    $exe = $Command[0]
    $args = @()
    if ($Command.Count -gt 1) {
        $args = $Command[1..($Command.Count - 1)]
    }

    Push-Location $repoRoot
    try {
        & $exe @args 1> $stdoutPath 2> $stderrPath
        $code = $LASTEXITCODE
        if ($null -eq $code) {
            $code = 0
        }
        Set-Content -Path $exitPath -Value ([string]$code)
        return [int]$code
    }
    finally {
        Pop-Location
    }
}

function Copy-RunArtifacts {
    param(
        [string]$Prefix,
        [int]$Index
    )

    $runDir = Join-Path $pf 'run_build'
    Copy-Item (Join-Path $runDir '03_cmd_build.txt') (Join-Path $pf ("{0}_cmd_{1}.txt" -f $Prefix, $Index)) -Force
    Copy-Item (Join-Path $runDir 'build_receipt.json') (Join-Path $pf ("{0}_receipt_{1}.json" -f $Prefix, $Index)) -Force
    Copy-Item (Join-Path $runDir '00_strategy_resolution.json') (Join-Path $pf ("{0}_strategy_{1}.json" -f $Prefix, $Index)) -Force
    Copy-Item (Join-Path $runDir '05_build_fingerprint.json') (Join-Path $pf ("{0}_fp_{1}.json" -f $Prefix, $Index)) -Force
}

function Read-Json {
    param([string]$Path)
    return Get-Content $Path -Raw | ConvertFrom-Json
}

$step = 0

$step++
$code = Invoke-AndLog -StepName ("{0:D2}_probe_target" -f $step) -Command @($pythonExe, '-m', 'ngk_fabric.main', 'probe', $target, '--pf', $pf)
if ($code -ne 0) { throw "Probe failed with exit code $code" }

$step++
$code = Invoke-AndLog -StepName ("{0:D2}_profile_target" -f $step) -Command @($pythonExe, '-m', 'ngk_fabric.main', 'profile', 'init', $target, '--pf', $pf)
if ($code -ne 0) { throw "Profile init failed with exit code $code" }

$step++
$code = Invoke-AndLog -StepName ("{0:D2}_build_a1_sln" -f $step) -Command @($pythonExe, '-m', 'ngk_fabric.main', 'build', $slnPath, '--pf', $pf, '--mode', 'debug')
if ($code -ne 0) { throw "A1 build failed with exit code $code" }
Copy-RunArtifacts -Prefix 'A' -Index 1

$step++
$code = Invoke-AndLog -StepName ("{0:D2}_build_a2_sln" -f $step) -Command @($pythonExe, '-m', 'ngk_fabric.main', 'build', $slnPath, '--pf', $pf, '--mode', 'debug')
if ($code -ne 0) { throw "A2 build failed with exit code $code" }
Copy-RunArtifacts -Prefix 'A' -Index 2

$csprojPath = Get-ChildItem -Path $target -Filter *.csproj -Recurse -File |
    Where-Object { $_.FullName -notmatch '\\.history\\' -and $_.FullName -notmatch '\\bin\\' -and $_.FullName -notmatch '\\obj\\' } |
    Sort-Object FullName |
    Select-Object -First 1
if (-not $csprojPath) {
    throw 'No filtered .csproj file found under target tree.'
}
Set-Content -Path (Join-Path $pf 'B_selected_csproj.txt') -Value $csprojPath.FullName

$csprojDir = $csprojPath.DirectoryName

$step++
$code = Invoke-AndLog -StepName ("{0:D2}_probe_csproj_dir" -f $step) -Command @($pythonExe, '-m', 'ngk_fabric.main', 'probe', $csprojDir, '--pf', $pf)
if ($code -ne 0) { throw "CSProj probe failed with exit code $code" }

$step++
$code = Invoke-AndLog -StepName ("{0:D2}_profile_csproj_dir" -f $step) -Command @($pythonExe, '-m', 'ngk_fabric.main', 'profile', 'init', $csprojDir, '--pf', $pf)
if ($code -ne 0) { throw "CSProj profile init failed with exit code $code" }

$statePath = Join-Path $pf 'run_build\07_last_successful_fingerprint.json'
if (Test-Path $statePath) {
    Remove-Item $statePath -Force
}

$step++
$code = Invoke-AndLog -StepName ("{0:D2}_build_b1_csproj" -f $step) -Command @($pythonExe, '-m', 'ngk_fabric.main', 'build', $csprojPath.FullName, '--pf', $pf, '--mode', 'debug')
if ($code -ne 0) { throw "B1 build failed with exit code $code" }
Copy-RunArtifacts -Prefix 'B' -Index 1

$step++
$code = Invoke-AndLog -StepName ("{0:D2}_build_b2_csproj" -f $step) -Command @($pythonExe, '-m', 'ngk_fabric.main', 'build', $csprojPath.FullName, '--pf', $pf, '--mode', 'debug')
if ($code -ne 0) { throw "B2 build failed with exit code $code" }
Copy-RunArtifacts -Prefix 'B' -Index 2

$originalCsproj = Get-Content $csprojPath.FullName -Raw
$toggleComment = "<!-- phase5_toggle $(Get-Date -Format o) -->"
Set-Content -Path $csprojPath.FullName -Value ($originalCsproj + [Environment]::NewLine + $toggleComment) -Encoding UTF8
try {
    $step++
    $code = Invoke-AndLog -StepName ("{0:D2}_build_b3_csproj_toggle" -f $step) -Command @($pythonExe, '-m', 'ngk_fabric.main', 'build', $csprojPath.FullName, '--pf', $pf, '--mode', 'debug')
    if ($code -ne 0) { throw "B3 build failed with exit code $code" }
    Copy-RunArtifacts -Prefix 'B' -Index 3
}
finally {
    Set-Content -Path $csprojPath.FullName -Value $originalCsproj -Encoding UTF8
}

$aStrategy1 = Read-Json (Join-Path $pf 'A_strategy_1.json')
$bStrategy1 = Read-Json (Join-Path $pf 'B_strategy_1.json')
$aReceipt1 = Read-Json (Join-Path $pf 'A_receipt_1.json')
$aReceipt2 = Read-Json (Join-Path $pf 'A_receipt_2.json')
$bReceipt1 = Read-Json (Join-Path $pf 'B_receipt_1.json')
$bReceipt2 = Read-Json (Join-Path $pf 'B_receipt_2.json')
$bReceipt3 = Read-Json (Join-Path $pf 'B_receipt_3.json')
$bFp2 = Read-Json (Join-Path $pf 'B_fp_2.json')
$bFp3 = Read-Json (Join-Path $pf 'B_fp_3.json')

$legacySlnStrategy = ('ms' + 'build_sln')
$g1 = ($aStrategy1.selected_strategy -eq $legacySlnStrategy -and $aStrategy1.input_kind -eq 'file')
$g2 = (
    ($aReceipt1.exit_code -eq 0) -and
    (-not [bool]$aReceipt1.build_skipped) -and
    ([bool]$aReceipt2.build_skipped) -and
    ($bReceipt1.exit_code -eq 0) -and
    (-not [bool]$bReceipt1.build_skipped) -and
    ([bool]$bReceipt2.build_skipped)
)
$g3 = ($bStrategy1.selected_strategy -eq 'dotnet_csproj' -and $bStrategy1.input_kind -eq 'file')
$g4 = (
    (-not [bool]$bReceipt3.build_skipped) -and
    (-not (Test-Path (Join-Path $pf 'run_build\06_build_skipped.txt')))
)
$g5 = (
    ($bReceipt3.exit_code -eq 0) -and
    (-not [bool]$bReceipt3.build_skipped) -and
    ($bFp2.fingerprint -ne $bFp3.fingerprint)
)

$gates = @(
    @{ Name = 'G1 strategy forced for .sln file'; Pass = $g1 },
    @{ Name = 'G2 skip only on successful previous fingerprint'; Pass = $g2 },
    @{ Name = 'G3 .csproj file forces dotnet_csproj strategy'; Pass = $g3 },
    @{ Name = 'G4 stale skip marker never persists'; Pass = $g4 },
    @{ Name = 'G5 toggle changes fingerprint and rebuilds (skip=false)'; Pass = $g5 }
)

$lines = @()
foreach ($gate in $gates) {
    $status = if ($gate.Pass) { 'PASS' } else { 'FAIL' }
    $lines += ("{0}: {1}" -f $gate.Name, $status)
}
$allPass = ($gates | Where-Object { -not $_.Pass }).Count -eq 0
$lines += ("OVERALL: {0}" -f ($(if ($allPass) { 'PASS' } else { 'FAIL' })))
$lines += ("A_EXITS: {0},{1}" -f $aReceipt1.exit_code, $aReceipt2.exit_code)
$lines += ("A_SKIPS: {0},{1}" -f $aReceipt1.build_skipped, $aReceipt2.build_skipped)
$lines += ("B_EXITS: {0},{1},{2}" -f $bReceipt1.exit_code, $bReceipt2.exit_code, $bReceipt3.exit_code)
$lines += ("B_SKIPS: {0},{1},{2}" -f $bReceipt1.build_skipped, $bReceipt2.build_skipped, $bReceipt3.build_skipped)
$lines += ("B_FP2: {0}" -f $bFp2.fingerprint)
$lines += ("B_FP3: {0}" -f $bFp3.fingerprint)

$gatesPath = Join-Path $pf 'PHASE5_GATES.txt'
Set-Content -Path $gatesPath -Value $lines -Encoding UTF8

if ($allPass) {
    exit 0
}
exit 1
