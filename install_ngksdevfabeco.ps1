param(
    [string]$WheelhousePath,
    [switch]$ForceRecreateVenv,
    [switch]$UserInstall,
    [string]$Version = '1.3.2',
    [switch]$CleanupInvalidUserDistributions,
    [switch]$PersistUserScriptsPath,
    [ValidateSet('auto', 'wheelhouse', 'pypi')]
    [string]$InstallSource = 'auto'
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

function Get-UserScriptsPath {
    return (Join-Path $env:APPDATA 'Python\Python313\Scripts')
}

function Add-UserScriptsPath {
    param([switch]$Persist)
    $scriptsPath = Get-UserScriptsPath
    if (-not (Test-Path $scriptsPath)) {
        return
    }

    $pathParts = ($env:Path -split ';' | Where-Object { $_.Trim() })
    if ($pathParts -notcontains $scriptsPath) {
        $env:Path = "$env:Path;$scriptsPath"
        Write-Log "added_user_scripts_to_session_path=$scriptsPath"
    }

    if ($Persist) {
        $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
        $userParts = ($userPath -split ';' | Where-Object { $_.Trim() })
        if ($userParts -notcontains $scriptsPath) {
            $nextUserPath = if ([string]::IsNullOrWhiteSpace($userPath)) { $scriptsPath } else { "$userPath;$scriptsPath" }
            [Environment]::SetEnvironmentVariable('Path', $nextUserPath, 'User')
            Write-Log "persisted_user_scripts_path=$scriptsPath"
        }
    }
}

function Remove-InvalidUserDistributions {
    $userSite = Join-Path $env:APPDATA 'Python\Python313\site-packages'
    if (-not (Test-Path $userSite)) {
        Write-Log "user_site_not_found=$userSite"
        return
    }

    $removed = 0
    Get-ChildItem -Path $userSite -Force -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -like '~*' -or $_.Name -like '*.dist-info' -and $_.Name -like '~*'
        } |
        ForEach-Object {
            try {
                Remove-Item -Recurse -Force $_.FullName -ErrorAction Stop
                $removed += 1
                Write-Log "removed_invalid_distribution=$($_.FullName)"
            }
            catch {
                Write-Log "warn_failed_remove_invalid_distribution=$($_.FullName)"
            }
        }

    Write-Log "invalid_distribution_cleanup_removed=$removed"
}

function Resolve-InstallerPython {
    $candidates = @('py', 'python')
    foreach ($candidate in $candidates) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) {
            return $cmd.Source
        }
    }
    throw 'PYTHON_NOT_FOUND: cannot locate py or python in PATH'
}

function Test-InVirtualEnvironment {
    return -not [string]::IsNullOrWhiteSpace($env:VIRTUAL_ENV)
}

function Resolve-ComponentVersions {
    param([string]$EcoVersion)

    switch ($EcoVersion) {
        '1.3.2' {
            return @{
                devfabric  = '1.3.2'
                graph      = '0.2.0'
                buildcore  = '0.2.0'
                envcapsule = '0.2.0'
                library    = '0.2.0'
            }
        }
        '1.3.1' {
            return @{
                devfabric  = '1.3.1'
                graph      = '0.2.0'
                buildcore  = '0.2.0'
                envcapsule = '0.2.0'
                library    = '0.2.0'
            }
        }
        '1.3.0' {
            return @{
                devfabric  = '1.3.0'
                graph      = '0.2.0'
                buildcore  = '0.2.0'
                envcapsule = '0.2.0'
                library    = '0.2.0'
            }
        }
        '1.2.5' {
            return @{
                devfabric  = '1.2.5'
                graph      = '0.1.14'
                buildcore  = '0.1.8'
                envcapsule = '0.1.6'
                library    = '0.1.6'
            }
        }
        '1.2.4' {
            return @{
                devfabric  = '1.2.4'
                graph      = '0.1.13'
                buildcore  = '0.1.8'
                envcapsule = '0.1.6'
                library    = '0.1.6'
            }
        }
        '1.2.3' {
            return @{
                devfabric  = '1.2.3'
                graph      = '0.1.12'
                buildcore  = '0.1.7'
                envcapsule = '0.1.5'
                library    = '0.1.5'
            }
        }
        default {
            throw "UNSUPPORTED_VERSION_MAPPING: add component version map for ngksdevfabeco==$EcoVersion"
        }
    }
}

function Invoke-Pip {
    param(
        [string]$PythonExe,
        [string[]]$PipArgs
    )
    Invoke-Logged -Executable $PythonExe -Arguments (@('-m', 'pip') + $PipArgs)
}

