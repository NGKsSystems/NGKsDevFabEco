#Requires -Version 5.0
param(
    [Parameter(Mandatory=$true)]
    [string]$ProofFolder,
    [string]$RuntimeRoot = 'C:\Users\suppo\Desktop\NGKsSystems\NGKsUI Runtime'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not (Test-Path -LiteralPath $ProofFolder -PathType Container)) {
    Write-Error "ProofFolder not found: $ProofFolder"; exit 1
}

$exe = Join-Path $RuntimeRoot 'build\debug\bin\widget_sandbox.exe'
$launcher = Join-Path $RuntimeRoot 'tools\run_widget_sandbox.ps1'
$artFile = Join-Path $RuntimeRoot 'control_plane\111_trust_chain_ledger_baseline_enforcement_surface_fingerprint_regression_anchor_trust_chain_baseline.json'
$gateScript = Join-Path $RuntimeRoot 'tools\phase53_2\phase53_2_runtime_gate_enforce.ps1'

foreach ($p in @($exe, $launcher, $artFile, $gateScript)) {
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) {
        Write-Error "Required file missing: $p"; exit 1
    }
}

$exeBak = "$exe.phase53_4_bak"
$artBak = "$artFile.phase53_4_bak"
$gateBak = "$gateScript.phase53_4_bak"

function Restore-State {
    if (Test-Path -LiteralPath $exeBak) { Move-Item -LiteralPath $exeBak -Destination $exe -Force }
    if (Test-Path -LiteralPath $artBak) { Move-Item -LiteralPath $artBak -Destination $artFile -Force }
    if (Test-Path -LiteralPath $gateBak) { Move-Item -LiteralPath $gateBak -Destination $gateScript -Force }
}

function Write-Case {
    param(
        [string]$FileName,
        [string]$Label,
        [string]$Manipulation,
        [string]$Command,
        [int]$ExitCode,
        [string]$Output,
        [string]$Expected
    )
    $class = if ($ExitCode -eq 0) { 'ALLOW' } else { 'BLOCK' }
    @(
        "LABEL=$Label",
        "MANIPULATION=$Manipulation",
        "COMMAND=$Command",
        "EXIT=$ExitCode",
        "CLASSIFICATION=$class",
        "EXPECTED=$Expected",
        "UTC=$([DateTime]::UtcNow.ToString('o'))",
        "---OUTPUT---",
        $Output
    ) | Set-Content -LiteralPath (Join-Path $ProofFolder $FileName) -Encoding UTF8
}

function Run-Native-Demo {
    Push-Location -LiteralPath $RuntimeRoot
    try {
        try {
            $out = (& $exe '--demo' 2>&1 | Out-String)
            $code = $LASTEXITCODE
            return @{ Output = $out; ExitCode = $code }
        }
        catch {
            # Preserve fail-closed behavior: any launch failure is a BLOCK result.
            return @{ Output = ($_.Exception.Message | Out-String); ExitCode = 9009 }
        }
    } finally {
        Pop-Location
    }
}

function Run-Script-Demo {
    $cmd = "Set-Location '$RuntimeRoot'; & '$launcher' -Config Debug -PassArgs '--demo'"
    try {
        $out = (& pwsh -NoProfile -ExecutionPolicy Bypass -Command $cmd 2>&1 | Out-String)
        $code = $LASTEXITCODE
        return @{ Output = $out; ExitCode = $code }
    }
    catch {
        return @{ Output = ($_.Exception.Message | Out-String); ExitCode = 9009 }
    }
}

