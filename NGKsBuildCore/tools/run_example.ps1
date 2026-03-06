$ErrorActionPreference='Stop'

$root = "C:\Users\suppo\Desktop\NGKsSystems\NGKsBuildCore"
Set-Location $root

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$proofRoot = Join-Path (Resolve-Path .\_proof).Path ("example_gate_" + $ts)
New-Item -ItemType Directory -Force -Path $proofRoot | Out-Null

if (Test-Path .\artifacts\hello) {
	Remove-Item -Recurse -Force .\artifacts\hello
}

$transcript = Join-Path $proofRoot "transcript.txt"
Start-Transcript -Path $transcript -Force | Out-Null

python -m ngksbuildcore doctor --proof $proofRoot 2>&1 | Tee-Object -FilePath (Join-Path $proofRoot "doctor_cmd.log")
python -m ngksbuildcore run --plan examples\hello_plan.json -j 4 --proof $proofRoot 2>&1 | Tee-Object -FilePath (Join-Path $proofRoot "run1_cmd.log")
python -m ngksbuildcore run --plan examples\hello_plan.json -j 4 --proof $proofRoot 2>&1 | Tee-Object -FilePath (Join-Path $proofRoot "run2_cmd.log")

Stop-Transcript | Out-Null
Write-Host "Proof root: $proofRoot"
