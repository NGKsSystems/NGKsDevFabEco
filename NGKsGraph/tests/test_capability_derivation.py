"""
Tests for canonical_target_spec._required_capabilities() capability derivation logic.

Focus areas:
- Link-only Qt libraries (Qt6EntryPoint) must NOT generate required capabilities
- Normal Qt modules (Qt6Core, Qt6Gui, etc.) MUST generate required capabilities
- Normalization path: Qt6<Foo> → qt.<foo>; Qt6Foo.lib → qt.foo
- Resolution engine must not block build due to link-only libs
"""
from __future__ import annotations

from ngksgraph.capability.capability_types import CapabilityInventory, CapabilityRecord
from ngksgraph.graph import Target
from ngksgraph.resolver import resolve_target_capabilities
from ngksgraph.targetspec.canonical_target_spec import _LINK_ONLY_QT_LIBS, _required_capabilities
from ngksgraph.targetspec.target_spec_types import CanonicalTargetSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_target(libs: list[str], cxx_std: int = 17) -> Target:
    """Minimal Target sufficient for _required_capabilities()."""
    return Target(
        name="app",
        kind="exe",
        out_dir="build",
        obj_dir="build/obj",
        bin_dir="build/bin",
        lib_dir="build/lib",
        sources=["src/main.cpp"],
        include_dirs=[],
        defines=[],
        cflags=[],
        libs=libs,
        lib_dirs=[],
        ldflags=[],
        cxx_std=cxx_std,
        links=[],
        toolchain={},
    )


def _record(name: str, status: str = "available") -> CapabilityRecord:
    return CapabilityRecord(
        capability_name=name,
        provider="test",
        version="",
        status=status,
        metadata={},
    )


def _spec(required: list[str]) -> CanonicalTargetSpec:
    return CanonicalTargetSpec(
        target_name="app",
        target_type="desktop_app",
        language="c++",
        platform="windows",
        configuration="debug",
        required_capabilities=required,
        optional_capabilities=[],
        policy_flags={"fail_on_missing_required_capability": True},
        source_roots=["src"],
        entrypoints=["src/main.cpp"],
    )


# ---------------------------------------------------------------------------
# Phase 1 hardening: _LINK_ONLY_QT_LIBS set correctness
# ---------------------------------------------------------------------------

def test_link_only_set_contains_entrypoint() -> None:
    """Verify that 'entrypoint' is in _LINK_ONLY_QT_LIBS (the frozenset is correct)."""
    assert "entrypoint" in _LINK_ONLY_QT_LIBS


# ---------------------------------------------------------------------------
# Phase 2 - Test 1: link-only Qt lib excluded from required capabilities
# ---------------------------------------------------------------------------

def test_link_only_qt_lib_excluded() -> None:
    """Qt6EntryPoint must NOT produce a qt.entrypoint required capability.

    Qt6EntryPoint is a Windows linker bootstrap library with no include headers.
    The capability detector checks include directory existence; QtEntrypoint has none.
    Generating qt.entrypoint as a required capability would permanently block builds.
    """
    target = _make_target(libs=["Qt6Core", "Qt6EntryPoint"])
    caps = _required_capabilities(target)
    assert "qt.entrypoint" not in caps, (
        "qt.entrypoint must not appear in required capabilities — "
        "Qt6EntryPoint is a link-only library with no include directory"
    )


# ---------------------------------------------------------------------------
# Phase 2 - Test 2: normal Qt module IS included
# ---------------------------------------------------------------------------

def test_normal_qt_module_included() -> None:
    """Qt6Core must produce qt.core in required capabilities."""
    target = _make_target(libs=["Qt6Core"])
    caps = _required_capabilities(target)
    assert "qt.core" in caps


def test_multiple_normal_qt_modules_included() -> None:
    """All header-bearing Qt modules must appear in required capabilities."""
    target = _make_target(libs=["Qt6Core", "Qt6Gui", "Qt6Widgets", "Qt6Concurrent", "Qt6Sql"])
    caps = _required_capabilities(target)
    assert "qt.core" in caps
    assert "qt.gui" in caps
    assert "qt.widgets" in caps
    assert "qt.concurrent" in caps
    assert "qt.sql" in caps


# ---------------------------------------------------------------------------
# Phase 2 - Test 3: semantic normalization is unchanged
# ---------------------------------------------------------------------------

def test_semantic_normalization_still_correct() -> None:
    """Qt6<Module> → qt.<module> normalization must remain deterministic.

    Verify: prefix strip (Qt6→strip), lowercase, dot-joining — unaffected by the fix.
    """
    target = _make_target(libs=["Qt6Core", "Qt6Gui"])
    caps = _required_capabilities(target)
    # Correct forms
    assert "qt.core" in caps
    assert "qt.gui" in caps
    # Old/wrong forms must not appear
    assert "qt.Qt6Core" not in caps
    assert "qt.Core" not in caps
    assert "Qt6core" not in caps


