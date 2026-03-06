from __future__ import annotations

import sys
from pathlib import Path


def setup_fake_qt_tools(tmp_path: Path) -> dict[str, str]:
    tools_dir = tmp_path / "qt_tools"
    tools_dir.mkdir(parents=True, exist_ok=True)

    impl = tools_dir / "qt_tool_impl.py"
    impl.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import hashlib",
                "import sys",
                "from pathlib import Path",
                "",
                "def _usage():",
                "    raise SystemExit(2)",
                "",
                "def main():",
                "    if len(sys.argv) < 3:",
                "        _usage()",
                "    mode = sys.argv[1]",
                "    if sys.argv[2] == '-v':",
                "        print(f'{mode} version 1.0.0')",
                "        return 0",
                "    if len(sys.argv) < 5 or sys.argv[3] != '-o':",
                "        _usage()",
                "    input_path = Path(sys.argv[2])",
                "    output_path = Path(sys.argv[4])",
                "    output_path.parent.mkdir(parents=True, exist_ok=True)",
                "    inp = input_path.read_bytes() if input_path.exists() else b''",
                "    h = hashlib.sha256(inp).hexdigest()",
                "    output_path.write_text(f'// {mode} generated\\n// input={input_path.name}\\n// hash={h}\\n', encoding='utf-8')",
                "    return 0",
                "",
                "if __name__ == '__main__':",
                "    raise SystemExit(main())",
            ]
        ),
        encoding="utf-8",
    )

    paths: dict[str, str] = {}
    for mode in ["moc", "uic", "rcc"]:
        cmd = tools_dir / f"{mode}.cmd"
        cmd.write_text(
            "\n".join(
                [
                    "@echo off",
                    f'"{sys.executable}" "{impl}" {mode} %*',
                ]
            ),
            encoding="utf-8",
        )
        paths[f"{mode}_path"] = str(cmd)

    return paths
