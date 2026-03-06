param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (!(Test-Path $python)) {
    $python = "python"
}

function Try-Get-ArgValue {
    param(
        [Parameter(Mandatory=$true)][string[]]$ArgsIn,
        [Parameter(Mandatory=$true)][string]$Name
    )
    for ($i = 0; $i -lt $ArgsIn.Count; $i++) {
        $t = $ArgsIn[$i]
        if ($t -eq $Name) {
            if ($i + 1 -lt $ArgsIn.Count) { return $ArgsIn[$i + 1] }
            return $null
        }
        if ($t -like ($Name + '=*')) {
            return $t.Substring($Name.Length + 1)
        }
    }
    return $null
}

$pf = Try-Get-ArgValue -ArgsIn $Args -Name '--pf'
$logDir = $null
$outLog = $null
$errLog = $null
if (-not [string]::IsNullOrWhiteSpace($pf)) {
    $logDir = Join-Path $pf "tool_runner"
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $outLog = Join-Path $logDir "runner_stdout.txt"
    $errLog = Join-Path $logDir "runner_stderr.txt"
}

$argv = @("-m", "ngksdevfabric") + $Args
if ($outLog -and $errLog) {
    $proc = Start-Process -FilePath $python -ArgumentList $argv -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru -Wait -NoNewWindow
    Write-Output ("runner_stdout=" + $outLog)
    Write-Output ("runner_stderr=" + $errLog)
    Write-Output ("exit_code=" + $proc.ExitCode)
    exit $proc.ExitCode
}

& $python @argv
exit $LASTEXITCODE
