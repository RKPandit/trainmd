"""Verify that workspace-visible artifacts contain no hidden-material tokens.

Spec §7 requires that hidden test data and hidden metrics never enter the
workspace container.  This test runs a short training job (2 epochs) and
scans every workspace-visible artifact for a list of forbidden tokens.

The token list is deliberately conservative — it catches the strings that
would appear if train.py loaded test data, logged test metrics, or if the
visible manifest referenced hidden files.
"""
from __future__ import annotations

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
    if not path.exists():
        pytest.skip(f"{artifact} not found")

    violations = _scan_file(path, FORBIDDEN_TOKENS)
    assert not violations, (
        f"Forbidden tokens found in {artifact}:\n" + "\n".join(violations)
    )


def test_no_forbidden_tokens_in_visible_manifest():
    """The visible data manifest must not reference hidden files or tokens."""
    manifest_path = WORKLOAD_DIR / ".data" / "manifest.json"
    if not manifest_path.exists():
        pytest.skip("Visible manifest not found; run `make data` first.")

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
    if not data_dir.exists():
        pytest.skip("Visible data dir not found; run `make data` first.")

    for fname in ["X_test.npy", "y_test.npy"]:
        assert not (data_dir / fname).exists(), (
            f"{fname} found in visible data dir {data_dir}; "
            "test data must only be in .hidden_data/"
        )


def test_hidden_data_in_correct_location():
    """X_test.npy and y_test.npy must exist in the hidden data directory."""
    hidden_dir = WORKLOAD_DIR / ".hidden_data"
    if not hidden_dir.exists():
        pytest.skip("Hidden data dir not found; run `make data` first.")

    for fname in ["X_test.npy", "y_test.npy"]:
        assert (hidden_dir / fname).exists(), (
            f"{fname} missing from hidden data dir {hidden_dir}"
        )