function Invoke-PipSoft {
    param(
        [string]$PythonExe,
        [string[]]$PipArgs
    )
    Write-Log ("RUN_SOFT: " + $PythonExe + " -m pip " + ($PipArgs -join ' '))
    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $PythonExe -m pip @PipArgs 2>&1 | Tee-Object -FilePath $logFile -Append | Out-Host
        return [int]$LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
}

function Get-PythonSitePackagesPath {
    param(
        [string]$PythonExe,
        [switch]$UserScope
    )

    $code = if ($UserScope) {
        'import site; print(site.getusersitepackages())'
    } else {
        'import site; paths=[p for p in site.getsitepackages() if "site-packages" in p]; print(paths[0] if paths else site.getusersitepackages())'
    }

    $path = (& $PythonExe -c $code 2>$null | Select-Object -Last 1)
    if ([string]::IsNullOrWhiteSpace($path)) {
        return ""
    }
    return $path.Trim()
}

function New-NgksPackagePlan {
    param([string]$EcoVersion)

    $componentVersions = Resolve-ComponentVersions -EcoVersion $EcoVersion
    $specs = @(
        ("ngksdevfabeco==" + $EcoVersion),
        ("ngksdevfabric==" + $componentVersions['devfabric']),
        ("ngksgraph==" + $componentVersions['graph']),
        ("ngksbuildcore==" + $componentVersions['buildcore']),
        ("ngksenvcapsule==" + $componentVersions['envcapsule']),
        ("ngkslibrary==" + $componentVersions['library'])
    )
    $names = @('ngksdevfabeco', 'ngksdevfabric', 'ngksgraph', 'ngksbuildcore', 'ngksenvcapsule', 'ngkslibrary')

    return @{
        specs = $specs
        names = $names
    }
}

function Test-NgksStateDrift {
    param(
        [string]$SitePackagesPath,
        [string[]]$PackageSpecs
    )

    if (-not (Test-Path $SitePackagesPath)) {
        return $false
    }

    foreach ($spec in $PackageSpecs) {
        $parts = $spec -split '=='
        if ($parts.Count -ne 2) {
            continue
        }
        $name = $parts[0]
        $expected = $parts[1]
        $matches = Get-ChildItem -Path $SitePackagesPath -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like ($name + '-*.dist-info') }
        if ($matches.Count -gt 1) {
            Write-Log "drift_detected=duplicate_dist_info package=$name count=$($matches.Count)"
            return $true
        }
        if ($matches.Count -eq 1 -and -not $matches[0].Name.StartsWith($name + '-' + $expected + '.dist-info')) {
            Write-Log "drift_detected=version_mismatch package=$name actual=$($matches[0].Name) expected=$expected"
            return $true
        }
    }

    return $false
}

function Repair-NgksState {
    param(
        [string]$PythonExe,
        [string]$SitePackagesPath,
        [string[]]$PackageNames,
        [switch]$UserScope
    )

    Write-Log "repair_action=begin site_packages=$SitePackagesPath user_scope=$([int]$UserScope)"
    [void](Invoke-PipSoft -PythonExe $PythonExe -PipArgs (@('uninstall', '-y') + $PackageNames))

    if (Test-Path $SitePackagesPath) {
        foreach ($name in $PackageNames) {
            $pkgDir = Join-Path $SitePackagesPath $name
            if (Test-Path $pkgDir) {
                try {
                    Remove-Item -Recurse -Force $pkgDir
                    Write-Log "repair_removed=$pkgDir"
                }
                catch {
                    Write-Log "repair_warn_failed_remove=$pkgDir"
                }
            }
            Get-ChildItem -Path $SitePackagesPath -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -like ($name + '-*.dist-info') } |
                ForEach-Object {
                    try {
                        Remove-Item -Recurse -Force $_.FullName
                        Write-Log "repair_removed=$($_.FullName)"
                    }
                    catch {
                        Write-Log "repair_warn_failed_remove=$($_.FullName)"
                    }
                }
        }
    }
}

function Assert-NgksVersions {
    param(
        [string]$PythonExe,
        [string[]]$PackageSpecs
    )

    $kvPairs = @()
    foreach ($spec in $PackageSpecs) {
        $parts = $spec -split '=='
        if ($parts.Count -eq 2) {
            $kvPairs += ($parts[0] + ':' + $parts[1])
        }
    }
    $kvBlob = ($kvPairs -join ',')
    $code = @"
import importlib.metadata as m
expected = {}
for pair in "$kvBlob".split(','):
    if not pair:
        continue
    name, ver = pair.split(':', 1)
    expected[name] = ver
actual = {name: m.version(name) for name in expected.keys()}
bad = {k: (actual.get(k), v) for k, v in expected.items() if actual.get(k) != v}
print(actual)
raise SystemExit(0 if not bad else 1)
"@

    Invoke-Logged -Executable $PythonExe -Arguments @('-c', $code)
}

