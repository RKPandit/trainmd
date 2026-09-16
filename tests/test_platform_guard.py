"""Canonical-platform guard (direction 1): artifact generation refuses under emulation.

A case build / reference run must be on native amd64 — emulated/translated amd64
diverges from native floating point per run (up to ~2.8σ on the visible metric).
The guard detects emulation from /proc/cpuinfo vendor_id (native reports
GenuineIntel/AuthenticAMD, incl. CI VMs; Rosetta reports VirtualApple; qemu reports
a QEMU model), so it does not false-positive on virtualized native CI runners.
"""
from __future__ import annotations

import pytest

from harness import platform_guard as pg

_INTEL = "vendor_id\t: GenuineIntel\nmodel name\t: Intel(R) Xeon(R) Platinum 8370C\n"
_AMD = "vendor_id\t: AuthenticAMD\nmodel name\t: AMD EPYC 7763\n"
_ROSETTA = "vendor_id\t: VirtualApple\nmodel name\t: VirtualApple @ 2.50GHz\n"
_QEMU = "vendor_id\t: GenuineIntel\nmodel name\t: QEMU Virtual CPU version 2.5+\n"


def test_native_amd64_is_allowed():
    for txt in (_INTEL, _AMD):
        assert pg.emulation_reason(system="Linux", machine="x86_64", cpuinfo_text=txt) is None


def test_rosetta_is_refused():
    reason = pg.emulation_reason(system="Linux", machine="x86_64", cpuinfo_text=_ROSETTA)
    assert reason is not None and "VirtualApple" in reason


def test_qemu_is_refused():
    reason = pg.emulation_reason(system="Linux", machine="x86_64", cpuinfo_text=_QEMU)
    assert reason is not None and "qemu" in reason.lower()


def test_macos_is_refused():
    reason = pg.emulation_reason(system="Darwin", machine="x86_64", cpuinfo_text=_INTEL)
    assert reason is not None and "macOS" in reason


def test_non_amd64_is_refused():
    reason = pg.emulation_reason(system="Linux", machine="aarch64", cpuinfo_text=_ROSETTA)
    assert reason is not None and "amd64" in reason


def test_cpu_provenance_records_vendor_and_model():
    assert pg.cpu_provenance(_ROSETTA) == "VirtualApple VirtualApple @ 2.50GHz"


def test_require_native_amd64_exits_with_actionable_message(monkeypatch, capsys):
    """A simulated emulated environment is refused (sys.exit 2) with an actionable message."""
    monkeypatch.delenv("TRAINMD_ALLOW_NONCANONICAL_BUILD", raising=False)  # exercise the refusal
    monkeypatch.setattr(pg, "emulation_reason",
                        lambda **_: "CPU vendor_id='VirtualApple' is not native amd64")
    monkeypatch.setattr(pg, "cpu_provenance", lambda *a, **k: "VirtualApple VirtualApple @ 2.50GHz")
    with pytest.raises(SystemExit) as exc:
        pg.require_native_amd64(context="build a case")
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "refusing to build a case" in err
    assert "native amd64" in err
    assert "VirtualApple" in err          # names the detected CPU
    assert "Emulation is fine for tests" in err  # actionable: says what IS allowed


def test_require_native_amd64_passes_on_native(monkeypatch):
    monkeypatch.setattr(pg, "emulation_reason", lambda **_: None)
    pg.require_native_amd64()  # no raise


def test_override_allows_ephemeral_build_with_loud_warning(monkeypatch, capsys):
    """The explicit override lets EPHEMERAL fixtures build under emulation, loudly."""
    monkeypatch.setenv("TRAINMD_ALLOW_NONCANONICAL_BUILD", "1")
    monkeypatch.setattr(pg, "emulation_reason", lambda **_: "emulated (VirtualApple)")
    pg.require_native_amd64(context="build a case")  # no raise
    assert "non-canonical" in capsys.readouterr().err.lower()
