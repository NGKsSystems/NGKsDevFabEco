# NGKsDevFabric - ngk.ps1
# Command-agnostic dispatcher: ngk <command> [args...]
# Manual parsing (no ParameterBinding surprises).
#
# Option A behavior:
# - build/ship/resolve execute downstream scripts via fresh powershell.exe -File
# - downstream stdout/stderr is captured to a log file under PF (if provided)
# - ngk prints ONLY its own summary (no duplicate receipts)
#
# ship is an alias of build.

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot   = Split-Path -Parent $scriptRoot

function Show-Help {
    @(
        'ngk <command> [args]'
        'commands: probe, profile, resolve, build, ship, verify'
        'use: ngk --help'
        ''
        'build/ship/resolve convenience:'
        '  -Target <path> / --target <path>'
        '  -PfPath <path> / --pf <path>'
        '  --backup-root <path> (required when --pf is omitted)'
        ''
        'examples:'
        '  ngk build -Target C:\Work\Proj --backup-root D:\Backups'
        '  ngk ship  C:\Work\Proj --pf C:\Work\pf'
        '  ngk verify'
    ) | Write-Output
}

function Normalize-Tokens {
    param([string[]]$Tokens)

    # Convert friendly GNU-ish flags into the canonical PowerShell param names
    $out = New-Object System.Collections.Generic.List[string]
    for ($i = 0; $i -lt $Tokens.Count; $i++) {
        $t = $Tokens[$i]

        if ($t -eq '--pf')           { $out.Add('-PfPath'); continue }
        if ($t -eq '--target')       { $out.Add('-Target'); continue }
        if ($t -eq '--backup-root')  { $out.Add('--backup-root'); continue }

        if ($t -like '--pf=*') {
            $out.Add('-PfPath')
            $out.Add($t.Substring(5))
            continue
        }
        if ($t -like '--target=*') {
            $out.Add('-Target')
            $out.Add($t.Substring(9))
            continue
        }
        if ($t -like '--backup-root=*') {
            $out.Add('--backup-root')
            $out.Add($t.Substring(14))
            continue
        }

        $out.Add($t)
    }
    return ,$out.ToArray()
}

function Ensure-Target-For {
    param(
        [Parameter(Mandatory=$true)][string]$Cmd,
        [Parameter(Mandatory=$true)][string[]]$ArgsIn
    )

    # For build/ship/resolve, allow: ngk build <TargetPath> ...
    # If no explicit -Target is provided, default to git root of current cwd (or cwd).
    $cmdLower = $Cmd.ToLower()
    if ($cmdLower -notin @('build','ship','resolve')) { return ,$ArgsIn }

    $hasTarget = $false
    foreach ($a in $ArgsIn) { if ($a -eq '-Target') { $hasTarget = $true; break } }

    if (-not $hasTarget -and $ArgsIn.Count -gt 0) {
        $first = $ArgsIn[0]
        if (-not [string]::IsNullOrWhiteSpace($first) -and -not $first.StartsWith('-')) {
            $tmp = New-Object System.Collections.Generic.List[string]
            $tmp.Add('-Target')
            foreach ($x in $ArgsIn) { $tmp.Add($x) }
            return ,$tmp.ToArray()
        }
    }

    if (-not $hasTarget) {
        $target = $null
        try {
            $gitTop = (& git -C (Get-Location).Path rev-parse --show-toplevel 2>$null)
            if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($gitTop)) {
                $target = $gitTop.Trim()
            }
        } catch {}
        if ([string]::IsNullOrWhiteSpace($target)) {
            $target = (Get-Location).Path
        }

        $tmp = New-Object System.Collections.Generic.List[string]
        $tmp.Add('-Target')
        $tmp.Add($target)
        foreach ($x in $ArgsIn) { $tmp.Add($x) }
        return ,$tmp.ToArray()
    }

    return ,$ArgsIn
}

