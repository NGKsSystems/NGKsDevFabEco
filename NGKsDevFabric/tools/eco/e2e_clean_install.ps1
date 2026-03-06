$ErrorActionPreference = 'Stop'
$eco = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
Set-Location $eco
$pf = Get-ChildItem -Directory (Join-Path $eco '_proof') -Filter 'eco_E1_*' | Sort-Object Name -Descending | Select-Object -First 1
if (-not $pf) { throw 'NO_ECO_PF_FOUND' }
$testPf = Join-Path $pf.FullName 'tests'
New-Item -ItemType Directory -Force -Path $testPf | Out-Null
$wheelhouse = Get-ChildItem -Directory (Join-Path $eco 'wheelhouse') | Sort-Object Name -Descending | Select-Object -First 1
if (-not $wheelhouse) { throw 'NO_WHEELHOUSE_FOUND' }
$venv = Join-Path $eco '_e2e_venv'
if (Test-Path $venv) { Remove-Item -Recurse -Force $venv }
python -m venv $venv
$py = Join-Path $venv 'Scripts\python.exe'
& $py -m pip install --upgrade pip 2>&1 | Tee-Object -FilePath (Join-Path $testPf '10_pip_upgrade.txt')
& $py -m pip install --no-index --find-links $wheelhouse.FullName ngksdevfabric ngksgraph ngksbuildcore ngksenvcapsule ngkslibrary 2>&1 | Tee-Object -FilePath (Join-Path $testPf '20_install_wheels.txt')
$emptyProject = Join-Path $eco '_e2e_projects\empty'
$nodeProject = Join-Path $eco '_e2e_projects\node'
New-Item -ItemType Directory -Force -Path $emptyProject | Out-Null
New-Item -ItemType Directory -Force -Path $nodeProject | Out-Null
@'{
  "name": "eco-node-minimal",
  "version": "1.0.0",
  "scripts": {
    "build": "echo build"
  }
}
'@ | Set-Content -Encoding UTF8 (Join-Path $nodeProject 'package.json')
& $py -m ngksdevfabric eco doctor 2>&1 | Tee-Object -FilePath (Join-Path $testPf '30_eco_doctor.txt')
& $py -m ngksdevfabric run --project $emptyProject --mode ecosystem 2>&1 | Tee-Object -FilePath (Join-Path $testPf '40_run_empty.txt')
& $py -m ngksdevfabric run --project $nodeProject --mode ecosystem 2>&1 | Tee-Object -FilePath (Join-Path $testPf '50_run_node.txt')
'completed' | Tee-Object -FilePath (Join-Path $testPf '99_summary.txt')
