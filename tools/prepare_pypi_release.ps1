param(
    [string]$OutDir
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $OutDir) {
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $OutDir = Join-Path $repoRoot "dist\publish_$stamp"
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    throw "PYTHON_NOT_FOUND: $python"
}

function Invoke-Step {
    param([string[]]$StepParameters)
    & $python @StepParameters
    if ($LASTEXITCODE -ne 0) {
        throw "COMMAND_FAILED: $($StepParameters -join ' ')"
    }
}

Invoke-Step @('-m', 'pip', 'install', '--upgrade', 'pip', 'build', 'twine')

$projects = @(
    $repoRoot,
    (Join-Path $repoRoot 'NGKsBuildCore'),
    (Join-Path $repoRoot 'NGKsEnvCapsule'),
    (Join-Path $repoRoot 'NGKsLibrary'),
    (Join-Path $repoRoot 'NGKsGraph'),
    (Join-Path $repoRoot 'NGKsDevFabric')
)

foreach ($project in $projects) {
    if (-not (Test-Path (Join-Path $project 'pyproject.toml'))) {
        throw "PYPROJECT_NOT_FOUND: $project"
    }
    Invoke-Step @('-m', 'build', '--wheel', '--outdir', $OutDir, $project)
}

Invoke-Step @('-m', 'twine', 'check', (Join-Path $OutDir '*.whl'))

Write-Host "PUBLISH_PREP_OK out=$OutDir"
Write-Host "Next: $python -m twine upload $OutDir\*.whl"