def test_normalization_dotlib_suffix_stripped() -> None:
    """.lib suffix on a lib name must be stripped before capability derivation."""
    target = _make_target(libs=["Qt6Core.lib"])
    caps = _required_capabilities(target)
    assert "qt.core" in caps
    assert "qt.core.lib" not in caps


def test_normalization_debug_qt_lib_suffix_stripped() -> None:
    """MSVC Qt debug suffix 'd' must normalize to canonical qt.<module> capability names."""
    target = _make_target(libs=["Qt6Cored.lib", "Qt6Guid.lib", "Qt6Widgetsd.lib", "Qt6Sqld.lib"])
    caps = _required_capabilities(target)
    assert "qt.core" in caps
    assert "qt.gui" in caps
    assert "qt.widgets" in caps
    assert "qt.sql" in caps
    assert "qt.cored" not in caps
    assert "qt.guid" not in caps
    assert "qt.widgetsd" not in caps
    assert "qt.sqld" not in caps


def test_normalization_cxx_standard_included() -> None:
    """cxx.standard:<N> required capability must reflect the target's cxx_std."""
    target17 = _make_target(libs=[], cxx_std=17)
    target20 = _make_target(libs=[], cxx_std=20)
    assert "cxx.standard:17" in _required_capabilities(target17)
    assert "cxx.standard:20" in _required_capabilities(target20)


def test_non_qt_libs_do_not_generate_qt_capabilities() -> None:
    """Non-Qt libs (user32.lib, shell32) must not produce qt.* capabilities."""
    target = _make_target(libs=["user32.lib", "shell32.lib", "gdi32"])
    caps = _required_capabilities(target)
    qt_caps = [c for c in caps if c.startswith("qt.")]
    assert qt_caps == [], f"Unexpected qt.* capabilities from non-Qt libs: {qt_caps}"


# ---------------------------------------------------------------------------
# Phase 2 - Test 4: no false missing capability — resolution gate
# ---------------------------------------------------------------------------

def test_no_false_missing_capability_from_qt_entrypoint() -> None:
    """build_allowed must be True when Qt6EntryPoint is the only Qt lib.

    Simulates the NGKsFileVisionary scenario: if qt.entrypoint is incorrectly
    in required capabilities and missing from the inventory, build_allowed=False.
    After the fix, qt.entrypoint must not be in required caps, so the resolver
    must return build_allowed=True even without qt.entrypoint in inventory.
    """
    target = _make_target(libs=["Qt6Core", "Qt6EntryPoint"])
    required = _required_capabilities(target)

    # The resolver uses cxx.standard.active (with version) to satisfy cxx.standard:N.
    # Replace the cxx.standard:<N> entries with cxx.standard.active in the inventory.
    inventory_records = [
        _record(cap) if not cap.startswith("cxx.standard:") else _record("cxx.standard.active")
        for cap in required
    ]
    # cxx.standard.active needs a version to match the required standard
    inventory_records = [
        CapabilityRecord(
            capability_name="cxx.standard.active",
            provider="test",
            version="17",
            status="available",
            metadata={},
        )
        if r.capability_name == "cxx.standard.active"
        else r
        for r in inventory_records
    ]
    inv = CapabilityInventory(records=inventory_records)
    spec = _spec(required)

    report = resolve_target_capabilities(target_spec=spec, inventory=inv)
    assert report.build_allowed is True, (
        f"build_allowed should be True — missing: {[r.capability for r in report.missing]}"
    )
    assert report.missing == [], f"Expected no missing caps, got: {[r.capability for r in report.missing]}"


def test_full_fvisionary_libs_no_missing_capabilities() -> None:
    """Full NGKsFileVisionary libs list must resolve cleanly with build_allowed=True."""
    fvisionary_libs = ["Qt6Core", "Qt6Gui", "Qt6Widgets", "Qt6Concurrent", "Qt6Sql", "Qt6EntryPoint"]
    target = _make_target(libs=fvisionary_libs)
    required = _required_capabilities(target)

    # qt.entrypoint must not be in required
    assert "qt.entrypoint" not in required

    # The resolver uses cxx.standard.active (with version) to satisfy cxx.standard:N.
    inventory_records = [
        CapabilityRecord(
            capability_name="cxx.standard.active",
            provider="test",
            version="17",
            status="available",
            metadata={},
        )
        if cap.startswith("cxx.standard:")
        else _record(cap)
        for cap in required
    ]
    inv = CapabilityInventory(records=inventory_records)
    spec = _spec(required)

    report = resolve_target_capabilities(target_spec=spec, inventory=inv)
    assert report.build_allowed is True, (
        f"build_allowed should be True — missing: {[r.capability for r in report.missing]}"
    )
    assert report.missing == []
