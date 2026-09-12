"""Verify that workspace-visible artifacts contain no hidden-material tokens.

Spec §7 requires that hidden test data and hidden metrics never enter the
workspace container.  This test runs a short training job (2 epochs) and
scans every workspace-visible artifact for a list of forbidden tokens.

The token list is deliberately conservative — it catches the strings that
would appear if train.py loaded test data, logged test metrics, or if the
visible manifest referenced hidden files.

The second half of this module tests case-level isolation: after building a
case via ``build_case``, the workspace directory and ``card.public.yaml``
must contain no incident metadata (operator, strength, seed, etc.).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# Tokens that must NEVER appear (case-insensitive) in workspace artifacts.
# These cover metric names, file names, and terminology that would indicate
# hidden material leaking into the workspace.
FORBIDDEN_TOKENS = [
    "test_acc",
    "test_loss",
    "X_test",
    "y_test",
    "hidden_test",
    "hidden_data",
    "holdout",
    "control",
    "healthy",
]

WORKLOAD_DIR = Path(__file__).resolve().parent.parent / "workloads" / "tabular_adult"


@pytest.fixture(scope="module")
def trained_output(tmp_path_factory):
    """Run a 2-epoch training job into a temp directory and return its path."""
    output_dir = tmp_path_factory.mktemp("workspace_isolation")

    # Write a minimal config (2 epochs for speed)
    config = {
        "workload": {"family": "tabular", "name": "tabular_adult"},
        "model": {"type": "mlp", "hidden_dims": [64, 32], "dropout": 0.0},
        "training": {
            "epochs": 2,
            "batch_size": 256,
            "lr": 0.01,
            "optimizer": "adam",
            "weight_decay": 0.0001,
        },
        "metrics": {"visible": "metric_visible_val_acc"},
    }
    config_path = output_dir / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    data_dir = WORKLOAD_DIR / ".data"
    if not data_dir.exists():
        pytest.skip(f"Visible data not found at {data_dir}; run `make data` first.")

    result = subprocess.run(
        [
            sys.executable,
            str(WORKLOAD_DIR / "train.py"),
            "--config", str(config_path),
            "--data-dir", str(data_dir),
            "--output-dir", str(output_dir),
            "--seed", "0",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Training failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    return output_dir


# --------------------------------------------------------------------------
# Workspace artifact scan
# --------------------------------------------------------------------------

_WORKSPACE_ARTIFACTS = [
    "metrics.jsonl",
    "logs/stdout.log",
    "config.resolved.yaml",
    "exitcode",
]


def _scan_file(path: Path, tokens: list[str]) -> list[str]:
    """Return list of (token, line_number, line) for any forbidden matches."""
    violations = []
    text = path.read_text()
    for i, line in enumerate(text.splitlines(), 1):
        lower = line.lower()
        for token in tokens:
            if token.lower() in lower:
                violations.append(f"  {path.name}:{i} contains '{token}': {line.strip()}")
    return violations


@pytest.mark.parametrize("artifact", _WORKSPACE_ARTIFACTS)
def test_no_forbidden_tokens_in_artifact(trained_output, artifact):
    """Each workspace artifact must not contain any forbidden token."""
    path = trained_output / artifact
    assert path.exists(), (
        f"Required workspace artifact {artifact} not produced (spec §2 output contract)"
    )

    violations = _scan_file(path, FORBIDDEN_TOKENS)
    assert not violations, (
        f"Forbidden tokens found in {artifact}:\n" + "\n".join(violations)
    )


def test_no_forbidden_tokens_in_visible_manifest():
    """The visible data manifest must not reference hidden files or tokens."""
    manifest_path = WORKLOAD_DIR / ".data" / "manifest.json"
    assert manifest_path.exists(), (
        "Visible manifest not found at .data/manifest.json; run `make data` first."
    )

    violations = _scan_file(manifest_path, FORBIDDEN_TOKENS)
    assert not violations, (
        "Forbidden tokens found in .data/manifest.json:\n" + "\n".join(violations)
    )


# --------------------------------------------------------------------------
# File-existence checks
# --------------------------------------------------------------------------

def test_no_test_data_in_visible_dir():
    """X_test.npy and y_test.npy must NOT exist in the visible data directory."""
    data_dir = WORKLOAD_DIR / ".data"
    assert data_dir.exists(), (
        "Visible data dir not found at .data/; run `make data` first."
    )

    for fname in ["X_test.npy", "y_test.npy"]:
        assert not (data_dir / fname).exists(), (
            f"{fname} found in visible data dir {data_dir}; "
            "test data must only be in .hidden_data/"
        )


def test_hidden_data_in_correct_location():
    """X_test.npy and y_test.npy must exist in the hidden data directory."""
    hidden_dir = WORKLOAD_DIR / ".hidden_data"
    assert hidden_dir.exists(), (
        "Hidden data dir not found at .hidden_data/; run `make data` first."
    )

    for fname in ["X_test.npy", "y_test.npy"]:
        assert (hidden_dir / fname).exists(), (
            f"{fname} missing from hidden data dir {hidden_dir}"
        )


# ==========================================================================
# Case-level isolation tests (spec §5 + §7)
# ==========================================================================

# Extended forbidden tokens for case workspace scans.
# Includes the base set plus terms that would leak operator/case metadata.
_CASE_FORBIDDEN_TOKENS = FORBIDDEN_TOKENS + [
    "operator_id",
    "card.hidden",
    "evidence.yaml",
    "verify.yaml",
    "tolerance_lower",
    "recovery_oracle",
]

# Tokens that must NOT appear in card.public.yaml — these would reveal
# incident information to the agent.
_PUBLIC_CARD_FORBIDDEN_TOKENS = [
    "lr_warmup",
    "silent",
    "dynamics",
    "operator",
    "mutation",
    "manifest",
    "incident",
    "strength",
    "severe",
    "moderate",
    "mild",
    "control",
    "healthy",
]


@pytest.fixture(scope="module")
def built_case(tmp_path_factory):
    """Build one case into a temp directory and return the case dir path.

    Sets up a minimal project-root structure in the temp dir:
      tmp/workloads/tabular_adult/{train.py, config.yaml, reference/, .data, .hidden_data}
    then calls ``build_case(project_root=tmp)``.
    """
    import shutil

    data_dir = WORKLOAD_DIR / ".data"
    hidden_dir = WORKLOAD_DIR / ".hidden_data"
    if not data_dir.exists() or not hidden_dir.exists():
        pytest.skip("Data not prepared; run `make data` first.")

    tmp = tmp_path_factory.mktemp("case_isolation")

    # Mirror the workload directory structure
    wl = tmp / "workloads" / "tabular_adult"
    wl.mkdir(parents=True)
    for fname in ["train.py", "config.yaml", "datautil.py"]:
        shutil.copy2(WORKLOAD_DIR / fname, wl / fname)

    # Copy reference stats (needed for tolerance check)
    ref = wl / "reference"
    ref.mkdir()
    shutil.copy2(WORKLOAD_DIR / "reference" / "stats.yaml", ref / "stats.yaml")

    # Symlink data directories (avoid copying large numpy arrays)
    (wl / ".data").symlink_to(data_dir.resolve())
    (wl / ".hidden_data").symlink_to(hidden_dir.resolve())

    # Import here so test collection doesn't fail if operators/ is absent
    from harness.build_case import build_case

    case_dir = build_case(
        workload_name="tabular_adult",
        operator_id="silent.lr_warmup.v1",
        strength="moderate",
        seed=42,
        project_root=tmp,
    )
    return case_dir


# --------------------------------------------------------------------------
# Structure checks
# --------------------------------------------------------------------------

def test_case_directory_structure(built_case):
    """All expected files and dirs must exist in the case."""
    case_dir = built_case
    expected_files = [
        "card.public.yaml",
        "hidden/card.hidden.yaml",
        "hidden/evidence.yaml",
        "hidden/verify.yaml",
        "workspace/train.py",
        "workspace/config.yaml",
        "workspace/run_output/metrics.jsonl",
        "workspace/run_output/logs/stdout.log",
        "workspace/run_output/config.resolved.yaml",
        "workspace/run_output/exitcode",
        "workspace/run_output/checkpoints/ckpt_final.pt",
    ]
    for fpath in expected_files:
        assert (case_dir / fpath).exists(), (
            f"Expected case artifact {fpath} missing"
        )


def test_workspace_no_hidden_files(built_case):
    """No hidden-side filenames should appear in the workspace tree."""
    workspace = built_case / "workspace"
    hidden_filenames = {"card.hidden.yaml", "evidence.yaml", "verify.yaml"}

    for p in workspace.rglob("*"):
        assert p.name not in hidden_filenames, (
            f"Hidden filename {p.name} found in workspace at {p}"
        )


# --------------------------------------------------------------------------
# Token scans on workspace artifacts
# --------------------------------------------------------------------------

def test_workspace_artifacts_no_forbidden_tokens(built_case):
    """Scan all text files in workspace for extended forbidden tokens."""
    workspace = built_case / "workspace"
    violations = []

    for p in workspace.rglob("*"):
        if not p.is_file():
            continue
        # Skip binary files (checkpoints, numpy arrays)
        if p.suffix in (".pt", ".npy", ".npz"):
            continue
        try:
            text = p.read_text()
        except UnicodeDecodeError:
            continue

        for i, line in enumerate(text.splitlines(), 1):
            lower = line.lower()
            for token in _CASE_FORBIDDEN_TOKENS:
                if token.lower() in lower:
                    violations.append(
                        f"  {p.relative_to(workspace)}:{i} "
                        f"contains '{token}': {line.strip()}"
                    )

    assert not violations, (
        "Forbidden tokens in workspace:\n" + "\n".join(violations)
    )


# --------------------------------------------------------------------------
# Public card isolation
# --------------------------------------------------------------------------

def test_public_card_no_incident_info(built_case):
    """card.public.yaml must not contain any incident-revealing tokens."""
    card_path = built_case / "card.public.yaml"
    violations = _scan_file(card_path, _PUBLIC_CARD_FORBIDDEN_TOKENS)
    assert not violations, (
        "Incident info leaked into card.public.yaml:\n"
        + "\n".join(violations)
    )


def test_public_card_has_opaque_id(built_case):
    """case_id must match the opaque pattern case_NNNN."""
    card_path = built_case / "card.public.yaml"
    with open(card_path) as f:
        card = yaml.safe_load(f)

    case_id = card["case_id"]
    assert re.fullmatch(r"case_\d{4}", case_id), (
        f"case_id {case_id!r} does not match opaque pattern case_NNNN"
    )

    # Must NOT contain generation parameters
    card_text = card_path.read_text().lower()
    for term in ["seed", "lr_warmup", "operator"]:
        assert term not in card_text, (
            f"Generation parameter '{term}' found in card.public.yaml"
        )


# --------------------------------------------------------------------------
# Hidden card positive checks
# --------------------------------------------------------------------------

def test_hidden_card_contains_operator_info(built_case):
    """Hidden card must contain correct operator metadata."""
    hidden_card_path = built_case / "hidden" / "card.hidden.yaml"
    with open(hidden_card_path) as f:
        card = yaml.safe_load(f)

    assert card["operator_id"] == "silent.lr_warmup.v1"
    assert card["layer"] == "dynamics"
    assert card["strength"] == "moderate"
    assert card["seed"] == 42
    assert len(card["mutations"]) >= 1
    assert card["mutations"][0]["key_path"] == "training.lr"


def test_verify_yaml_has_oracle_params(built_case):
    """verify.yaml must contain tolerance params and faulty value."""
    verify_path = built_case / "hidden" / "verify.yaml"
    with open(verify_path) as f:
        verify = yaml.safe_load(f)

    assert "tolerance_lower" in verify
    assert "faulty_value" in verify
    assert "hidden_eval_seeds" in verify
    assert "admissible_repairs" in verify

    # faulty_value must be below tolerance (the whole point)
    assert verify["faulty_value"] < verify["tolerance_lower"], (
        f"faulty_value={verify['faulty_value']} >= "
        f"tolerance_lower={verify['tolerance_lower']}"
    )


# --------------------------------------------------------------------------
# Clean-config convention: absent-when-clean for every operator knob
# --------------------------------------------------------------------------

# Config keys that only an operator should ever introduce.  The clean
# workload config must contain none of them — a knob's presence in a case
# is then itself a signal that an operator set it.
_OPERATOR_KNOB_KEYS = {
    "label_noise_fraction",
    "include_aux_feature",
    "aux_feature_strength",
}


def test_clean_config_has_no_operator_knobs():
    """workloads/tabular_adult/config.yaml carries no operator knob keys."""
    with open(WORKLOAD_DIR / "config.yaml") as f:
        config = yaml.safe_load(f)

    data_section = config.get("data") or {}
    present = _OPERATOR_KNOB_KEYS & set(data_section)
    assert not present, (
        f"Clean config leaks operator knob(s) {sorted(present)}; "
        f"knobs must be absent-when-clean"
    )


# --------------------------------------------------------------------------
# datautil workspace copy fidelity
# --------------------------------------------------------------------------

def test_datautil_copied_byte_identical(built_case):
    """The workspace datautil.py must be byte-identical to the workload source.

    train.py imports it as a sibling; a drifted copy would silently change the
    deterministic selection the evaluator relies on.
    """
    ws_copy = built_case / "workspace" / "datautil.py"
    source = WORKLOAD_DIR / "datautil.py"
    assert ws_copy.is_file(), "workspace/datautil.py missing"
    assert ws_copy.read_bytes() == source.read_bytes(), (
        "workspace datautil.py differs from workload source"
    )


def test_datautil_has_no_forbidden_tokens(built_case):
    """datautil.py is agent-visible; it must trip no isolation tokens (W1)."""
    text = (built_case / "workspace" / "datautil.py").read_text()
    violations = _scan_file(built_case / "workspace" / "datautil.py", _CASE_FORBIDDEN_TOKENS)
    assert not violations, "datautil.py contains forbidden tokens:\n" + "\n".join(violations)
