#Requires -Version 5.0
param(
    [Parameter(Mandatory=$true)]
    [string]$ProofFolder,
    [string]$RuntimeRoot = 'C:\Users\suppo\Desktop\NGKsSystems\NGKsUI Runtime'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $PSNativeCommandUseErrorActionPreference = $false
}

if (-not (Test-Path -LiteralPath $ProofFolder -PathType Container)) {
    throw "ProofFolder not found: $ProofFolder"
}

$exe = Join-Path $RuntimeRoot 'build\debug\bin\widget_sandbox.exe'
$launcher = Join-Path $RuntimeRoot 'tools\run_widget_sandbox.ps1'
$art111 = Join-Path $RuntimeRoot 'control_plane\111_trust_chain_ledger_baseline_enforcement_surface_fingerprint_regression_anchor_trust_chain_baseline.json'
$gateScript = Join-Path $RuntimeRoot 'tools\phase53_2\phase53_2_runtime_gate_enforce.ps1'

foreach ($p in @($exe, $launcher, $art111, $gateScript)) {
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) {
        throw "Required file missing: $p"
    }
}

$exeBak = "$exe.phase53_5_bak"
$art111Bak = "$art111.phase53_5_bak"

function Restore-State {
    if (Test-Path -LiteralPath $exeBak) { Move-Item -LiteralPath $exeBak -Destination $exe -Force }
    if (Test-Path -LiteralPath $art111Bak) { Move-Item -LiteralPath $art111Bak -Destination $art111 -Force }
}

function Safe-NativeRun {
    Push-Location -LiteralPath $RuntimeRoot
    try {
        try {
            $out = (& $exe '--demo' 2>&1 | Out-String)
            return @{ ExitCode = $LASTEXITCODE; Output = $out }
        }
        catch {
            return @{ ExitCode = 9009; Output = ($_.Exception.Message | Out-String) }
        }
    }
    finally {
        Pop-Location
    }
}

function Safe-ScriptRun {
    $cmd = "Set-Location '$RuntimeRoot'; & '$launcher' -Config Debug -PassArgs '--demo'"
    try {
        $out = (& pwsh -NoProfile -ExecutionPolicy Bypass -Command $cmd 2>&1 | Out-String)
        return @{ ExitCode = $LASTEXITCODE; Output = $out }
    }
    catch {
        return @{ ExitCode = 9009; Output = ($_.Exception.Message | Out-String) }
    }
}

function Write-CaseEvidence {
    param(
        [string]$AttackId,
        [string]$ScenarioName,
        [string]$ManipulationSummary,
        [string]$ExpectedResult,
        [string]$CaseFileName,
        [int]$ExitCode,
        [string]$Output,
        [string]$Command
    )

    $actual = if ($ExitCode -eq 0) { 'ALLOW' } else { 'BLOCK' }
    @(
        "attack_id=$AttackId",
        "scenario_name=$ScenarioName",
        "manipulation_summary=$ManipulationSummary",
        "expected_result=$ExpectedResult",
        "actual_result=$actual",
        "exit_code=$ExitCode",
        "evidence_file=$CaseFileName",
        "command=$Command",
        "utc=$([DateTime]::UtcNow.ToString('o'))",
        '---output---',
        $Output
    ) | Set-Content -LiteralPath (Join-Path $ProofFolder $CaseFileName) -Encoding UTF8

    return [pscustomobject]@{
        attack_id = $AttackId
        scenario_name = $ScenarioName
        manipulation_summary = $ManipulationSummary
        expected_result = $ExpectedResult
        actual_result = $actual
        exit_code = $ExitCode
        evidence_file = $CaseFileName
    }
}

$results = New-Object System.Collections.Generic.List[object]

