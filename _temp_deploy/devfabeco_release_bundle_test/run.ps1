#!/usr/bin/env pwsh
<#
================================================================================
NGKsDevFabEco Release Bundle Orchestrator
Main entry point for running the deterministic build workflow
================================================================================
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

$BundleRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ToolsDir = Join-Path $BundleRoot 'tools'
$DocsDir = Join-Path $BundleRoot 'docs'
$StatusDir = Join-Path $BundleRoot 'status'
$ProjectRoot = (Get-Location).Path

Write-Host "═" * 80
Write-Host "NGKsDevFabEco Release Bundle Orchestrator"
Write-Host "═" * 80
Write-Host ""
Write-Host "Bundle: $BundleRoot"
Write-Host "Project: $ProjectRoot"
Write-Host ""

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1: CHECK PREREQUISITES
# ─────────────────────────────────────────────────────────────────────────────

Write-Host "PHASE 1: Checking prerequisites..."
Write-Host ""

# Check Python
$pythonCheck = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ FAIL: Python not found"
    Write-Host "  See: $BundleRoot\PREREQS.txt"
    exit 1
}
Write-Host "✓ Python: $pythonCheck"

# Check pip
$pipCheck = pip --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ FAIL: pip not found"
    exit 1
}
Write-Host "✓ pip: $pipCheck"

# Check git
$gitCheck = git --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ FAIL: git not found"
    exit 1
}
Write-Host "✓ $gitCheck"

Write-Host ""
Write-Host "✓ Prerequisites satisfied"
Write-Host ""

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2: CREATE STATUS DIRECTORY
# ─────────────────────────────────────────────────────────────────────────────

Write-Host "PHASE 2: Preparing output directories..."
if (-not (Test-Path $StatusDir)) {
    New-Item -ItemType Directory -Path $StatusDir -Force | Out-Null
}
Write-Host "✓ Status directory ready: $StatusDir"
Write-Host ""

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3: INVOKE NGKSDEVFABRIC WORKFLOW
# ─────────────────────────────────────────────────────────────────────────────

Write-Host "PHASE 3: Running DevFabEco certification workflow..."
Write-Host ""

# Invoke the packaged ngksdevfabric CLI
# This runs the full end-to-end deterministic workflow:
#   - Environment locking (NGKsEnvCapsule)
#   - Build planning (NGKsGraph)
#   - Execution (NGKsBuildCore)
#   - Proof generation (NGKsLibrary, NGKsDevFabric)

$cmd = @('python', '-m', 'ngksdevfabric', 'run', '--mode', 'ecosystem')
Write-Host "Command: $($cmd -join ' ')"
Write-Host ""

& $cmd[0] $cmd[1] $cmd[2] $cmd[3] $cmd[4] $cmd[5] $cmd[6]
$exitCode = $LASTEXITCODE

Write-Host ""
Write-Host "Exit code: $exitCode"
Write-Host ""

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 4: GENERATE DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

Write-Host "PHASE 4: Generating HTML dashboard..."
Write-Host ""

# Create a simple HTML dashboard summarizing the result
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$status = if ($exitCode -eq 0) { "PASS" } else { "FAIL" }
$statusClass = if ($exitCode -eq 0) { "pass" } else { "fail" }
$statusSymbol = if ($exitCode -eq 0) { "✓" } else { "✗" }

$proofDir = "See output above for _proof/ location"

