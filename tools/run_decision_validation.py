from __future__ import annotations

from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    devfab_src = repo_root / "NGKsDevFabric" / "src"

    import sys

    sys.path.insert(0, str(devfab_src))
    from ngksdevfabric.ngk_fabric.decision_validation import run_decision_validation  # pyright: ignore[reportMissingImports]

    result = run_decision_validation(
        repo_root=repo_root,
        baseline_path=Path(r"C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab\certification\baseline_v1"),
        current_path=Path(r"C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab"),
    )

    print(f"VALIDATION_DIR={result.get('validation_dir', '')}")
    print(f"VALIDATION_ZIP={result.get('validation_zip', '')}")
    print(f"GATE={result.get('gate', 'FAIL')}")
    return 0 if str(result.get("gate", "FAIL")).upper() == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
