param(
  [Parameter(Mandatory=$true)][string]$ProofDir
)

$ErrorActionPreference='Stop'

$root = "C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph"
Set-Location $root
if ((Get-Location).Path -ne $root) { "hey stupid Fucker, wrong window again"; exit 1 }

$sample = Join-Path $root "artifacts\phaseA_sample"
if (Test-Path $sample) {
  Remove-Item -Recurse -Force $sample
}
New-Item -ItemType Directory -Force -Path (Join-Path $sample "src") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $sample "include") | Out-Null

 $tomlText = @"
name = "hello"
out_dir = "build"
target_type = "exe"
cxx_std = 20

src_glob = ["src/**/*.cpp"]
include_dirs = ["include"]
defines = ["HELLO=1"]
cflags = []
ldflags = []
libs = []
lib_dirs = []
warnings = "default"

[profiles.debug]
cflags = ["/Od", "/Zi"]
defines = ["DEBUG"]
ldflags = []
"@
[System.IO.File]::WriteAllText((Join-Path $sample "ngksgraph.toml"), $tomlText, (New-Object System.Text.UTF8Encoding($false)))

@"
#include <iostream>
int main(){ std::cout << "hello" << std::endl; return 0; }
"@ | Set-Content -Path (Join-Path $sample "src\main.cpp") -Encoding utf8

$planOut = Join-Path $root "artifacts\plan.json"
$cmdLog = Join-Path $ProofDir "buildplan_command.log"
$cmdLine = 'python -m ngksgraph buildplan --project "' + $sample + '" --profile debug --out "' + $planOut + '" > "' + $cmdLog + '" 2>&1'
cmd /c $cmdLine | Out-Null
Get-Content -Path $cmdLog -Encoding utf8
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

$jsonOk = $false
$nodeCount = 0
try {
  $plan = Get-Content -Path $planOut -Raw -Encoding utf8 | ConvertFrom-Json
  if ($null -ne $plan.nodes) {
    $nodeCount = @($plan.nodes).Count
  }
  $jsonOk = $true
} catch {
  $jsonOk = $false
}

Copy-Item -Force $planOut (Join-Path $ProofDir "plan.json")

$status = "FAIL"
if ($jsonOk -and $nodeCount -gt 0) {
  $status = "PASS"
}

$gateText = @(
  "status=$status",
  "json_ok=$jsonOk",
  "nodes=$nodeCount",
  "plan=$planOut"
) -join "`n"

Set-Content -Path (Join-Path $ProofDir "graph_buildplan_gate.txt") -Value $gateText -Encoding utf8

if ($status -ne "PASS") {
  exit 1
}

Write-Host "GRAPH_PHASE_A_GATE=PASS nodes=$nodeCount"