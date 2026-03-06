import hashlib

from ngksgraph.capsule import build_capsule_payload_files, compute_hashes, write_deterministic_capsule_zip


def test_capsule_deterministic_zip_bytes_identical(tmp_path):
    graph = {
        "schema_version": 1,
        "repo_root": "C:/repo",
        "generated_at": "fixed",
        "targets": {
            "app": {
                "name": "app",
                "kind": "exe",
                "sources": ["src/main.cpp"],
                "include_dirs": ["include"],
                "defines": ["UNICODE"],
                "cflags": [],
                "libs": ["user32"],
                "lib_dirs": [],
                "ldflags": [],
                "links": [],
            }
        },
        "edges": [],
        "build_order": ["app"],
    }
    compdb = [
        {
            "directory": "C:/repo",
            "file": "C:/repo/src/main.cpp",
            "command": "cl /c src/main.cpp /Fobuild/obj/src/main.obj",
        }
    ]
    config_normalized = {
        "name": "app",
        "out_dir": "build",
        "targets": [{"name": "app", "type": "exe", "links": []}],
    }
    hashes = compute_hashes(config_normalized, graph, compdb)

    payload = build_capsule_payload_files(
        capsule_meta={"schema_version": 1, "project": "app", "target": "app", "msvc_auto_used": False, "source": "live"},
        graph=graph,
        compdb=compdb,
        config_normalized=config_normalized,
        hashes=hashes,
        toolchain={"python_version": "3.x", "platform": "win32", "msvc_auto_used": False, "vswhere_path": None, "vs_install_path": None, "vsdevcmd_path": None},
        snapshot_ref=None,
    )

    zip_a = tmp_path / "a.ngkcapsule.zip"
    zip_b = tmp_path / "b.ngkcapsule.zip"
    write_deterministic_capsule_zip(zip_a, payload)
    write_deterministic_capsule_zip(zip_b, payload)

    hash_a = hashlib.sha256(zip_a.read_bytes()).hexdigest()
    hash_b = hashlib.sha256(zip_b.read_bytes()).hexdigest()
    assert hash_a == hash_b
    assert zip_a.read_bytes() == zip_b.read_bytes()
