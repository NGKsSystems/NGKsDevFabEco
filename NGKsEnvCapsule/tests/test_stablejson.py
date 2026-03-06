from ngksenvcapsule.stablejson import dumps_stable


def test_stable_order_and_lf() -> None:
    data = {"b": 1, "a": {"d": 2, "c": 3}}
    out = dumps_stable(data)
    assert out.endswith("\n")
    assert "\r" not in out
    assert out.index('"a"') < out.index('"b"')
