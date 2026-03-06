from ngksgraph.msvc import parse_set_output


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
