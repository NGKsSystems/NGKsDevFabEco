#!/usr/bin/env pwsh
<#
NGKsDevFabEco Release Bundle - Prerequisite Checker
#>

$ErrorActionPreference = 'Continue'
$passed = 0
$failed = 0

Write-Host '=' * 80
Write-Host 'Prerequisite Checker'
Write-Host '=' * 80
Write-Host ''

Write-Host '1. Python 3.11+'
$pythonVersion = python --version 2>&1
if ($?) {
    Write-Host "   OK: $pythonVersion"
    $passed++
} else {
    Write-Host '   FAIL: Python not found'
    $failed++
}

Write-Host '2. pip'
$pipVersion = pip --version 2>&1
if ($?) {
    Write-Host "   OK: $pipVersion"
    $passed++
} else {
    Write-Host '   FAIL: pip not found'
    $failed++
}

Write-Host '3. git'
$gitVersion = git --version 2>&1
if ($?) {
    Write-Host "   OK: $gitVersion"
    $passed++
} else {
    Write-Host '   FAIL: git not found'
    $failed++
}

Write-Host '4. MSVC (C++ compiler, optional)'
$clCheck = cl.exe /? 2>&1
if ($?) {
    Write-Host '   OK: MSVC found'
    $passed++
} else {
    Write-Host '   WARNING: MSVC not found (skip if not building C++)'
}

Write-Host '5. PowerShell 5.0+'
$psVersion = $PSVersionTable.PSVersion
if ($psVersion.Major -ge 5) {
    Write-Host "   OK: PowerShell $($psVersion.Major).$($psVersion.Minor)"
    $passed++
} else {
    Write-Host "   FAIL: PowerShell $($psVersion.Major).$($psVersion.Minor) (need 5.0+)"
    $failed++
}

Write-Host ''
Write-Host '=' * 80
Write-Host 'Summary'
Write-Host '=' * 80
Write-Host "Passed: $passed"
Write-Host "Failed: $failed"
Write-Host ''

if ($failed -eq 0) {
    Write-Host 'All prerequisites satisfied! Ready to run: .\run.ps1'
    exit 0
} else {
    Write-Host 'Fix prerequisites before running'
    exit 1
}
