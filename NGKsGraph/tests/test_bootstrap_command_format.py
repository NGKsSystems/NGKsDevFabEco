from ngksgraph.msvc import build_capture_env_command, build_capture_env_invocation


def test_build_capture_env_command_quotes_vsdevcmd_path():
    path = r"C:\Program Files\Microsoft Visual Studio\18\Community\Common7\Tools\VsDevCmd.bat"
    cmd = build_capture_env_command(path)

    assert cmd.startswith('call "C:\\Program Files\\Microsoft Visual Studio\\18\\Community\\Common7\\Tools\\VsDevCmd.bat"')
    assert " -arch=amd64 " in cmd
    assert cmd.endswith(" >nul && set")


def test_build_capture_env_invocation_uses_cmd_d_s_c():
    path = r"C:\Program Files\Microsoft Visual Studio\18\Community\Common7\Tools\VsDevCmd.bat"
    invocation = build_capture_env_invocation(path)

    assert invocation.startswith("cmd.exe /d /s /c ")
    assert 'call "C:\\Program Files\\Microsoft Visual Studio\\18\\Community\\Common7\\Tools\\VsDevCmd.bat"' in invocation
    assert invocation.endswith("&& set\"")
