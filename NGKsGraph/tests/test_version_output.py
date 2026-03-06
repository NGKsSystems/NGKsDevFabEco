from __future__ import annotations

import re
import pytest

from ngksgraph.cli import main, version_string


def test_version_string_format_and_contracts():
    value = version_string()
    pattern = r"^NGKsGraph\s+\d+\.\d+\.\d+\s+\([a-z0-9]+|unknown\)\s+cache_schema=\d+\s+contracts=6G,6H,7,9$"
    assert re.match(pattern, value), value


def test_version_string_has_no_timestamps_or_paths():
    value = version_string()
    assert not re.search(r"\d{4}-\d{2}-\d{2}", value)
    assert ":\\" not in value
    assert "/" not in value


def test_cli_version_output_stable(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert int(exc.value.code) == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("NGKsGraph ")
    assert "cache_schema=" in out
    assert "contracts=6G,6H,7,9" in out
