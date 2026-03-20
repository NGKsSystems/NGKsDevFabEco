# Repo Selection

Selected repos are bounded to real app candidates with ngksgraph.toml and git presence, excluding ecosystem package/tooling repos.

Included:
- C:\Users\suppo\Desktop\NGKsSystems\NGKsUI Runtime: explicitly required; real C++ app repo with ngksgraph.toml.
- C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab: explicitly required; mixed app repo with ngksgraph.toml.
- C:\Users\suppo\Desktop\NGKsSystems\NGKsFileVisionary: active mixed app repo with ngksgraph.toml and recently validated local venv install.
- C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative: active C++ app repo with ngksgraph.toml and CMake markers.

Excluded from certification set:
- Ecosystem package repos (NGKsGraph, NGKsDevFabric, NGKsBuildCore, NGKsEnvCapsule, NGKsLibrary, NGKsDevFabEco) because this pass targets downstream real usage, not package self-tests.
- Pure Node/Python repos without ngksgraph.toml because they are not current DevFabEco graph/build consumers.
