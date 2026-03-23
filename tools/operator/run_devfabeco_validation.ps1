param(
    [string]$ProjectRoot = "C:\Users\suppo\Desktop\NGKsSystems\NGKs_Content_Curator",
    [string]$PythonExe = "C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_validation_venv\Scripts\python.exe",
    [string]$ProofRoot = "C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\_proof",
    [string]$InjectRegressionCapability = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = "C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco"
$gateScript = Join-Path $repoRoot "tools\regression\qt_consumer_regression_gate.ps1"
if (-not (Test-Path $gateScript)) {
    Write-Host "DECISION=FAIL"
    Write-Host "REASON=missing underlying gate script"
    Write-Host "GATE_SCRIPT=$gateScript"
    exit 1
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$operatorProof = Join-Path $ProofRoot ("devfabeco_operator_run_" + $stamp)
$gateProof = Join-Path $operatorProof "gate_proof"
New-Item -ItemType Directory -Force -Path $operatorProof | Out-Null
New-Item -ItemType Directory -Force -Path $gateProof | Out-Null

$gateStdout = Join-Path $operatorProof "gate_stdout.txt"
$gateStderr = Join-Path $operatorProof "gate_stderr.txt"
$resultJsonName = "operator_gate_results.json"
$resultJsonPath = Join-Path $gateProof $resultJsonName

$certProof = Join-Path $operatorProof "certification_enforcement"
New-Item -ItemType Directory -Force -Path $certProof | Out-Null
$certStatusPath = Join-Path $certProof "certification_status.json"
$certReportPath = Join-Path $certProof "certification_report.txt"
$certArgList = @("-m", "ngksdevfabric", "certification-enforce", "--project", $ProjectRoot, "--pf", $certProof)
$certProc = Start-Process -FilePath "python" -ArgumentList $certArgList -NoNewWindow -Wait -PassThru -RedirectStandardOutput $gateStdout -RedirectStandardError $gateStderr
$certExit = [int]$certProc.ExitCode

if (-not (Test-Path $certStatusPath) -and (Test-Path $gateStdout)) {
    $certOut = Get-Content -Path $gateStdout -Raw
    $statusMatch = [regex]::Match($certOut, "certification_status_json=(.+)")
    if ($statusMatch.Success) {
        $resolvedStatusPath = $statusMatch.Groups[1].Value.Trim()
        if (-not [string]::IsNullOrWhiteSpace($resolvedStatusPath) -and (Test-Path $resolvedStatusPath)) {
            $certStatusPath = $resolvedStatusPath
        }
    }

    $reportMatch = [regex]::Match($certOut, "certification_report_txt=(.+)")
    if ($reportMatch.Success) {
        $resolvedReportPath = $reportMatch.Groups[1].Value.Trim()
        if (-not [string]::IsNullOrWhiteSpace($resolvedReportPath) -and (Test-Path $resolvedReportPath)) {
            $certReportPath = $resolvedReportPath
        }
    }
}

$certificationBlocked = $certExit -ne 0
$certificationFailureSummary = "none"
if ($certificationBlocked) {
    if (Test-Path $certStatusPath) {
        try {
            $certData = Get-Content -Path $certStatusPath -Raw | ConvertFrom-Json
            $blockCodes = @($certData.findings | Where-Object { $_.severity -eq "BLOCK" } | ForEach-Object { [string]$_.code })
            if (($blockCodes | Measure-Object).Count -gt 0) {
                $certificationFailureSummary = ($blockCodes | Sort-Object -Unique) -join "; "
            }
            else {
                $certificationFailureSummary = "certification_enforcement_blocked"
            }
        }
        catch {
            $certificationFailureSummary = "certification_enforcement_parse_error"
        }
    }
    else {
        $certificationFailureSummary = "certification_enforcement_status_missing"
    }
}

$argList = @(
    "-ExecutionPolicy", "Bypass",
    "-File", $gateScript,
    "-ProjectRoot", $ProjectRoot,
    "-PythonExe", $PythonExe,
    "-ProofDir", $gateProof,
    "-ResultJsonName", $resultJsonName
)
if (-not [string]::IsNullOrWhiteSpace($InjectRegressionCapability)) {
    $argList += @("-InjectRegressionCapability", $InjectRegressionCapability)
}

if ($certificationBlocked) {
    $gateExit = 2
    Add-Content -Path $gateStdout -Value "[certification-enforcement]"
    Add-Content -Path $gateStdout -Value "gate=FAIL"
    Add-Content -Path $gateStdout -Value "reason=$certificationFailureSummary"
}
else {
    $proc = Start-Process -FilePath "powershell" -ArgumentList $argList -NoNewWindow -Wait -PassThru -RedirectStandardOutput $gateStdout -RedirectStandardError $gateStderr
    $gateExit = [int]$proc.ExitCode
}

if (Test-Path $gateStderr) {
    $stderrText = Get-Content -Path $gateStderr -Raw
    if (-not [string]::IsNullOrWhiteSpace($stderrText)) {
        Add-Content -Path $gateStdout -Value "`n[stderr]"
        Add-Content -Path $gateStdout -Value $stderrText
    }
}

$decision = "FAIL"
$reason = "fail-closed"
$hasResultJson = Test-Path $resultJsonPath
$gateResult = $null
$workflowName = "qt_consumer_regression_gate"
$failedChecks = @()
$failureSummary = "none"
if ($hasResultJson) {
    try {
        $gateResult = Get-Content -Path $resultJsonPath -Raw | ConvertFrom-Json
        if ($gateResult.gate_name) {
            $workflowName = [string]$gateResult.gate_name
        }
        if ($gateResult.checks) {
            foreach ($prop in $gateResult.checks.PSObject.Properties) {
                if ($prop.Name -in @("forbidden_capability_hits", "injected_regression_capability")) {
                    continue
                }
                if ($prop.Value -is [bool] -and $prop.Value -eq $false) {
                    $failedChecks += $prop.Name
                }
            }
            if (($gateResult.checks.forbidden_capability_hits | Measure-Object).Count -gt 0) {
                $failedChecks += ("forbidden_capability_hits=" + (($gateResult.checks.forbidden_capability_hits | Sort-Object -Unique) -join ","))
            }
        }
        if ($gateResult.pass -eq $true -and $gateExit -eq 0) {
            $decision = "PASS"
            $reason = "all required consumer paths passed"
        }
        elseif ($gateResult.pass -eq $false -and $gateExit -ne 0) {
            $decision = "FAIL"
            $reason = "underlying gate reported failure"
        }
        else {
            $decision = "FAIL"
            $reason = "exit/result mismatch"
        }
    }
    catch {
        $decision = "FAIL"
        $reason = "result json parse error"
    }
}
else {
    $decision = "FAIL"
    if ($certificationBlocked) {
        $reason = "certification_enforcement_blocked"
    }
    else {
        $reason = "missing result json"
    }
}

if (($failedChecks | Measure-Object).Count -gt 0) {
    $failureSummary = ($failedChecks | Sort-Object -Unique) -join "; "
}
elseif ($certificationBlocked) {
    $failureSummary = $certificationFailureSummary
}

$nextStep = if ($decision -eq 'PASS') {
    'no action required'
}
else {
    'inspect operator_status.txt, operator_status.json, and gate_stdout.txt in operator proof'
}

$operatorSummary = Join-Path $operatorProof "operator_summary.txt"
@"
DEVFABECO_OPERATOR_VALIDATION_SUMMARY
command=powershell -ExecutionPolicy Bypass -File tools/operator/run_devfabeco_validation.ps1
workflow=$workflowName
underlying_gate=$gateScript
project_root=$ProjectRoot
injected_regression_capability=$InjectRegressionCapability
operator_decision=$decision
reason=$reason
failure_summary=$failureSummary
underlying_exit_code=$gateExit
underlying_result_json=$resultJsonPath
certification_status_json=$certStatusPath
certification_report_txt=$certReportPath
operator_proof=$operatorProof
gate_proof=$gateProof
gate_stdout=$gateStdout
next_step=$nextStep
"@.Trim() | Set-Content -Path $operatorSummary

$operatorStatusTxt = Join-Path $operatorProof "operator_status.txt"
@"
STATUS: $decision
WORKFLOW: $workflowName
GATE_SCRIPT: $gateScript
PROOF: $operatorProof
GATE_PROOF: $gateProof
RESULT_JSON: $resultJsonPath
CERTIFICATION_STATUS_JSON: $certStatusPath
CERTIFICATION_REPORT_TXT: $certReportPath
FAILURE_SUMMARY: $failureSummary
NEXT_STEP: $nextStep
"@.Trim() | Set-Content -Path $operatorStatusTxt

$operatorStatusJson = Join-Path $operatorProof "operator_status.json"
$statusObj = [ordered]@{
    status = $decision
    workflow = $workflowName
    gate_script = $gateScript
    project_root = $ProjectRoot
    proof = $operatorProof
    gate_proof = $gateProof
    result_json = $resultJsonPath
    certification_status_json = $certStatusPath
    certification_report_txt = $certReportPath
    failure_summary = $failureSummary
    next_step = $nextStep
    underlying_exit_code = $gateExit
    injected_regression_capability = $InjectRegressionCapability
}
($statusObj | ConvertTo-Json -Depth 6) | Set-Content -Path $operatorStatusJson -Encoding UTF8

# ==============================================================================
# GENERATE DASHBOARD.HTML
# ==============================================================================
$dashboardPath = Join-Path $operatorProof "dashboard.html"
$recordedTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# Determine status styling
$statusBgColor = if ($decision -eq "PASS") { "#d4edda" } else { "#f8d7da" }
$statusBorderColor = if ($decision -eq "PASS") { "#28a745" } else { "#dc3545" }
$statusTextColor = if ($decision -eq "PASS") { "#155724" } else { "#721c24" }
$statusIcon = if ($decision -eq "PASS") { "[PASS]" } else { "[FAIL]" }

# Build failure details section (only show if failed)
$failureSection = ""
if ($decision -eq "FAIL") {
    $escapedFailureSummary = [System.Web.HttpUtility]::HtmlEncode($failureSummary)
    $failureSection = @"
  <div class="section" style="background-color: #fff3cd; border-left: 5px solid #ffc107;">
    <h2 style="color: #856404;">What Failed</h2>
    <div style="background-color: #fffbea; padding: 10px; border-radius: 3px; font-family: monospace; font-size: 0.95em;">
      $escapedFailureSummary
    </div>
  </div>
"@
}

# Build artifact list
$proofItems = @(
    "operator_status.txt",
    "operator_status.json",
    "operator_summary.txt",
    "gate_stdout.txt",
    "gate_stderr.txt",
    "gate_proof/operator_gate_results.json"
)
$artifactListHtml = ""
foreach ($item in $proofItems) {
    if ($item -like "*/*") {
        $artifactListHtml += "    <li><code>$item</code></li>`n"
    }
    else {
        $itemPath = Join-Path $operatorProof $item
        if (Test-Path $itemPath) {
            $artifactListHtml += "    <li><code>$item</code> PRESENT</li>`n"
        }
        else {
            $artifactListHtml += "    <li><code>$item</code></li>`n"
        }
    }
}

$htmlContent = @"
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DevFabEco Operator Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background-color: #f5f5f5;
            padding: 20px;
            line-height: 1.6;
            color: #333;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }
        .header {
            background-color: $statusBgColor;
            border-left: 6px solid $statusBorderColor;
            padding: 40px 30px;
            text-align: center;
        }
        .status-symbol {
            font-size: 4em;
            font-weight: bold;
            color: $statusBorderColor;
            margin-bottom: 10px;
        }
        .status-text {
            font-size: 2em;
            font-weight: 600;
            color: $statusTextColor;
            margin-bottom: 5px;
        }
        .status-time {
            font-size: 0.95em;
            color: #666;
            font-weight: 400;
        }
        .content {
            padding: 30px;
        }
        .section {
            margin-bottom: 25px;
            padding: 15px;
            background-color: #fafafa;
            border-radius: 4px;
            border-left: 4px solid #ddd;
        }
        .section h2 {
            font-size: 1.3em;
            margin-bottom: 10px;
            color: #222;
        }
        .workflow-info {
            display: grid;
            gap: 10px;
        }
        .info-row {
            display: flex;
            gap: 15px;
        }
        .info-label {
            font-weight: 600;
            color: #666;
            min-width: 120px;
        }
        .info-value {
            color: #333;
            word-break: break-all;
        }
        .proof-path {
            background-color: #f0f0f0;
            padding: 10px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            user-select: all;
            margin: 5px 0;
            word-break: break-all;
        }
        .next-steps {
            background-color: $statusBgColor;
            border-left: 4px solid $statusBorderColor;
            padding: 15px;
            border-radius: 4px;
        }
        .next-steps p {
            color: $statusTextColor;
            font-weight: 500;
        }
        .artifact-list {
            list-style: none;
            padding-left: 0;
        }
        .artifact-list li {
            padding: 5px 0;
            padding-left: 25px;
            position: relative;
        }
        .artifact-list li:before {
            content: ">";
            position: absolute;
            left: 0;
            color: #999;
        }
        .artifact-list code {
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            background-color: #f0f0f0;
            padding: 2px 6px;
            border-radius: 2px;
        }
        .footer {
            background-color: #f0f0f0;
            padding: 15px 30px;
            font-size: 0.85em;
            color: #666;
            border-top: 1px solid #ddd;
            text-align: center;
        }
        .footer-item {
            margin: 3px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="status-symbol">$statusIcon</div>
            <div class="status-text">$decision</div>
            <div class="status-time">Run completed at $recordedTime</div>
        </div>

        <div class="content">
            <!-- WORKFLOW SECTION -->
            <div class="section">
                <h2>Workflow</h2>
                <div class="workflow-info">
                    <div class="info-row">
                        <div class="info-label">Gate:</div>
                        <div class="info-value">$workflowName</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">Script:</div>
                        <div class="info-value">$gateScript</div>
                    </div>
                </div>
            </div>

            <!-- PROOF SECTION -->
            <div class="section">
                <h2>Proof Evidence</h2>
                <div style="margin-bottom: 12px;">
                    <strong>Operator Proof:</strong>
                    <div class="proof-path">$operatorProof</div>
                </div>
                <div style="margin-bottom: 12px;">
                    <strong>Gate Proof:</strong>
                    <div class="proof-path">$gateProof</div>
                </div>
                <div>
                    <strong>Result JSON:</strong>
                    <div class="proof-path">$resultJsonPath</div>
                </div>
            </div>

            <!-- FAILURE SECTION (conditional) -->
            $failureSection

            <!-- NEXT STEPS SECTION -->
            <div class="section next-steps">
                <h2 style="color: $statusTextColor;">Next Steps</h2>
                <p>$nextStep</p>
            </div>

            <!-- ARTIFACTS SECTION -->
            <div class="section">
                <h2>Proof Artifacts</h2>
                <p style="margin-bottom: 10px; font-size: 0.95em; color: #666;">Available files in proof directory:</p>
                <ul class="artifact-list">
$artifactListHtml
                </ul>
            </div>
        </div>

        <div class="footer">
            <div class="footer-item">Generated by DevFabEco Status Dashboard</div>
            <div class="footer-item">Generated at: $(Get-Date -Format 'o')</div>
            <div class="footer-item">Proof ID: $(Split-Path -Leaf $operatorProof)</div>
        </div>
    </div>
</body>
</html>
"@

$htmlContent | Set-Content -Path $dashboardPath -Encoding UTF8
$dashboardGenerated = Test-Path $dashboardPath
$dashboardSize = if ($dashboardGenerated) { (Get-Item $dashboardPath).Length } else { 0 }

Write-Host "=== DEVFABECO OPERATOR STATUS ==="
Write-Host "STATUS=$decision"
Write-Host "WORKFLOW=$workflowName"
Write-Host "PROOF=$operatorProof"
Write-Host "FAILURE_SUMMARY=$failureSummary"
Write-Host "NEXT_STEP=$nextStep"
Write-Host "=== END STATUS ==="

Write-Host "DECISION=$decision"
Write-Host "REASON=$reason"
Write-Host "OPERATOR_PROOF=$operatorProof"
Write-Host "GATE_PROOF=$gateProof"
Write-Host "RESULT_JSON=$resultJsonPath"
Write-Host "SUMMARY=$operatorSummary"
Write-Host "STATUS_TXT=$operatorStatusTxt"
Write-Host "STATUS_JSON=$operatorStatusJson"
Write-Host "DASHBOARD=$dashboardPath"

if ($decision -eq "PASS") {
    exit 0
}

if ($gateExit -ne 0) {
    exit $gateExit
}
exit 1