try {
    # Original baseline 4 cases
    Restore-State
    $r = Run-Native-Demo
    Write-Case -FileName '10_native_clean.txt' -Label 'direct_native_clean' -Manipulation 'none' -Command "& '$exe' '--demo'" -ExitCode $r.ExitCode -Output $r.Output -Expected 'ALLOW'

    Restore-State
    Copy-Item -LiteralPath $artFile -Destination $artBak -Force
    Add-Content -LiteralPath $artFile -Value "`n " -Encoding UTF8
    $r = Run-Native-Demo
    Write-Case -FileName '11_native_tampered.txt' -Label 'direct_native_tampered' -Manipulation 'append whitespace to control_plane/111' -Command "& '$exe' '--demo'" -ExitCode $r.ExitCode -Output $r.Output -Expected 'BLOCK'
    Restore-State

    Restore-State
    $r = Run-Script-Demo
    Write-Case -FileName '20_script_clean.txt' -Label 'script_clean' -Manipulation 'none' -Command "pwsh -File '$launcher' -Config Debug -PassArgs '--demo'" -ExitCode $r.ExitCode -Output $r.Output -Expected 'ALLOW'

    Restore-State
    Copy-Item -LiteralPath $artFile -Destination $artBak -Force
    Add-Content -LiteralPath $artFile -Value "`n " -Encoding UTF8
    $r = Run-Script-Demo
    Write-Case -FileName '21_script_tampered.txt' -Label 'script_tampered' -Manipulation 'append whitespace to control_plane/111' -Command "pwsh -File '$launcher' -Config Debug -PassArgs '--demo'" -ExitCode $r.ExitCode -Output $r.Output -Expected 'BLOCK'
    Restore-State

    # A. Binary mutation
    Restore-State
    Copy-Item -LiteralPath $exe -Destination $exeBak -Force
    $bytes = [System.IO.File]::ReadAllBytes($exe)
    $bytes[128] = ($bytes[128] -bxor 0x5A)
    [System.IO.File]::WriteAllBytes($exe, $bytes)
    $r = Run-Native-Demo
    Write-Case -FileName '30_binary_mutation.txt' -Label 'binary_mutation' -Manipulation 'flip byte at offset 128 in widget_sandbox.exe' -Command "& '$exe' '--demo'" -ExitCode $r.ExitCode -Output $r.Output -Expected 'BLOCK'
    Restore-State

    # B. Hash mismatch (control plane modify)
    Restore-State
    Copy-Item -LiteralPath $artFile -Destination $artBak -Force
    Add-Content -LiteralPath $artFile -Value "`n#phase53_4_hash_mismatch" -Encoding UTF8
    $r = Run-Native-Demo
    Write-Case -FileName '31_hash_mismatch.txt' -Label 'hash_mismatch' -Manipulation 'modify baseline json after seal' -Command "& '$exe' '--demo'" -ExitCode $r.ExitCode -Output $r.Output -Expected 'BLOCK'
    Restore-State

    # C. Loader path injection (spoof cwd)
    Restore-State
    $spoof = 'C:\Windows\Temp'
    $out = (& pwsh -NoProfile -ExecutionPolicy Bypass -Command "Set-Location '$spoof'; & '$exe' '--demo'" 2>&1 | Out-String)
    $code = $LASTEXITCODE
    Write-Case -FileName '32_loader_injection.txt' -Label 'loader_path_injection' -Manipulation 'launch binary from spoofed cwd' -Command "Set-Location '$spoof'; & '$exe' '--demo'" -ExitCode $code -Output $out -Expected 'BLOCK'

    # D. Environment variable injection
    Restore-State
    $envCmd = @'
$env:NGKS_RUNTIME_ROOT='C:\malicious'
$env:NGKS_BYPASS_GUARD='1'
Set-Location '__RUNTIME_ROOT__'
& '__EXE__' '--demo'
'@
    $envCmd = $envCmd.Replace('__RUNTIME_ROOT__', $RuntimeRoot).Replace('__EXE__', $exe)
    $out = (& pwsh -NoProfile -ExecutionPolicy Bypass -Command $envCmd 2>&1 | Out-String)
    $code = $LASTEXITCODE
    Write-Case -FileName '33_env_injection.txt' -Label 'environment_injection' -Manipulation 'inject NGKS_* env vars before launch' -Command "NGKS_RUNTIME_ROOT=C:\malicious; NGKS_BYPASS_GUARD=1; & '$exe' '--demo'" -ExitCode $code -Output $out -Expected 'BLOCK'

    # E. Script wrapper bypass attempt (attempt to bypass wrapper via direct call from wrong cwd)
    Restore-State
    $out = (& pwsh -NoProfile -ExecutionPolicy Bypass -Command "Set-Location 'C:\'; & '$exe' '--demo'" 2>&1 | Out-String)
    $code = $LASTEXITCODE
    Write-Case -FileName '34_wrapper_bypass.txt' -Label 'wrapper_bypass_attempt' -Manipulation 'direct binary invocation from non-runtime cwd' -Command "Set-Location 'C:\'; & '$exe' '--demo'" -ExitCode $code -Output $out -Expected 'BLOCK'

    # F. Partial file truncation
    Restore-State
    Copy-Item -LiteralPath $exe -Destination $exeBak -Force
    $orig = [System.IO.File]::ReadAllBytes($exe)
    $half = [Math]::Max([int]($orig.Length / 2), 1024)
    $trunc = New-Object byte[] $half
    [Array]::Copy($orig, $trunc, $half)
    [System.IO.File]::WriteAllBytes($exe, $trunc)
    $r = Run-Native-Demo
    Write-Case -FileName '35_truncation.txt' -Label 'partial_truncation' -Manipulation 'truncate widget_sandbox.exe to 50%' -Command "& '$exe' '--demo'" -ExitCode $r.ExitCode -Output $r.Output -Expected 'BLOCK'
    Restore-State

    # G. TOCTOU simulation (flip artifact between two launches)
    Restore-State
    $r1 = Run-Native-Demo
    Copy-Item -LiteralPath $artFile -Destination $artBak -Force
    Add-Content -LiteralPath $artFile -Value "`n#phase53_4_toctou" -Encoding UTF8
    $r2 = Run-Native-Demo
    Write-Case -FileName '36_toctou.txt' -Label 'toctou_simulation' -Manipulation 'launch clean then mutate control_plane/111 before second launch' -Command "launch_clean; mutate_artifact; launch_again" -ExitCode $r2.ExitCode -Output ("FIRST_EXIT=$($r1.ExitCode)`nSECOND_EXIT=$($r2.ExitCode)`n---SECOND_OUTPUT---`n$($r2.Output)") -Expected 'BLOCK'
    Restore-State

    # H. Clean control
    Restore-State
    $r = Run-Native-Demo
    Write-Case -FileName '37_clean_control.txt' -Label 'clean_control' -Manipulation 'none' -Command "& '$exe' '--demo'" -ExitCode $r.ExitCode -Output $r.Output -Expected 'ALLOW'

} finally {
    Restore-State
}

Write-Host 'PHASE53_4_RUNNER_COMPLETE=1'
