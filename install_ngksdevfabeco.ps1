param(
    [string]$WheelhousePath,
    [switch]$ForceRecreateVenv
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Test-Path $repoRoot)) {
    throw "REPO_ROOT_NOT_FOUND: $repoRoot"
}

$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$proofDir = Join-Path $repoRoot ("_proof\install_" + $ts)
New-Item -ItemType Directory -Force -Path $proofDir | Out-Null
$logFile = Join-Path $proofDir 'install.log'

function Write-Log {
    param([string]$Message)
    $line = "[$(Get-Date -Format s)] $Message"
    $line | Tee-Object -FilePath $logFile -Append | Out-Host
}

function Invoke-Logged {
    param(
        [string]$Executable,
        [string[]]$Arguments
    )
    Write-Log ("RUN: " + $Executable + " " + ($Arguments -join ' '))
    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $Executable @Arguments 2>&1 | Tee-Object -FilePath $logFile -Append | Out-Host
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if ($exitCode -ne 0) {
        throw "COMMAND_FAILED exit=$exitCode cmd=$Executable $($Arguments -join ' ')"
    }
}

Write-Log "repo_root=$repoRoot"

$wheelSource = $null
if ($WheelhousePath) {
    $wheelSource = (Resolve-Path $WheelhousePath).Path
    if (-not (Test-Path $wheelSource)) {
        throw "WHEELHOUSE_PATH_NOT_FOUND: $WheelhousePath"
    }
} else {
    $wheelRoot = Join-Path $repoRoot 'wheelhouse'
    if (-not (Test-Path $wheelRoot)) {
        throw "WHEELHOUSE_ROOT_NOT_FOUND: $wheelRoot"
    }
    $latest = Get-ChildItem -Path $wheelRoot -Directory -Filter 'e2e_*' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) {
        throw "NO_E2E_WHEELHOUSE_FOUND under $wheelRoot"
    }
    $wheelSource = $latest.FullName
}

$wheelCount = (Get-ChildItem -Path $wheelSource -Filter '*.whl' -File -ErrorAction SilentlyContinue | Measure-Object).Count
if ($wheelCount -eq 0) {
    throw "NO_WHEELS_FOUND: $wheelSource"
}
Write-Log "wheelhouse=$wheelSource"
Write-Log "wheel_count=$wheelCount"

$venvDir = Join-Path $repoRoot '.venv'
if ($ForceRecreateVenv -and (Test-Path $venvDir)) {
    Write-Log "Removing existing .venv due to -ForceRecreateVenv"
    Remove-Item -Recurse -Force $venvDir
}

if (-not (Test-Path $venvDir)) {
    Invoke-Logged -Executable 'python' -Arguments @('-m', 'venv', $venvDir)
}

$venvPython = Join-Path $venvDir 'Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    throw "VENV_PYTHON_MISSING: $venvPython"
}

Invoke-Logged -Executable $venvPython -Arguments @('-m', 'pip', 'install', '--upgrade', 'pip')
$packages = @(
    'ngksdevfabric==0.1.15',
    'ngksgraph==0.1.9',
    'ngksbuildcore==0.1.4',
    'ngksenvcapsule==0.1.2',
    'ngkslibrary==0.1.2'
)
$packageNames = @('ngksdevfabric', 'ngksgraph', 'ngksbuildcore', 'ngksenvcapsule', 'ngkslibrary')
Invoke-Logged -Executable $venvPython -Arguments (@('-m', 'pip', 'install', '--no-index', '--no-cache-dir', '--force-reinstall', '--find-links', $wheelSource) + $packages)
Invoke-Logged -Executable $venvPython -Arguments (@('-m', 'pip', 'show') + $packageNames)
Invoke-Logged -Executable $venvPython -Arguments @('-m', 'ngksgraph', '--help')
Invoke-Logged -Executable $venvPython -Arguments @('-m', 'ngksbuildcore', '--help')
Invoke-Logged -Executable $venvPython -Arguments @('-m', 'ngksdevfabric', '--help')

@(
    "repo_root=$repoRoot",
    "wheelhouse=$wheelSource",
    "venv=$venvDir",
    "status=PASS"
) | Set-Content -Encoding UTF8 (Join-Path $proofDir 'result.txt')

Write-Host "INSTALL_OK proof=$proofDir"
