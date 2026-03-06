$ErrorActionPreference = 'Stop'
$eco = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
Set-Location $eco
$pf = Get-ChildItem -Directory (Join-Path $eco '_proof') -Filter 'eco_E1_*' | Sort-Object Name -Descending | Select-Object -First 1
if (-not $pf) { throw 'NO_ECO_PF_FOUND' }
$wheelTs = Get-Date -Format 'yyyyMMdd_HHmmss'
$wheelRoot = Join-Path $eco ("wheelhouse\$wheelTs")
New-Item -ItemType Directory -Force -Path $wheelRoot | Out-Null
$wheelPf = Join-Path $pf.FullName 'wheelhouse'
New-Item -ItemType Directory -Force -Path $wheelPf | Out-Null
$repos = @('NGKsDevFabric','NGKsGraph','NGKsBuildCore','NGKsEnvCapsule','NGKsLibrary')
foreach($r in $repos){
  Push-Location (Join-Path $eco $r)
  python -m pip wheel . -w $wheelRoot 2>&1 | Tee-Object -FilePath (Join-Path $wheelPf ("10_wheel_"+$r+".txt"))
  Pop-Location
}
Get-ChildItem $wheelRoot -Filter *.whl | ForEach-Object {
  $h = Get-FileHash $_.FullName -Algorithm SHA256
  "{0}  {1}" -f $h.Hash.ToLowerInvariant(), $_.Name
} | Tee-Object -FilePath (Join-Path $wheelPf '20_sha256.txt')
"wheelhouse=$wheelRoot" | Tee-Object -FilePath (Join-Path $wheelPf '30_summary.txt')
Write-Output "WHEELHOUSE=$wheelRoot"
