from types import SimpleNamespace
from pathlib import Path

from ngksgraph.msvc import build_capture_env_command, find_vs_installation, parse_set_output


def test_parse_set_output_into_dict():
    raw = "\n".join(
        [
            "INCLUDE=C:\\VC\\include",
            "LIB=C:\\VC\\lib",
            "PATH=C:\\VC\\bin;C:\\Windows\\System32",
            "VSCMD_VER=18.3.2",
            "",
        ]
    )

    env = parse_set_output(raw)

    assert env["INCLUDE"] == "C:\\VC\\include"
    assert env["LIB"] == "C:\\VC\\lib"
    assert env["VSCMD_VER"] == "18.3.2"
    assert "PATH" in env


def test_find_vs_installation_strips_wrapping_quotes(monkeypatch):
    monkeypatch.setattr(
        "ngksgraph.msvc.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout='"C:\\Program Files\\Microsoft Visual Studio\\18\\Community"\n'),
    )

    value = find_vs_installation(Path("C:/dummy/vswhere.exe"))
    assert value == "C:\\Program Files\\Microsoft Visual Studio\\18\\Community"


def test_build_capture_env_command_normalizes_quoted_vsdevcmd_path():
    cmd = build_capture_env_command('"C:/Program Files/Microsoft Visual Studio/18/Community/Common7/Tools/VsDevCmd.bat"')
    assert '""C:/Program Files' not in cmd
    assert "VsDevCmd.bat\" -arch=amd64" in cmd