function Try-Get-ArgValue {
    param(
        [Parameter(Mandatory=$true)][string[]]$ArgsIn,
        [Parameter(Mandatory=$true)][string]$Name
    )

    # Supports: -PfPath <v>   or   -PfPath=<v>
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

function Write-Summary {
    param(
        [Parameter(Mandatory=$true)][string]$Cmd,
        [Parameter(Mandatory=$true)][int]$ExitCode,
        [string]$PfPath
    )

    if (-not [string]::IsNullOrWhiteSpace($PfPath)) {
        Write-Output ("PF=" + $PfPath)
        Write-Output ("proof_dir=" + $PfPath)
    }
    Write-Output ("exit_code=" + $ExitCode)

    if ([string]::IsNullOrWhiteSpace($PfPath)) { return }

    $probe = Join-Path $PfPath 'probe_report.json'
    if (Test-Path $probe) { Write-Output ("probe_report=" + $probe) }

    $pwr = Join-Path $PfPath 'profile_write_receipt.json'
    if (Test-Path $pwr) { Write-Output ("profile_write_receipt=" + $pwr) }

    $runBuild = Join-Path $PfPath 'run_build'
    if (Test-Path $runBuild) { Write-Output ("build_run_dir=" + $runBuild) }

    if ($Cmd.ToLower() -in @('build','ship') -and (Test-Path $runBuild)) {
        if ($ExitCode -eq 0) {
            Write-Output ("PHASE12_REPLAY_OK PF=" + $PfPath)
        } else {
            Write-Output ("PHASE12_REPLAY_FAIL PF=" + $PfPath)
        }
    }
}

function Invoke-PhaseScriptFresh {
    param(
        [Parameter(Mandatory=$true)][string]$ScriptPath,
        [Parameter(Mandatory=$true)][string[]]$ArgsIn,
        [string]$PfPath,
        [string]$LogName
    )

    # Option A: suppress child output to console; capture to PF log if PF provided.
    $logFile = $null
    if (-not [string]::IsNullOrWhiteSpace($PfPath)) {
        $logBase = if ([string]::IsNullOrWhiteSpace($LogName)) { 'ngk_child_out.txt' } else { $LogName }
        $logFile = Join-Path $PfPath $logBase
    }

    # IMPORTANT: do NOT let native stderr become terminating just because our wrapper uses EAP=Stop.
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if ($logFile) {
            $null = & powershell -NoProfile -ExecutionPolicy Bypass -File $ScriptPath $ArgsIn 2>&1 |
                Out-File -FilePath $logFile -Encoding utf8
        } else {
            $null = & powershell -NoProfile -ExecutionPolicy Bypass -File $ScriptPath $ArgsIn 2>&1 | Out-Null
        }
    } finally {
        $ErrorActionPreference = $prevEap
    }

    return [int]$LASTEXITCODE
}
# ---- Entry: parse raw $args ----
if ($args.Count -eq 0 -or $args[0] -in @('--help','-h','help')) {
    Show-Help
    exit 0
}

$cmd  = [string]$args[0]
$rest = @()
if ($args.Count -gt 1) { $rest = $args[1..($args.Count-1)] }

$rest = Normalize-Tokens -Tokens $rest
$rest = Ensure-Target-For -Cmd $cmd -ArgsIn $rest

switch ($cmd.ToLower()) {
    'probe' {
        & (Join-Path $scriptRoot 'ngk_fabric.ps1') @rest
        exit $LASTEXITCODE
    }
    'profile' {
        & (Join-Path $scriptRoot 'ngk_fabric.ps1') @rest
        exit $LASTEXITCODE
    }
    'resolve' {
        $script = Join-Path $scriptRoot 'phase15_graph_only_lock_gate.ps1'
        $pf = Try-Get-ArgValue -ArgsIn $rest -Name '-PfPath'
        $ec = Invoke-PhaseScriptFresh -ScriptPath $script -ArgsIn $rest -PfPath $pf -LogName 'ngk_resolve_out.txt'
        Write-Summary -Cmd 'resolve' -ExitCode $ec -PfPath $pf
        exit $ec
    }
    'build' {
        $script = Join-Path $scriptRoot 'phase12_runner.ps1'
        $pf = Try-Get-ArgValue -ArgsIn $rest -Name '-PfPath'
        $ec = Invoke-PhaseScriptFresh -ScriptPath $script -ArgsIn $rest -PfPath $pf -LogName 'ngk_build_out.txt'
        Write-Summary -Cmd 'build' -ExitCode $ec -PfPath $pf
        exit $ec
    }
    'ship' {
        # ship is an alias of build
        $script = Join-Path $scriptRoot 'phase12_runner.ps1'
        $pf = Try-Get-ArgValue -ArgsIn $rest -Name '-PfPath'
        $ec = Invoke-PhaseScriptFresh -ScriptPath $script -ArgsIn $rest -PfPath $pf -LogName 'ngk_ship_out.txt'
        Write-Summary -Cmd 'ship' -ExitCode $ec -PfPath $pf
        exit $ec
    }
    'verify' {
        & (Join-Path $scriptRoot 'phase17_verify.ps1') -Root $repoRoot @rest
        exit $LASTEXITCODE
    }
    default {
        Write-Error ('Unknown command: ' + $cmd)
        Show-Help
        exit 1
    }
}