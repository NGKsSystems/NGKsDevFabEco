# Minimal DevFabEco CI gate snippet
# Fails pipeline when certification decision is REGRESSION or INCONCLUSIVE.

$env:PYTHONPATH = 'C:/Users/suppo/Desktop/NGKsSystems/NGKsDevFabEco/NGKsDevFabric/src'
$python = 'C:/Users/suppo/Desktop/NGKsSystems/NGKsDevFabEco/.venv/Scripts/python.exe'
$project = 'C:/Users/suppo/Desktop/NGKsSystems/NGKsMediaLab'
$baseline = 'C:/Users/suppo/Desktop/NGKsSystems/NGKsMediaLab/certification/baseline_v1'

& $python -m ngksdevfabric certify-gate --project $project --baseline $baseline --strict-mode on
if ($LASTEXITCODE -ne 0) {
    throw "Certification gate failed with exit code $LASTEXITCODE"
}
