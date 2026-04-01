param(
    [string]$OutputRoot,
    [string]$WheelhousePath,
    [string]$BundleVersion,
    [ValidateSet('dev', 'candidate', 'stable')]
    [string]$Channel = 'candidate',
    [string]$CertificationProofReference,
    [string]$CertificationState = 'CERTIFICATION_ENFORCED'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path $repoRoot)) {
    throw "REPO_ROOT_NOT_FOUND: $repoRoot"
}

if (-not $OutputRoot) {
    $OutputRoot = Join-Path $repoRoot 'releases'
}
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

if (-not $BundleVersion) {
    $pyprojectPath = Join-Path $repoRoot 'pyproject.toml'
    if (-not (Test-Path $pyprojectPath)) {
        throw "PYPROJECT_NOT_FOUND: $pyprojectPath"
    }
    $pyprojectRaw = Get-Content -Path $pyprojectPath -Raw
    $versionMatch = [regex]::Match($pyprojectRaw, '(?m)^version\s*=\s*"([^"]+)"')
    if (-not $versionMatch.Success) {
        throw 'BUNDLE_VERSION_NOT_FOUND_IN_PYPROJECT'
    }
    $BundleVersion = $versionMatch.Groups[1].Value
}

if (-not $CertificationProofReference) {
    throw 'CERTIFICATION_PROOF_REFERENCE_REQUIRED'
}

$wheelSource = $null
if ($WheelhousePath) {
    $wheelSource = (Resolve-Path $WheelhousePath).Path
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
if (-not (Test-Path $wheelSource)) {
    throw "WHEEL_SOURCE_NOT_FOUND: $wheelSource"
}

$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$bundleDir = Join-Path $OutputRoot ("ngksdevfabeco_release_" + $ts)
New-Item -ItemType Directory -Force -Path $bundleDir | Out-Null

$readmeCandidate = Join-Path $repoRoot 'README.md'
if (-not (Test-Path $readmeCandidate)) {
    $readmeCandidate = Join-Path $repoRoot 'NGKsDevFabric\README.md'
}
if (-not (Test-Path $readmeCandidate)) {
    throw "README_NOT_FOUND"
}
Copy-Item -Force $readmeCandidate (Join-Path $bundleDir 'README.md')

$licenseCandidate = Join-Path $repoRoot 'LICENSE'
if (-not (Test-Path $licenseCandidate)) {
    $licenseCandidate = Join-Path $repoRoot 'NGKsGraph\LICENSE'
}
if (Test-Path $licenseCandidate) {
    Copy-Item -Force $licenseCandidate (Join-Path $bundleDir 'LICENSE')
}

Copy-Item -Force (Join-Path $repoRoot 'install_ngksdevfabeco.ps1') (Join-Path $bundleDir 'install_ngksdevfabeco.ps1')
Copy-Item -Force (Join-Path $repoRoot 'uninstall_ngksdevfabeco.ps1') (Join-Path $bundleDir 'uninstall_ngksdevfabeco.ps1')
Copy-Item -Force (Join-Path $repoRoot 'verify_release_integrity.ps1') (Join-Path $bundleDir 'verify_release_integrity.ps1')

$bundleToolsDir = Join-Path $bundleDir 'tools'
New-Item -ItemType Directory -Force -Path $bundleToolsDir | Out-Null

$toolFiles = @(
    '_update_common.ps1',
    'install_update.ps1',
    'activate_version.ps1',
    'rollback_last.ps1',
    'get_active_version.ps1',
    'generate_release_integrity.ps1'
)

foreach ($toolFile in $toolFiles) {
    $sourceTool = Join-Path $repoRoot ('tools\' + $toolFile)
    if (-not (Test-Path $sourceTool)) {
        throw "REQUIRED_TOOL_NOT_FOUND: $sourceTool"
    }
    Copy-Item -Force $sourceTool (Join-Path $bundleToolsDir $toolFile)
}

$bundleWheelDir = Join-Path $bundleDir 'wheelhouse'
New-Item -ItemType Directory -Force -Path $bundleWheelDir | Out-Null
Get-ChildItem -Path $wheelSource -Filter '*.whl' -File | ForEach-Object {
    Copy-Item -Force $_.FullName (Join-Path $bundleWheelDir $_.Name)
}

$wheelCount = (Get-ChildItem -Path $bundleWheelDir -Filter '*.whl' -File | Measure-Object).Count
if ($wheelCount -eq 0) {
    throw "BUNDLE_WHEEL_COPY_EMPTY from $wheelSource"
}

$sourceCommit = (& git -C $repoRoot rev-parse HEAD).Trim()
if (-not $sourceCommit) {
    throw 'SOURCE_COMMIT_RESOLUTION_FAILED'
}

$integrityScript = Join-Path $bundleToolsDir 'generate_release_integrity.ps1'
& pwsh -ExecutionPolicy Bypass -File $integrityScript `
    -SourceCommit $sourceCommit `
    -CertificationProofReference $CertificationProofReference `
    -CertificationState $CertificationState `
    -BundleVersion $BundleVersion `
    -Channel $Channel

if ($LASTEXITCODE -ne 0) {
    throw "INTEGRITY_GENERATION_FAILED exit=$LASTEXITCODE"
}

$bundleMetaPath = Join-Path $bundleDir 'bundle_meta.txt'
$manifest = Get-Content -Path (Join-Path $bundleDir 'RELEASE_MANIFEST.json') -Raw | ConvertFrom-Json
$bundleMeta = @(
    ('bundle_dir=' + $bundleDir),
    ('wheel_source=' + $wheelSource),
    ('wheel_count=' + $wheelCount),
    ('bundle_version=' + $manifest.bundle_version),
    ('release_channel=' + $manifest.release_channel),
    ('semver_full=' + $manifest.semver_full),
    ('source_commit=' + $manifest.source_commit)
)
$bundleMeta | Set-Content -Path $bundleMetaPath -Encoding UTF8

Write-Host "BUNDLE_OK path=$bundleDir"
