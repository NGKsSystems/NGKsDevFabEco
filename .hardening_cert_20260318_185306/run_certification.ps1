param([string]$OutFile = "C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.hardening_cert_20260318_185306\cert_results.txt")

$repos = @(
    @{ name = "NGKsFileVisionary"; path = "C:\Users\suppo\Desktop\NGKsSystems\NGKsFileVisionary"; profile = "debug"; target = "app" },
    @{ name = "NGKsMediaLab";      path = "C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab";      profile = "debug"; target = "NGKsMediaLab" },
    @{ name = "NGKsPlayerNative";  path = "C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative";  profile = "debug"; target = "native" },
    @{ name = "NGKsUI_Runtime";    path = "C:\Users\suppo\Desktop\NGKsSystems\NGKsUI Runtime";    profile = "debug"; target = "widget_sandbox" },
    @{ name = "NGKsGraph_self";    path = "C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\NGKsGraph"; profile = "debug"; target = "NGKsGraph" }
)

$results = @()

foreach ($repo in $repos) {
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "REPO: $($repo.name)"
    Write-Host "============================================================"

    $r = @{
        name        = $repo.name
        path        = $repo.path
        probe       = "N/A"
        probe_exit  = -1
        doctor      = "N/A"
        doctor_exit = -1
        configure   = "N/A"
        cfg_exit    = -1
        build       = "N/A"
        build_exit  = -1
        proof_zip   = ""
        build_allowed = "N/A"
        missing_count  = "N/A"
        blocker     = "CLEAN_PASS"
    }

    if (-not (Test-Path $repo.path)) {
        Write-Host "SKIP: path not found"
        $r.blocker = "REPO_NOT_FOUND"
        $results += $r
        continue
    }

    # --- probe ---
    $out = ngksdevfabric probe $repo.path 2>&1
    $r.probe_exit = $LASTEXITCODE
    $r.probe = if ($r.probe_exit -eq 0) { "PASS" } else { "FAIL" }
    Write-Host "probe: $($r.probe) (exit $($r.probe_exit))"

    # --- doctor ---
    $out = ngksdevfabric doctor $repo.path 2>&1
    $r.doctor_exit = $LASTEXITCODE
    $r.doctor = if ($r.doctor_exit -eq 0) { "PASS" } else { "FAIL" }
    Write-Host "doctor: $($r.doctor) (exit $($r.doctor_exit))"

    # --- configure ---
    $out = ngksgraph configure --project $repo.path --profile $repo.profile 2>&1
    $r.cfg_exit = $LASTEXITCODE
    $r.configure = if ($r.cfg_exit -eq 0) { "PASS" } else { "FAIL" }
    $pf = ($out | Select-String "PROOF_ZIP=").Line
    if ($pf) { $r.proof_zip = $pf.Trim() }
    Write-Host "configure: $($r.configure) (exit $($r.cfg_exit))"

    # --- build ---
    $out = ngksgraph build --project $repo.path --profile $repo.profile --target $repo.target 2>&1
    $r.build_exit = $LASTEXITCODE
    $r.build = if ($r.build_exit -eq 0) { "PASS" } else { "FAIL" }
    $pf2 = ($out | Select-String "PROOF_ZIP=").Line
    if ($pf2) { $r.proof_zip = $pf2.Trim() }
    Write-Host "build: $($r.build) (exit $($r.build_exit))"

    # Read resolution report
    $resDir = "$($repo.path)\build_graph\$($repo.profile)\resolution\14_resolution_report.json"
    if (Test-Path $resDir) {
        $res = Get-Content $resDir | ConvertFrom-Json
        $r.build_allowed = $res.build_allowed
        $r.missing_count = $res.summary.missing_count
        if ($res.build_allowed -eq $false) {
            $r.blocker = "BUILD_FAILURE"
        }
    } else {
        Write-Host "  (no resolution report found at $resDir)"
    }

    $results += $r
}

# Write results
$lines = @("==============================================")
$lines += "  CERTIFICATION RUN: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$lines += "=============================================="
$lines += ""
foreach ($r in $results) {
    $lines += "REPO: $($r.name)"
    $lines += "  probe:     $($r.probe) (exit $($r.probe_exit))"
    $lines += "  doctor:    $($r.doctor) (exit $($r.doctor_exit))"
    $lines += "  configure: $($r.configure) (exit $($r.cfg_exit))"
    $lines += "  build:     $($r.build) (exit $($r.build_exit))"
    $lines += "  build_allowed: $($r.build_allowed)"
    $lines += "  missing_count: $($r.missing_count)"
    $lines += "  blocker:   $($r.blocker)"
    $lines += "  proof_zip: $($r.proof_zip)"
    $lines += ""
}
$lines | Out-File $OutFile -Encoding utf8
Write-Host ""
Write-Host "Results written to: $OutFile"
