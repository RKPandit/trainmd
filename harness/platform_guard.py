"""Canonical-platform guard: artifact generation must run on NATIVE amd64.

Sibling to ``train.require_pinned_threads`` in the fail-loud family. Thread
pinning removes *within-platform* nondeterminism; this guard removes the
*cross-platform* hazard: emulated/translated amd64 (Apple Rosetta, qemu) diverges
from native amd64 floating point **per run**, on BOTH metrics (measured 30-seed
native-EPYC vs emulated-Rosetta: visible up to ~2.8σ, hidden up to ~2.1σ,
seed-dependent — LIMITATIONS). Native-vs-native is robust — two EPYC microarchs
(9V45, 7763) were byte-identical — but native-vs-emulated is not. A case or
reference built off native amd64 is therefore NON-CANONICAL — its agent-facing
visible metric may not match the band it is compared against.

So any path that GENERATES ARTIFACTS — a case build or a reference run — refuses
to run unless it is on native amd64. Emulation stays fine for tests and
development (``train.py`` has no such guard on purpose); it must not produce
committed artifacts. This applies from now on, not retroactively: Sweep 1 and the
Stage-2 gate ran on macOS x86_64 and would have been blocked by this guard — that
is correct going forward, and it is why those sweeps carry a platform caveat
(they are internally consistent — macOS metric vs macOS band — so they stand as
run; see LIMITATIONS / DECISIONS).

Detection (in-container-reliable): read ``/proc/cpuinfo`` ``vendor_id``. Native
amd64 — INCLUDING virtualized CI runners (GitHub ubuntu-latest) — reports
``GenuineIntel`` or ``AuthenticAMD``, so this does NOT false-positive on CI (unlike
a ``hypervisor``-flag test, which every cloud VM would trip). Apple Rosetta reports
``VirtualApple``; qemu-tcg reports a ``QEMU Virtual CPU`` model name. Both are
caught. Timing/FP signatures were rejected as unreliable here: the model is tiny
(emulation is only ~17% slower, so wall-time is ambiguous) and a "golden" FP value
is itself platform-dependent (circular).
"""
from __future__ import annotations

import os
import platform
import sys

_NATIVE_VENDORS = ("GenuineIntel", "AuthenticAMD")

# Explicit, loud escape hatch for EPHEMERAL builds (the test suite's fixtures, and
# deliberate local experiments) under emulation. It never makes an emulated build
# canonical: build_cpu is still stamped into the hidden card, so an artifact built
# this way is marked non-native and remains catchable downstream. Committed-artifact
# paths (scripts/build_all_cases.py, docker-reference, sweeps) do NOT set it.
_OVERRIDE_ENV = "TRAINMD_ALLOW_NONCANONICAL_BUILD"


def _parse_cpuinfo(cpuinfo_text: str) -> tuple[str | None, str | None]:
    """Return (vendor_id, model_name) from the first CPU block of /proc/cpuinfo text."""
    vendor = model = None
    for line in cpuinfo_text.splitlines():
        if vendor is None and line.startswith("vendor_id"):
            vendor = line.split(":", 1)[1].strip()
        elif model is None and line.startswith("model name"):
            model = line.split(":", 1)[1].strip()
        if vendor is not None and model is not None:
            break
    return vendor, model


def detect_cpu(cpuinfo_text: str | None = None) -> tuple[str | None, str | None]:
    """(vendor_id, model_name) from /proc/cpuinfo (or *cpuinfo_text* if given)."""
    if cpuinfo_text is None:
        try:
            with open("/proc/cpuinfo") as f:
                cpuinfo_text = f.read()
        except OSError:
            return None, None
    return _parse_cpuinfo(cpuinfo_text)


def cpu_provenance(cpuinfo_text: str | None = None) -> str:
    """A single string recording the detected CPU for the hidden card / manifest.

    e.g. ``"GenuineIntel Intel(R) Xeon(R) ..."`` on native CI, or
    ``"VirtualApple VirtualApple @ 2.50GHz"`` under Rosetta.
    """
    vendor, model = detect_cpu(cpuinfo_text)
    if vendor is None and model is None:
        return f"{platform.system()}/{platform.machine()} (no /proc/cpuinfo)"
    return f"{vendor or '?'} {model or '?'}".strip()


def emulation_reason(
    *,
    system: str | None = None,
    machine: str | None = None,
    cpuinfo_text: str | None = None,
) -> str | None:
    """Return a human-readable reason if this is NOT native amd64, else ``None``.

    Pure and fully injectable so a test can simulate an emulated environment.
    """
    system = system if system is not None else platform.system()
    machine = machine if machine is not None else platform.machine()

    if system == "Darwin":
        return ("running on macOS — a smoke-test platform; canonical artifacts are "
                "generated on native amd64 Linux (the committed reference's platform)")
    if machine not in ("x86_64", "amd64"):
        return f"CPU architecture is {machine!r}, not amd64"

    vendor, model = detect_cpu(cpuinfo_text)
    if vendor is None:
        return "cannot read /proc/cpuinfo vendor_id to confirm native amd64"
    if vendor not in _NATIVE_VENDORS:
        return (f"CPU vendor_id={vendor!r} (model={model!r}) is not native amd64 — "
                f"Apple Rosetta reports 'VirtualApple'")
    if model and "qemu" in model.lower():
        return f"CPU model={model!r} indicates qemu emulation"
    return None


def require_native_amd64(context: str = "generate artifacts") -> None:
    """Refuse (``sys.exit(2)``, fail-loud) unless on native amd64.

    Call at the entry of every artifact generator (``build_case``, ``run_reference``).
    """
    reason = emulation_reason()
    if reason is None:
        return
    cpu = cpu_provenance()
    if os.environ.get(_OVERRIDE_ENV) == "1":
        sys.stderr.write(
            f"\nWARNING: {_OVERRIDE_ENV}=1 — building EPHEMERAL/non-canonical artifacts "
            f"under emulation ({reason}; CPU {cpu}). build_cpu is stamped non-native; "
            f"do NOT commit these artifacts.\n\n"
        )
        return
    sys.stderr.write(
        f"\nFATAL: refusing to {context} on a non-canonical platform.\n"
        f"  Reason: {reason}\n"
        f"  Detected CPU: {cpu}\n"
        "  Why: emulated/translated amd64 diverges from native amd64 floating point\n"
        "  per run, on BOTH metrics (visible up to ~2.8σ, hidden up to ~2.1σ); a case\n"
        "  or reference built here would be NON-CANONICAL — its visible metric may not\n"
        "  match the band it is compared against.\n"
        "  Fix: generate artifacts on native amd64 (CI: the linux/amd64 runners, or a\n"
        "  real Intel/AMD host). Emulation is fine for tests and development — just not\n"
        "  for producing cases or references. See docs/LIMITATIONS.md, docs/DECISIONS.md.\n\n"
    )
    sys.exit(2)
