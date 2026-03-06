$ErrorActionPreference = "Stop"

$repo = "C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative"
if ((Get-Location).Path -ne $repo) { "hey stupid Fucker, wrong window again"; exit 1 }

# Point Python at NGKsGraph
$env:PYTHONPATH = "C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph"

# Ensure MSVC env is loaded
cmd /d /s /c "call tools\msvc_x64.cmd && python -m ngksgraph run --project . --profile debug --clear-cache"