function Test-WheelhouseContains {
    param(
        [string]$SourcePath,
        [string]$PackageName,
        [string]$PackageVersion
    )
    $prefix = ($PackageName + '-' + $PackageVersion + '-').ToLowerInvariant()
    $wheel = Get-ChildItem -Path $SourcePath -Filter '*.whl' -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name.ToLowerInvariant().StartsWith($prefix) } |
        Select-Object -First 1
    return $null -ne $wheel
}

Write-Log "repo_root=$repoRoot"

if ($UserInstall) {
    $installerPython = Resolve-InstallerPython
    Write-Log "install_mode=user"
    Write-Log "python_executable=$installerPython"

    $venvPrompt = $false
    if (-not (Test-InVirtualEnvironment)) {
        if ([Environment]::UserInteractive) {
            $venvPrompt = $true
        }
    }

    if ($venvPrompt) {
        $answer = (Read-Host "You are not in a virtual environment. Create and activate .venv now? [Y/N]").Trim().ToUpperInvariant()
        if ($answer -eq 'Y') {
            $venvDir = Join-Path $repoRoot '.venv'
            if (-not (Test-Path $venvDir)) {
                Invoke-Logged -Executable $installerPython -Arguments @('-m', 'venv', $venvDir)
            }
            $venvPython = Join-Path $venvDir 'Scripts\python.exe'
            if (-not (Test-Path $venvPython)) {
                throw "VENV_PYTHON_MISSING: $venvPython"
            }

            $plan = New-NgksPackagePlan -EcoVersion $Version
            $packageSpecs = @($plan['specs'])
            $packageNames = @($plan['names'])
            $sitePackagesPath = Get-PythonSitePackagesPath -PythonExe $venvPython

            Invoke-Pip -PythonExe $venvPython -PipArgs @('install', '--upgrade', 'pip', 'setuptools', 'wheel')
            if (Test-NgksStateDrift -SitePackagesPath $sitePackagesPath -PackageSpecs $packageSpecs) {
                Repair-NgksState -PythonExe $venvPython -SitePackagesPath $sitePackagesPath -PackageNames $packageNames
                Invoke-Pip -PythonExe $venvPython -PipArgs (@('install', '--upgrade', '--force-reinstall', '--no-cache-dir', '--no-deps') + $packageSpecs)
            } else {
                Invoke-Pip -PythonExe $venvPython -PipArgs (@('install', '--upgrade') + $packageSpecs)
            }
            Assert-NgksVersions -PythonExe $venvPython -PackageSpecs $packageSpecs
            Invoke-Pip -PythonExe $venvPython -PipArgs (@('show') + $packageNames)
            Invoke-Pip -PythonExe $venvPython -PipArgs @('check')

            Invoke-Logged -Executable $venvPython -Arguments @('-m', 'ngksdevfabric', '--help')
            Invoke-Logged -Executable $venvPython -Arguments @('-m', 'ngksdevfabric', 'predict-risk', '--help')

            @(
                "repo_root=$repoRoot",
                "install_mode=venv_prompted",
                "venv=$venvDir",
                "version=$Version",
                "status=PASS"
            ) | Set-Content -Encoding UTF8 (Join-Path $proofDir 'result.txt')

            Write-Host "INSTALL_OK mode=venv version=$Version proof=$proofDir"
            return
        }
        Write-Log 'venv_prompt_response=N continuing with user install'
    }

    if ($CleanupInvalidUserDistributions) {
        Remove-InvalidUserDistributions
    }

    Add-UserScriptsPath -Persist:$PersistUserScriptsPath

    $plan = New-NgksPackagePlan -EcoVersion $Version
    $packageSpecs = @($plan['specs'])
    $packageNames = @($plan['names'])
    $userSitePackagesPath = Get-PythonSitePackagesPath -PythonExe $installerPython -UserScope

    Invoke-Pip -PythonExe $installerPython -PipArgs @('install', '--user', '--upgrade', 'pip', 'setuptools', 'wheel')
    if (Test-NgksStateDrift -SitePackagesPath $userSitePackagesPath -PackageSpecs $packageSpecs) {
        Repair-NgksState -PythonExe $installerPython -SitePackagesPath $userSitePackagesPath -PackageNames $packageNames -UserScope
        Invoke-Pip -PythonExe $installerPython -PipArgs (@('install', '--user', '--upgrade', '--force-reinstall', '--no-cache-dir', '--no-deps') + $packageSpecs)
    } else {
        Invoke-Pip -PythonExe $installerPython -PipArgs (@('install', '--user', '--upgrade') + $packageSpecs)
    }
    Assert-NgksVersions -PythonExe $installerPython -PackageSpecs $packageSpecs
    Invoke-Pip -PythonExe $installerPython -PipArgs (@('show') + $packageNames)
    Invoke-Pip -PythonExe $installerPython -PipArgs @('check')

    Invoke-Logged -Executable $installerPython -Arguments @('-m', 'ngksdevfabric', '--help')
    Invoke-Logged -Executable $installerPython -Arguments @('-m', 'ngksdevfabric', 'predict-risk', '--help')

    @(
        "repo_root=$repoRoot",
        "install_mode=user",
        "version=$Version",
        "status=PASS"
    ) | Set-Content -Encoding UTF8 (Join-Path $proofDir 'result.txt')

    Write-Host "INSTALL_OK mode=user version=$Version proof=$proofDir"
    return
}

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
Write-Log "install_mode=venv"
Write-Log "version=$Version"
Write-Log "install_source=$InstallSource"

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
Invoke-Logged -Executable $venvPython -Arguments @('-m', 'pip', 'install', '--upgrade', 'setuptools', 'wheel')
$plan = New-NgksPackagePlan -EcoVersion $Version
$packages = @($plan['specs'])
$packageNames = @($plan['names'])
$sitePackagesPath = Get-PythonSitePackagesPath -PythonExe $venvPython

