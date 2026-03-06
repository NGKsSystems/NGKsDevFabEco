param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgsRest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$cwd = (Get-Location).Path
if (-not (Test-Path (Join-Path $cwd "ngksgraph.toml"))) {
    Write-Host "hey stupid Fucker, wrong window again"
    $global:LASTEXITCODE = 1
    return
}

$py = $null
$source = $null
if ($env:NGKSTOOLS_PY -and (Test-Path $env:NGKSTOOLS_PY -PathType Leaf)) {
    $py = $env:NGKSTOOLS_PY
    $source = "env:NGKSTOOLS_PY"
}
else {
    $fallback = Join-Path $env:USERPROFILE "NGKsTools\.venv\Scripts\python.exe"
    if (Test-Path $fallback -PathType Leaf) {
        $py = $fallback
        $source = "%USERPROFILE%\\NGKsTools\\.venv\\Scripts\\python.exe"
    }
}

if (-not $py) {
    $msg = "NGKSTOOLS_PY_NOT_FOUND: set NGKSTOOLS_PY or install to %USERPROFILE%\NGKsTools\.venv"
    [Console]::Error.WriteLine($msg)
    $global:LASTEXITCODE = 2
    return
}

$forward = @("-m", "ngksgraph") + $ArgsRest
$hasProject = $false
for ($i = 0; $i -lt $ArgsRest.Count; $i++) {
    $a = $ArgsRest[$i]
    if ($a -eq "--project") { $hasProject = $true; break }
}
if (-not $hasProject) {
    $forward += @("--project", $cwd)
}
$global:LASTEXITCODE = 0
& $py @forward
$global:LASTEXITCODE = $LASTEXITCODE
return
