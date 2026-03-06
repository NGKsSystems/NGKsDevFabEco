param(
    [switch]$OneFile
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

$timestamp = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH-mm-ssZ')
$stageRoot = Join-Path $repoRoot "artifacts\package\phase10\$timestamp"
if (Test-Path $stageRoot) {
    Remove-Item -Recurse -Force $stageRoot
}
New-Item -ItemType Directory -Path $stageRoot | Out-Null

$buildMode = if ($OneFile) { 'onefile' } else { 'onefolder' }

& $pythonExe -m pip install -r (Join-Path $repoRoot 'requirements-packaging.txt') | Out-Host

$buildWork = Join-Path $stageRoot '_build'
$distDir = Join-Path $buildWork 'dist'
$workDir = Join-Path $buildWork 'work'
$specDir = Join-Path $buildWork 'spec'

New-Item -ItemType Directory -Path $buildWork, $distDir, $workDir, $specDir | Out-Null

$pyiArgs = @(
    '-m', 'PyInstaller',
    '--noconfirm',
    '--name', 'ngksgraph',
    '--distpath', $distDir,
    '--workpath', $workDir,
    '--specpath', $specDir,
    'ngksgraph\__main__.py'
)
if ($OneFile) {
    $pyiArgs += '--onefile'
} else {
    $pyiArgs += '--onedir'
}

& $pythonExe @pyiArgs | Out-Host

$distApp = Join-Path $distDir 'ngksgraph'
$exePath = if ($OneFile) { $distApp + '.exe' } else { Join-Path $distApp 'ngksgraph.exe' }
if (-not (Test-Path $exePath)) {
    throw "Packaged executable not found: $exePath"
}

if ($OneFile) {
    Copy-Item -Path $exePath -Destination (Join-Path $stageRoot 'ngksgraph.exe') -Force
} else {
    Copy-Item -Path (Join-Path $distApp '*') -Destination $stageRoot -Recurse -Force
}

$requiredCopies = @('QUICKSTART.md', 'MIGRATION.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md')
foreach ($item in $requiredCopies) {
    $src = Join-Path $repoRoot $item
    if (-not (Test-Path $src)) {
        throw "Required packaging file missing: $src"
    }
    Copy-Item -Path $src -Destination (Join-Path $stageRoot $item) -Force
}

$exampleSrc = Join-Path $repoRoot 'examples\real_qt_widgets'
if (-not (Test-Path $exampleSrc)) {
    throw "Required example missing: $exampleSrc"
}
$exampleDst = Join-Path $stageRoot 'examples\real_qt_widgets'
New-Item -ItemType Directory -Path (Split-Path -Parent $exampleDst) -Force | Out-Null
Copy-Item -Path $exampleSrc -Destination $exampleDst -Recurse -Force

$stageExe = Join-Path $stageRoot 'ngksgraph.exe'
if (-not (Test-Path $stageExe)) {
    throw "Final staged executable missing: $stageExe"
}

$versionOutput = (& $stageExe --version).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Failed to get packaged version output"
}

$sha256 = (Get-FileHash -Path $stageExe -Algorithm SHA256).Hash.ToLowerInvariant()

$gitCommit = 'unknown'
try {
    $gitCommitProbe = (& git rev-parse --short HEAD 2>$null)
    if ($LASTEXITCODE -eq 0 -and $gitCommitProbe) {
        $gitCommit = $gitCommitProbe.Trim()
    }
} catch {
    $gitCommit = 'unknown'
}

$appVersion = (& $pythonExe -c "from ngksgraph import __version__; print(__version__)").Trim()
$pythonVersion = (& $pythonExe -c "import sys; print(sys.version.split()[0])").Trim()
$pyinstallerVersion = (& $pythonExe -m PyInstaller --version).Trim()

$manifest = [ordered]@{
    app_version = $appVersion
    git_commit = $gitCommit
    build_mode = $buildMode
    sha256_ngksgraph_exe = $sha256
    build_time_iso = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    python_runtime_version = $pythonVersion
    dependencies = [ordered]@{
        pyinstaller = $pyinstallerVersion
    }
    version_output = $versionOutput
}

$manifestPath = Join-Path $stageRoot 'manifest.json'
$manifest | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 -Path $manifestPath

$latestPathFile = Join-Path (Join-Path $repoRoot 'artifacts\package\phase10') 'latest_path.txt'
$stageRoot | Set-Content -Encoding UTF8 -Path $latestPathFile

Write-Host "PACKAGE_DIR=$stageRoot"
Write-Host "BUILD_MODE=$buildMode"
Write-Host "EXE_SHA256=$sha256"