$canUseWheelhouse = $true
foreach ($spec in $packages) {
    $parts = $spec -split '=='
    if ($parts.Count -ne 2) {
        continue
    }
    if (-not (Test-WheelhouseContains -SourcePath $wheelSource -PackageName $parts[0] -PackageVersion $parts[1])) {
        $canUseWheelhouse = $false
        Write-Log "wheelhouse_missing_package=$spec"
    }
}

$useWheelhouse = $false
if ($InstallSource -eq 'wheelhouse') {
    if (-not $canUseWheelhouse) {
        throw "WHEELHOUSE_INCOMPLETE_FOR_REQUESTED_VERSION: $wheelSource"
    }
    $useWheelhouse = $true
} elseif ($InstallSource -eq 'pypi') {
    $useWheelhouse = $false
} else {
    $useWheelhouse = $canUseWheelhouse
}

if ($useWheelhouse) {
    Write-Log 'install_path=wheelhouse'
    if (Test-NgksStateDrift -SitePackagesPath $sitePackagesPath -PackageSpecs $packages) {
        Repair-NgksState -PythonExe $venvPython -SitePackagesPath $sitePackagesPath -PackageNames $packageNames
    }
    Invoke-Logged -Executable $venvPython -Arguments (@('-m', 'pip', 'install', '--no-index', '--no-cache-dir', '--force-reinstall', '--find-links', $wheelSource) + $packages)
} else {
    Write-Log 'install_path=pypi'
    if (Test-NgksStateDrift -SitePackagesPath $sitePackagesPath -PackageSpecs $packages) {
        Repair-NgksState -PythonExe $venvPython -SitePackagesPath $sitePackagesPath -PackageNames $packageNames
        Invoke-Logged -Executable $venvPython -Arguments (@('-m', 'pip', 'install', '--upgrade', '--force-reinstall', '--no-cache-dir', '--no-deps') + $packages)
    } else {
        Invoke-Logged -Executable $venvPython -Arguments (@('-m', 'pip', 'install', '--upgrade') + $packages)
    }
}

Assert-NgksVersions -PythonExe $venvPython -PackageSpecs $packages
Invoke-Logged -Executable $venvPython -Arguments (@('-m', 'pip', 'show') + $packageNames)
Invoke-Logged -Executable $venvPython -Arguments @('-m', 'pip', 'check')
Invoke-Logged -Executable $venvPython -Arguments @('-m', 'ngksgraph', '--help')
Invoke-Logged -Executable $venvPython -Arguments @('-m', 'ngksbuildcore', '--help')
Invoke-Logged -Executable $venvPython -Arguments @('-m', 'ngksdevfabric', '--help')
Invoke-Logged -Executable $venvPython -Arguments @('-m', 'ngksdevfabric', 'predict-risk', '--help')

@(
    "repo_root=$repoRoot",
    "wheelhouse=$wheelSource",
    "venv=$venvDir",
    "version=$Version",
    "status=PASS"
) | Set-Content -Encoding UTF8 (Join-Path $proofDir 'result.txt')

Write-Host "INSTALL_OK proof=$proofDir"
