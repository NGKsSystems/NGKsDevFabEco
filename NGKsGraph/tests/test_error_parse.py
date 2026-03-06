from ngksgraph.repair import parse_errors


def test_parse_common_errors():
    log = "\n".join(
        [
            "fatal error C1083: Cannot open include file: 'myhdr.hpp': No such file or directory",
            "LINK : fatal error LNK1104: cannot open file 'foo.lib'",
            "x.obj : error LNK2019: unresolved external symbol MessageBoxA referenced in function main",
        ]
    )
    errors = parse_errors(log)
    assert errors[0]["type"] == "C1083"
    assert errors[0]["header"] == "myhdr.hpp"
    assert errors[1]["type"] == "LNK1104"
    assert errors[1]["lib"] == "foo.lib"
    assert errors[2]["type"] == "LNK2019"
