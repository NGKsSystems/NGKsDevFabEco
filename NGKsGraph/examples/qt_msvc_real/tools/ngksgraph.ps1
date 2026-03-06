param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgsRest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$cwd = (Get-Location).Path
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$proofRoot = Join-Path $cwd "_proof"
$pf = Join-Path $proofRoot ("ngksgraph_wrap_" + $ts)
New-Item -ItemType Directory -Force -Path $pf | Out-Null

$pwdFile = Join-Path $pf "01_pwd.txt"
$pythonFile = Join-Path $pf "02_python_selected.txt"
$cmdlineFile = Join-Path $pf "03_cmdline.txt"
$stdoutFile = Join-Path $pf "04_stdout.txt"
$stderrFile = Join-Path $pf "05_stderr.txt"
$exitFile = Join-Path $pf "06_exitcode.txt"

$cwd | Out-File -FilePath $pwdFile -Encoding utf8
"" | Out-File -FilePath $pythonFile -Encoding utf8
"" | Out-File -FilePath $cmdlineFile -Encoding utf8
"" | Out-File -FilePath $stdoutFile -Encoding utf8
"" | Out-File -FilePath $stderrFile -Encoding utf8
"" | Out-File -FilePath $exitFile -Encoding utf8

if (-not (Test-Path (Join-Path $cwd "ngksgraph.toml"))) {
    "<missing>" | Out-File -FilePath $pythonFile -Encoding utf8
    "root_guard_failed" | Out-File -FilePath $cmdlineFile -Encoding utf8
    "1" | Out-File -FilePath $exitFile -Encoding utf8
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
    "<not-found>" | Out-File -FilePath $pythonFile -Encoding utf8
    $msg | Out-File -FilePath $stderrFile -Encoding utf8
    "2" | Out-File -FilePath $exitFile -Encoding utf8
    [Console]::Error.WriteLine($msg)
    $global:LASTEXITCODE = 2
    return
}

("source=" + $source + "`npython=" + $py) | Out-File -FilePath $pythonFile -Encoding utf8

$forward = @("-m", "ngksgraph") + $ArgsRest
$hasProject = $false
for ($i = 0; $i -lt $ArgsRest.Count; $i++) {
    $a = $ArgsRest[$i]
    if ($a -eq "--project") { $hasProject = $true; break }
}
if (-not $hasProject) {
    $forward += @("--project", $cwd)
}

function Quote-Arg {
    param([string]$value)
    if ($null -eq $value) { return '""' }
    if ($value -notmatch '[\s\"]') { return $value }
    return '"' + ($value -replace '"', '\\"') + '"'
}

$argLine = ($forward | ForEach-Object { Quote-Arg $_ }) -join " "
("python=" + $py + "`nargs=" + $argLine) | Out-File -FilePath $cmdlineFile -Encoding utf8

Push-Location $cwd
try {
    & $py @forward 1> $stdoutFile 2> $stderrFile
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

if (Test-Path $stdoutFile) {
    Get-Content $stdoutFile | ForEach-Object { Write-Host $_ }
}
if (Test-Path $stderrFile) {
    Get-Content $stderrFile | ForEach-Object { [Console]::Error.WriteLine($_) }
}

("" + $exitCode) | Out-File -FilePath $exitFile -Encoding utf8
$global:LASTEXITCODE = $exitCode
return