try {
    # A
    Restore-State
    $r = Safe-NativeRun
    $results.Add((Write-CaseEvidence -AttackId 'A' -ScenarioName 'Native clean control' -ManipulationSummary 'None' -ExpectedResult 'ALLOW' -CaseFileName 'A_native_clean.txt' -ExitCode $r.ExitCode -Output $r.Output -Command "& '$exe' '--demo'"))

    # B
    Restore-State
    Copy-Item -LiteralPath $art111 -Destination $art111Bak -Force
    Add-Content -LiteralPath $art111 -Value "`n " -Encoding UTF8
    $r = Safe-NativeRun
    $results.Add((Write-CaseEvidence -AttackId 'B' -ScenarioName 'Native tampered baseline' -ManipulationSummary 'Append whitespace to control_plane/111' -ExpectedResult 'BLOCK' -CaseFileName 'B_native_tampered.txt' -ExitCode $r.ExitCode -Output $r.Output -Command "append whitespace to 111; & '$exe' '--demo'"))
    Restore-State

    # C
    Restore-State
    $r = Safe-ScriptRun
    $results.Add((Write-CaseEvidence -AttackId 'C' -ScenarioName 'Script clean control' -ManipulationSummary 'None' -ExpectedResult 'ALLOW' -CaseFileName 'C_script_clean.txt' -ExitCode $r.ExitCode -Output $r.Output -Command "pwsh -File '$launcher' -Config Debug -PassArgs '--demo'"))

    # D
    Restore-State
    Copy-Item -LiteralPath $art111 -Destination $art111Bak -Force
    Add-Content -LiteralPath $art111 -Value "`n " -Encoding UTF8
    $r = Safe-ScriptRun
    $results.Add((Write-CaseEvidence -AttackId 'D' -ScenarioName 'Script tampered baseline' -ManipulationSummary 'Append whitespace to control_plane/111' -ExpectedResult 'BLOCK' -CaseFileName 'D_script_tampered.txt' -ExitCode $r.ExitCode -Output $r.Output -Command "append whitespace to 111; pwsh -File '$launcher' -Config Debug -PassArgs '--demo'"))
    Restore-State

    # E
    Restore-State
    Copy-Item -LiteralPath $exe -Destination $exeBak -Force
    $bytes = [System.IO.File]::ReadAllBytes($exe)
    $bytes[128] = ($bytes[128] -bxor 0x5A)
    [System.IO.File]::WriteAllBytes($exe, $bytes)
    $r = Safe-NativeRun
    $results.Add((Write-CaseEvidence -AttackId 'E' -ScenarioName 'Binary mutation' -ManipulationSummary 'Flip byte at offset 128 in widget_sandbox.exe' -ExpectedResult 'BLOCK' -CaseFileName 'E_binary_mutation.txt' -ExitCode $r.ExitCode -Output $r.Output -Command "flip exe byte; & '$exe' '--demo'"))
    Restore-State

    # F
    Restore-State
    Copy-Item -LiteralPath $art111 -Destination $art111Bak -Force
    Add-Content -LiteralPath $art111 -Value "`n#phase53_5_hash_mismatch" -Encoding UTF8
    $r = Safe-NativeRun
    $results.Add((Write-CaseEvidence -AttackId 'F' -ScenarioName 'Hash/signature mismatch' -ManipulationSummary 'Modify baseline json after seal' -ExpectedResult 'BLOCK' -CaseFileName 'F_hash_mismatch.txt' -ExitCode $r.ExitCode -Output $r.Output -Command "modify 111; & '$exe' '--demo'"))
    Restore-State

    # G
    Restore-State
    $spoof = 'C:\Windows\Temp'
    $out = (& pwsh -NoProfile -ExecutionPolicy Bypass -Command "Set-Location '$spoof'; & '$exe' '--demo'" 2>&1 | Out-String)
    $code = $LASTEXITCODE
    $results.Add((Write-CaseEvidence -AttackId 'G' -ScenarioName 'Loader/path injection' -ManipulationSummary 'Launch binary from spoofed cwd' -ExpectedResult 'BLOCK' -CaseFileName 'G_loader_injection.txt' -ExitCode $code -Output $out -Command "Set-Location '$spoof'; & '$exe' '--demo'"))

    # H
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
    $results.Add((Write-CaseEvidence -AttackId 'H' -ScenarioName 'Environment injection' -ManipulationSummary 'Set NGKS_RUNTIME_ROOT and NGKS_BYPASS_GUARD before launch' -ExpectedResult 'BLOCK' -CaseFileName 'H_env_injection.txt' -ExitCode $code -Output $out -Command "set NGKS_RUNTIME_ROOT/NGKS_BYPASS_GUARD; & '$exe' '--demo'"))

    # I
    Restore-State
    $out = (& pwsh -NoProfile -ExecutionPolicy Bypass -Command "Set-Location 'C:\'; & '$exe' '--demo'" 2>&1 | Out-String)
    $code = $LASTEXITCODE
    $results.Add((Write-CaseEvidence -AttackId 'I' -ScenarioName 'Wrapper bypass attempt' -ManipulationSummary 'Direct binary invocation from non-runtime cwd' -ExpectedResult 'BLOCK' -CaseFileName 'I_wrapper_bypass.txt' -ExitCode $code -Output $out -Command "Set-Location 'C:\'; & '$exe' '--demo'"))

    # J
    Restore-State
    Copy-Item -LiteralPath $exe -Destination $exeBak -Force
    $orig = [System.IO.File]::ReadAllBytes($exe)
    $half = [Math]::Max([int]($orig.Length / 2), 1024)
    $trunc = New-Object byte[] $half
    [Array]::Copy($orig, $trunc, $half)
    [System.IO.File]::WriteAllBytes($exe, $trunc)
    $r = Safe-NativeRun
    $results.Add((Write-CaseEvidence -AttackId 'J' -ScenarioName 'Partial truncation' -ManipulationSummary 'Truncate widget_sandbox.exe to 50%' -ExpectedResult 'BLOCK' -CaseFileName 'J_truncation.txt' -ExitCode $r.ExitCode -Output $r.Output -Command "truncate exe; & '$exe' '--demo'"))
    Restore-State

    # K
    Restore-State
    $r1 = Safe-NativeRun
    Copy-Item -LiteralPath $art111 -Destination $art111Bak -Force
    Add-Content -LiteralPath $art111 -Value "`n#phase53_5_toctou" -Encoding UTF8
    $r2 = Safe-NativeRun
    $toctouOut = "first_exit=$($r1.ExitCode)`nsecond_exit=$($r2.ExitCode)`n---second_output---`n$($r2.Output)"
    $results.Add((Write-CaseEvidence -AttackId 'K' -ScenarioName 'TOCTOU simulation' -ManipulationSummary 'Launch clean, mutate artifact, launch again' -ExpectedResult 'BLOCK' -CaseFileName 'K_toctou.txt' -ExitCode $r2.ExitCode -Output $toctouOut -Command "launch clean; mutate 111; launch again"))
    Restore-State
}
finally {
    Restore-State
}

$results | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $ProofFolder '03_attack_matrix_results.json') -Encoding UTF8
Write-Host 'PHASE53_5_ATTACK_MATRIX_COMPLETE=1'
