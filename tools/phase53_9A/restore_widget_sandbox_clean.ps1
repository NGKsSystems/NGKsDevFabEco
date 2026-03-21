# ============================================================================
# Phase 53.9A — Widget Sandbox Clean Executable Restore Mechanism
# ============================================================================
# Purpose: Restore a known-clean copy of widget_sandbox.exe for orchestration
# 
# Usage: .\restore_widget_sandbox_clean.ps1 [-VerifyOnly] [-OutputLog <path>]
#
# Requirements:
# - Source exe must exist at runtime location (external repo)
# - Exe hash/size must match documented clean baseline
# - Destination exe is copied and verified before return
# ============================================================================

param(
    [switch]$VerifyOnly,
    [string]$OutputLog = $null
)

$ErrorActionPreference = 'Stop'

# Configuration
$CLEAN_HASH = "0768c5cb66790500486dbba466c0516a7a76823c823c885da3e8af22be017ea8"
$CLEAN_SIZE = 445952
$SOURCE_EXE = "C:\Users\suppo\Desktop\NGKsSystems\NGKsUI Runtime\build\debug\bin\widget_sandbox.exe"
$DEST_EXE = "C:\Users\suppo\Desktop\NGKsSystems\NGKsUI Runtime\build\debug\bin\widget_sandbox.exe"

# Logging
function Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] $Message"
    Write-Host $line
    if ($OutputLog) { Add-Content -Path $OutputLog -Value $line -Encoding UTF8 }
}

# ==========================================
# PHASE 1: VERIFY SOURCE EXISTS
# ==========================================
Log "RESTORE_START"
Log "EcoRoot=$(Get-Location)"

if (-not (Test-Path $SOURCE_EXE)) {
    Log "ERROR: Source exe not found at $SOURCE_EXE"
    exit 1
}
Log "SOURCE_EXE_EXISTS: $SOURCE_EXE"

# ==========================================
# PHASE 2: VERIFY SOURCE STATE
# ==========================================
try {
    $source_stat = Get-Item $SOURCE_EXE
    $source_size = $source_stat.Length
    $source_hash = (Get-FileHash $SOURCE_EXE -Algorithm SHA256).Hash
    
    Log "SOURCE_SIZE=$source_size EXPECTED=$CLEAN_SIZE"
    Log "SOURCE_HASH=$source_hash"
    Log "EXPECTED_HASH=$CLEAN_HASH"
    
    # Check if source is clean
    $is_clean = ($source_size -eq $CLEAN_SIZE) -and ($source_hash -eq $CLEAN_HASH)
    
    if ($is_clean) {
        Log "SOURCE_STATE: CLEAN (matches baseline)"
    } else {
        if ($source_size -ne $CLEAN_SIZE) {
            Log "SIZE_MISMATCH: got $source_size, expected $CLEAN_SIZE"
        }
        if ($source_hash -ne $CLEAN_HASH) {
            Log "HASH_MISMATCH: hash does not match clean baseline"
        }
        Log "SOURCE_STATE: CONTAMINATED or UNKNOWN"
    }
} catch {
    Log "ERROR: Failed to verify source state: $_"
    exit 1
}

# If verify-only mode, exit here
if ($VerifyOnly) {
    Log "VERIFY_ONLY_MODE: Exiting after verification"
    exit (if ($is_clean) { 0 } else { 1 })
}

# ==========================================
# PHASE 3: COPY TO DESTINATION (if clean)
# ==========================================
if (-not $is_clean) {
    Log "RESTORE_BLOCKED: Source exe is not clean, refusing to copy"
    exit 1
}

Log "RESTORE_COPYING: Source is clean, proceeding with copy"
try {
    # Create backup if destination exists
    if (Test-Path $DEST_EXE) {
        $backup = "$DEST_EXE.restore_backup_$(Get-Date -Format yyyyMMdd_HHmmss).bak"
        Log "CREATING_BACKUP: $backup"
        Copy-Item -LiteralPath $DEST_EXE -Destination $backup -Force
        Log "BACKUP_CREATED"
    }
    
    # Copy source to destination
    Log "COPYING: $SOURCE_EXE -> $DEST_EXE"
    Copy-Item -LiteralPath $SOURCE_EXE -Destination $DEST_EXE -Force
    Log "COPY_COMPLETE"
    
    # Verify destination
    $dest_stat = Get-Item $DEST_EXE
    $dest_size = $dest_stat.Length
    $dest_hash = (Get-FileHash $DEST_EXE -Algorithm SHA256).Hash
    
    Log "DEST_SIZE=$dest_size"
    Log "DEST_HASH=$dest_hash"
    
    $dest_clean = ($dest_size -eq $CLEAN_SIZE) -and ($dest_hash -eq $CLEAN_HASH)
    if ($dest_clean) {
        Log "DEST_STATE: CLEAN_VERIFIED"
    } else {
        Log "ERROR: Destination does not match clean baseline after copy"
        exit 1
    }
} catch {
    Log "ERROR: Failed to copy exe: $_"
    exit 1
}

# ==========================================
# PHASE 4: FINAL VALIDATION
# ==========================================
Log "FINAL_VALIDATION: Attempting clean launch"
$launch_log = "$DEST_EXE.launch_test_$(Get-Date -Format yyyyMMdd_HHmmss).txt"

try {
    $proc_out = (& $DEST_EXE --auto-close-ms=1000 2>&1 | Out-String)
    $exit_code = $LASTEXITCODE
    Log "LAUNCH_EXIT_CODE: $exit_code"
    $proc_out | Set-Content -Path $launch_log -Encoding UTF8
    
    if ($exit_code -eq 0) {
        Log "LAUNCH_SUCCESS: Exe launched cleanly (exit=0)"
    } else {
        Log "LAUNCH_WARNING: Exe exited with code $exit_code (not necessarily failure)"
    }
} catch {
    Log "LAUNCH_ERROR: Failed to launch exe: $_"
    exit 1
}

# ==========================================
# RESTORE COMPLETE
# ==========================================
Log "RESTORE_COMPLETE: EXIT=0"
exit 0