$dashboardHtml = @"
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DevFabEco Result</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #f5f5f5;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        .header h1 {
            margin: 0;
            color: #333;
        }
        .result {
            font-size: 48px;
            font-weight: bold;
            margin: 20px 0;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }
        .result.pass {
            background: #d4edda;
            color: #155724;
        }
        .result.fail {
            background: #f8d7da;
            color: #721c24;
        }
        .info {
            background: #f9f9f9;
            padding: 15px;
            border-left: 4px solid #007bff;
            margin: 20px 0;
            border-radius: 4px;
        }
        .section {
            margin: 20px 0;
        }
        .section h2 {
            font-size: 18px;
            color: #333;
            border-bottom: 2px solid #007bff;
            padding-bottom: 10px;
        }
        .section p {
            margin: 10px 0;
            line-height: 1.6;
        }
        .gates {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin: 10px 0;
        }
        .gate {
            padding: 10px;
            background: #f9f9f9;
            border-radius: 4px;
            font-size: 14px;
        }
        .gate.checked {
            background: #d4edda;
            color: #155724;
        }
        .gate.failed {
            background: #f8d7da;
            color: #721c24;
        }
        .footer {
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            font-size: 12px;
            color: #666;
            text-align: center;
        }
        .action-next {
            background: #e7f3ff;
            border-left: 4px solid #2196F3;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }
        .action-next h3 {
            margin-top: 0;
            color: #1565c0;
        }
        code {
            background: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>DevFabEco Certification Result</h1>
        </div>

        <div class="result $statusClass">
            $statusSymbol $status
        </div>

        <div class="info">
            <strong>Generated:</strong> $timestamp<br>
            <strong>Exit Code:</strong> $exitCode<br>
            <strong>Project:</strong> $ProjectRoot
        </div>

        <div class="section">
            <h2>Gates Checked</h2>
            <div class="gates">
                <div class="gate $(if ($exitCode -eq 0) { 'checked' } else { 'failed' })">
                    Environment Gate: $(if ($exitCode -eq 0) { '✓' } else { '✗' })
                </div>
                <div class="gate $(if ($exitCode -eq 0) { 'checked' } else { 'failed' })">
                    Build Gate: $(if ($exitCode -eq 0) { '✓' } else { '✗' })
                </div>
                <div class="gate $(if ($exitCode -eq 0) { 'checked' } else { 'failed' })">
                    Certification Gate: $(if ($exitCode -eq 0) { '✓' } else { '✗' })
                </div>
                <div class="gate $(if ($exitCode -eq 0) { 'checked' } else { 'failed' })">
                    Proof Generation: $(if ($exitCode -eq 0) { '✓' } else { '✗' })
                </div>
            </div>
        </div>

        <div class="action-next">
            <h3>What to do next:</h3>
            $(if ($exitCode -eq 0) {
                "<p><strong>You are cleared to ship!</strong></p>" +
                "<ul>" +
                "<li>Review the proof artifacts in: <code>_proof/</code></li>" +
                "<li>Proceed with your deployment process</li>" +
                "<li>Archive proof if required by your organization</li>" +
                "</ul>"
            } else {
                "<p><strong>The build did not pass certification.</strong></p>" +
                "<ul>" +
                "<li>Review the error details above</li>" +
                "<li>Check <code>FAILURE_GUIDE.txt</code> for troubleshooting</li>" +
                "<li>Fix the underlying issue</li>" +
                "<li>Re-run: <code>.\run.ps1</code></li>" +
                "</ul>"
            })
        </div>

        <div class="section">
            <h2>For More Information</h2>
            <p>
                <strong>Proof Location:</strong><br>
                See console output for <code>_proof/devfabric_run_&lt;timestamp&gt;/</code><br>
                <strong>Documentation:</strong><br>
                <code>README.txt</code> - Overview<br>
                <code>FAILURE_GUIDE.txt</code> - Troubleshooting<br>
                <code>docs/GATE_SEMANTICS.txt</code> - What PASS/FAIL means<br>
                <code>docs/CUSTODY_POLICY.txt</code> - Guarantees
            </p>
        </div>

        <div class="footer">
            <p>DevFabEco Release Bundle v1.2.0 | Deterministic Developer OS</p>
            <p>Generated by orchestration at $timestamp</p>
        </div>
    </div>
</body>
</html>
"@

$dashboardPath = Join-Path $StatusDir 'dashboard.html'
Set-Content -Path $dashboardPath -Value $dashboardHtml -Encoding UTF8
Write-Host "✓ Dashboard created: $dashboardPath"
Write-Host ""

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 5: PRINT SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

Write-Host "═" * 80
Write-Host "SUMMARY"
Write-Host "═" * 80
Write-Host ""
Write-Host "Status: $($statusSymbol) $status"
Write-Host ""
Write-Host "Proof Location: See _proof/ directory (path shown in output above)"
Write-Host "Dashboard: $dashboardPath"
Write-Host ""

if ($exitCode -eq 0) {
    Write-Host "✓ All gates passed. You are cleared to ship."
} else {
    Write-Host "✗ At least one gate failed. See FAILURE_GUIDE.txt for next steps."
}

Write-Host ""
Write-Host "═" * 80
Write-Host ""

exit $exitCode
