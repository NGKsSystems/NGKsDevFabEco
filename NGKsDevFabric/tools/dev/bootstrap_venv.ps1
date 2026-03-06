param(
  [string]$RepoRoot = "C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabric"
)

$ErrorActionPreference = 'Stop'

Set-Location $RepoRoot
if ((Get-Location).Path -ne $RepoRoot) { throw 'ROOT_GUARD_FAIL' }
if (!(Test-Path (Join-Path $RepoRoot 'pyproject.toml'))) { throw 'ROOT_GUARD_FAIL' }

$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$pf = Join-Path $RepoRoot ("_proof\devfabric_bootstrap_" + $ts)
New-Item -ItemType Directory -Force -Path $pf | Out-Null

function Write-RunArtifact {
  param(
    [string]$Label,
    [string]$FilePath,
    [string[]]$ArgumentList
  )

  $artifact = Join-Path $pf ($Label + '.txt')
  $stdout = $artifact + '.stdout'
  $stderr = $artifact + '.stderr'

  $old = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    $proc = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -NoNewWindow -PassThru -Wait `
      -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $exitCode = $proc.ExitCode
  } finally {
    $ErrorActionPreference = $old
  }

  "=== EXE ===" | Out-File $artifact -Encoding UTF8
  $FilePath | Add-Content $artifact -Encoding UTF8
  "=== ARGS ===" | Add-Content $artifact -Encoding UTF8
  (($ArgumentList | ForEach-Object { $_ }) -join ' ') | Add-Content $artifact -Encoding UTF8
  "=== STDOUT ===" | Add-Content $artifact -Encoding UTF8
  if (Test-Path $stdout) { Get-Content $stdout | Add-Content $artifact -Encoding UTF8 }
  "=== STDERR ===" | Add-Content $artifact -Encoding UTF8
  if (Test-Path $stderr) { Get-Content $stderr | Add-Content $artifact -Encoding UTF8 }
  "=== EXITCODE ===" | Add-Content $artifact -Encoding UTF8
  ("EXITCODE=" + $exitCode) | Add-Content $artifact -Encoding UTF8

  Remove-Item $stdout, $stderr -ErrorAction SilentlyContinue

  if ($exitCode -ne 0) { throw "Command failed ($Label) exit=$exitCode (see $artifact)" }
}

$venvPath = Join-Path $RepoRoot '.venv'
if (!(Test-Path $venvPath)) {
  Write-RunArtifact -Label '10_create_venv' -FilePath 'python' -ArgumentList @('-m','venv',$venvPath)
}

$venvPy = Join-Path $venvPath 'Scripts\python.exe'
if (!(Test-Path $venvPy)) { throw "Missing venv python: $venvPy" }

Write-RunArtifact -Label '20_pip_version' -FilePath $venvPy -ArgumentList @('-m','pip','--version')
Write-RunArtifact -Label '30_pip_tooling_upgrade' -FilePath $venvPy -ArgumentList @('-m','pip','install','-U','pip','setuptools','wheel')
Write-RunArtifact -Label '40_install_editable_dev' -FilePath $venvPy -ArgumentList @('-m','pip','install','-e','.[dev]')
Write-RunArtifact -Label '50_pytest_q' -FilePath $venvPy -ArgumentList @('-m','pytest','-q')

@"
bootstrap_venv completed
repo=$RepoRoot
venv=$venvPath
"@ | Set-Content (Join-Path $pf '99_summary.txt') -Encoding UTF8

"PF=$pf"