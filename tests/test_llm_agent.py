"""LLM agent tests — all driven by FakeLLMClient (zero API cost).

Tests the ReAct loop, incremental usage capture, defensive handling,
crash recovery, and token budget enforcement.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from harness.llm.client import (
    FakeLLMClient,
    LLMResponse,
    ToolCallRequest,
    Usage,
)

WORKLOAD_DIR = Path(__file__).resolve().parent.parent / "workloads" / "tabular_adult"


# ---------------------------------------------------------------------------
# Fixture: build one case (same pattern as test_run_agent.py)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def built_case(tmp_path_factory):
    """Build one case and return (case_dir, project_root)."""
    data_dir = WORKLOAD_DIR / ".data"
    hidden_dir = WORKLOAD_DIR / ".hidden_data"
    if not data_dir.exists() or not hidden_dir.exists():
        pytest.skip("Data not prepared; run `make data` first.")

    tmp = tmp_path_factory.mktemp("test_llm_agent")

    wl = tmp / "workloads" / "tabular_adult"
    wl.mkdir(parents=True)
    for fname in ["train.py", "config.yaml", "datautil.py"]:
        shutil.copy2(WORKLOAD_DIR / fname, wl / fname)

    ref = wl / "reference"
    ref.mkdir()
    shutil.copy2(WORKLOAD_DIR / "reference" / "stats.yaml", ref / "stats.yaml")

    (wl / ".data").symlink_to(data_dir.resolve())
    (wl / ".hidden_data").symlink_to(hidden_dir.resolve())

    from harness.build_case import build_case

    case_dir = build_case(
        workload_name="tabular_adult",
        operator_id="silent.lr_warmup.v1",
        strength="moderate",
        seed=42,
        project_root=tmp,
    )
    return case_dir, tmp


# ---------------------------------------------------------------------------
# Helper: run an LLMAgent through run_trial and return the record
# ---------------------------------------------------------------------------

def _run_llm_trial(built_case, client, *, max_turns=15, max_total_tokens=200_000):
    """Build an LLMAgent with the given client and run a trial."""
    case_dir, project_root = built_case

    from agents.llm_agent import LLMAgent
    from harness.run_agent import run_trial

    agent = LLMAgent(
        client,
        model_id="fake-model",
        temperature=0.5,
        max_turns=max_turns,
        max_total_tokens=max_total_tokens,
        provider="fake",
    )
    return run_trial(agent, case_dir, project_root)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHappyPath:

    def test_three_turn_investigation_and_submit(self, built_case):
        """Agent investigates (read_config, query_metrics) then submits."""
        responses = [
            LLMResponse(
                text="Let me check the config.",
                tool_calls=[
                    ToolCallRequest(id="tc1", name="read_config", arguments={}),
                ],
                stop_reason="tool_use",
                usage=Usage(input_tokens=100, output_tokens=50),
            ),
            LLMResponse(
                text="Now checking metrics.",
                tool_calls=[
                    ToolCallRequest(
                        id="tc2",
                        name="query_metrics",
                        arguments={"series": "train_loss"},
                    ),
                ],
                stop_reason="tool_use",
                usage=Usage(input_tokens=200, output_tokens=60),
            ),
            LLMResponse(
                text="I found the issue.",
                tool_calls=[
                    ToolCallRequest(
                        id="tc3",
                        name="submit",
                        arguments={
                            "diagnosis": {
                                "detected": True,
                                "operator_class": "lr_misconfiguration",
                            },
                            "evidence_refs": [
                                {
                                    "kind": "config_key",
                                    "artifact_id": "config.yaml",
                                    "detail": {"key_path": "training.lr"},
                                },
                            ],
                            "repair_spec": {
                                "repair_type": "config_patch",
                                "patches": {"training.lr": 0.01},
                            },
                        },
                    ),
                ],
                stop_reason="tool_use",
                usage=Usage(input_tokens=300, output_tokens=80),
            ),
        ]

        client = FakeLLMClient(responses)
        record = _run_llm_trial(built_case, client)

        # Usage accumulated correctly
        assert record["usage"]["llm_calls"] == 3
        assert record["usage"]["input_tokens"] == 600
        assert record["usage"]["output_tokens"] == 190
        assert record["usage"]["total_tokens"] == 790

        # LLM transcript captured
        assert len(record["llm_transcript"]) == 3
        assert record["llm_transcript"][0]["turn"] == 0
        assert record["llm_transcript"][2]["turn"] == 2

        # Submission present
        assert record["submission"] is not None
        assert record["submission"]["diagnosis"]["detected"] is True

        # Model block populated
        assert record["model"]["model_id"] == "fake-model"
        assert record["model"]["provider"] == "fake"
        assert record["model"]["temperature"] == 0.5

        # Record completed
        assert record["status"] == "completed"

    def test_agent_name(self):
        """Agent name includes model_id."""
        from agents.llm_agent import LLMAgent

        client = FakeLLMClient([])
        agent = LLMAgent(client, model_id="test-model")
        assert agent.name == "llm_test-model"


class TestNeverSubmits:

    def test_no_submission_within_max_turns(self, built_case):
        """Agent that never calls submit completes with no submission."""
        responses = [
            LLMResponse(
                text=f"Reading config attempt {i}.",
                tool_calls=[
                    ToolCallRequest(
                        id=f"tc{i}",
                        name="read_config",
                        arguments={},
                    ),
                ],
                stop_reason="tool_use",
                usage=Usage(input_tokens=50, output_tokens=30),
            )
            for i in range(5)
        ]

        client = FakeLLMClient(responses)
        record = _run_llm_trial(built_case, client, max_turns=3)

        assert record["submission"] is None
        assert record["status"] == "completed"
        assert record["usage"]["llm_calls"] == 3
        assert record["usage"]["input_tokens"] == 150
        assert record["usage"]["output_tokens"] == 90

    def test_model_stops_talking(self, built_case):
        """Agent that returns end_turn with no tool calls stops cleanly."""
        responses = [
            LLMResponse(
                text="I don't know what to do.",
                tool_calls=[],
                stop_reason="end_turn",
                usage=Usage(input_tokens=100, output_tokens=40),
            ),
        ]

        client = FakeLLMClient(responses)
        record = _run_llm_trial(built_case, client)

        assert record["submission"] is None
        assert record["status"] == "completed"
        assert record["usage"]["llm_calls"] == 1


class TestMalformedToolCall:

    def test_non_dict_arguments(self, built_case):
        """Tool call with non-dict arguments produces error, loop continues."""
        responses = [
            LLMResponse(
                text="Trying with bad args.",
                tool_calls=[
                    ToolCallRequest(
                        id="tc_bad",
                        name="read_config",
                        arguments="not a dict",  # type: ignore[arg-type]
                    ),
                ],
                stop_reason="tool_use",
                usage=Usage(input_tokens=100, output_tokens=50),
            ),
            LLMResponse(
                text="Now submitting.",
                tool_calls=[
                    ToolCallRequest(
                        id="tc_submit",
                        name="submit",
                        arguments={
                            "diagnosis": {
                                "detected": False,
                                "operator_class": "none",
                            },
                            "evidence_refs": [],
                            "repair_spec": {
                                "repair_type": "config_patch",
                                "patches": {},
                            },
                        },
                    ),
                ],
                stop_reason="tool_use",
                usage=Usage(input_tokens=150, output_tokens=60),
            ),
        ]

        client = FakeLLMClient(responses)
        record = _run_llm_trial(built_case, client)

        # Did not crash
        assert record["status"] == "completed"
        assert record["usage"]["llm_calls"] == 2
        # Submission was recorded
        assert record["submission"] is not None

    def test_empty_response(self, built_case):
        """Model returns no text and no tool calls — loop exits cleanly."""
        responses = [
            LLMResponse(
                text=None,
                tool_calls=[],
                stop_reason="end_turn",
                usage=Usage(input_tokens=80, output_tokens=0),
            ),
        ]

        client = FakeLLMClient(responses)
        record = _run_llm_trial(built_case, client)

        assert record["status"] == "completed"
        assert record["usage"]["llm_calls"] == 1


class TestCrashPreservesUsage:

    def test_crash_on_second_call(self, built_case):
        """LLM client crash after first call preserves turn-1 usage."""
        case_dir, project_root = built_case

        first_response = LLMResponse(
            text="Checking config.",
            tool_calls=[
                ToolCallRequest(id="tc1", name="read_config", arguments={}),
            ],
            stop_reason="tool_use",
            usage=Usage(input_tokens=100, output_tokens=50, cached_tokens=10),
        )

        class CrashingClient:
            def __init__(self):
                self._called = False

            def complete(self, messages, tools_schema, *, max_tokens=4096):
                if not self._called:
                    self._called = True
                    return first_response
                raise RuntimeError("Simulated network error")

        from agents.llm_agent import LLMAgent
        from harness.run_agent import run_trial

        agent = LLMAgent(
            CrashingClient(),
            model_id="crash-model",
            provider="fake",
        )

        with pytest.raises(RuntimeError, match="Simulated network error"):
            run_trial(agent, case_dir, project_root)

        # Read the persisted record to verify usage was captured
        trials_dir = project_root / "results"
        yaml_files = list(trials_dir.rglob("llm_crash-model_*.yaml"))
        assert len(yaml_files) >= 1

        persisted = yaml.safe_load(yaml_files[-1].read_text())
        assert persisted["status"] == "crashed"
        assert persisted["usage"]["llm_calls"] == 1
        assert persisted["usage"]["input_tokens"] == 100
        assert persisted["usage"]["output_tokens"] == 50
        assert persisted["usage"]["cached_tokens"] == 10


class TestTokenBudgetCap:

    def test_stops_before_exceeding_budget(self, built_case):
        """Agent stops when token budget would be exceeded."""
        responses = [
            LLMResponse(
                text="First call.",
                tool_calls=[
                    ToolCallRequest(id="tc1", name="read_config", arguments={}),
                ],
                stop_reason="tool_use",
                usage=Usage(input_tokens=150, output_tokens=100),
            ),
            # This response would push total over 300, but the agent
            # should stop before making this call because
            # 150 + 100 = 250 >= max_total_tokens=250.
            LLMResponse(
                text="Second call (should not happen).",
                tool_calls=[
                    ToolCallRequest(id="tc2", name="read_config", arguments={}),
                ],
                stop_reason="tool_use",
                usage=Usage(input_tokens=200, output_tokens=100),
            ),
        ]

        client = FakeLLMClient(responses)
        record = _run_llm_trial(built_case, client, max_total_tokens=250)

        # Only 1 LLM call should have been made
        assert record["usage"]["llm_calls"] == 1
        assert record["usage"]["input_tokens"] == 150
        assert record["usage"]["output_tokens"] == 100
        assert record["status"] == "completed"


class TestSetRecord:

    def test_set_record_wiring(self, built_case):
        """run_trial calls set_record on agents that have it."""
        case_dir, project_root = built_case

        from agents.llm_agent import LLMAgent
        from harness.run_agent import run_trial

        # Simple agent that submits immediately
        responses = [
            LLMResponse(
                text="Submitting.",
                tool_calls=[
                    ToolCallRequest(
                        id="tc1",
                        name="submit",
                        arguments={
                            "diagnosis": {
                                "detected": False,
                                "operator_class": "none",
                            },
                            "evidence_refs": [],
                            "repair_spec": {
                                "repair_type": "config_patch",
                                "patches": {},
                            },
                        },
                    ),
                ],
                stop_reason="tool_use",
                usage=Usage(input_tokens=50, output_tokens=20),
            ),
        ]

        agent = LLMAgent(FakeLLMClient(responses), model_id="wiring-test")
        record = run_trial(agent, case_dir, project_root)

        # Verify the model block was populated (proves set_record worked)
        assert record["model"]["model_id"] == "wiring-test"
        assert record["usage"]["llm_calls"] == 1
        assert record["usage"]["input_tokens"] == 50

    def test_stub_agents_unaffected(self, built_case):
        """Stub agents without set_record still work fine."""
        case_dir, project_root = built_case

        from agents.stub_agent import StubAgent
        from harness.run_agent import run_trial

        record = run_trial(StubAgent(), case_dir, project_root)

        assert record["status"] == "completed"
        assert record["model"]["model_id"] is None
        assert record["usage"]["llm_calls"] == 0


# ---------------------------------------------------------------------------
# max_tokens truncation → continuation (not silent completion)
# ---------------------------------------------------------------------------

def _submit_response(usage=Usage(input_tokens=120, output_tokens=40)):
    """A well-formed submit response."""
    return LLMResponse(
        text="Submitting.",
        tool_calls=[
            ToolCallRequest(
                id="tc_submit",
                name="submit",
                arguments={
                    "diagnosis": {"detected": False, "operator_class": "none"},
                    "evidence_refs": [],
                    "repair_spec": {"repair_type": "config_patch", "patches": {}},
                },
            ),
        ],
        stop_reason="tool_use",
        usage=usage,
    )


class TestMaxTokensContinuation:

    def test_max_tokens_no_toolcall_continues_then_submits(self, built_case):
        """A truncated response with no tool call must NOT end the trial."""
        responses = [
            LLMResponse(
                text="Long reasoning that got cut off mid-sen",
                tool_calls=[],
                stop_reason="max_tokens",
                usage=Usage(input_tokens=100, output_tokens=50),
            ),
            _submit_response(),
        ]

        client = FakeLLMClient(responses)
        record = _run_llm_trial(built_case, client)

        # The trial continued and submitted rather than ending at turn 0.
        assert record["submission"] is not None
        assert record["usage"]["llm_calls"] == 2
        assert record["usage"]["max_tokens_truncations"] == 1
        assert record["llm_transcript"][0]["truncated"] is True
        assert record["status"] == "completed"

    def test_continuation_cap_enforced(self, built_case):
        """Four consecutive truncations end cleanly after the cap of 3."""
        responses = [
            LLMResponse(
                text=f"Cut off attempt {i}",
                tool_calls=[],
                stop_reason="max_tokens",
                usage=Usage(input_tokens=50, output_tokens=30),
            )
            for i in range(4)
        ]

        client = FakeLLMClient(responses)
        record = _run_llm_trial(built_case, client, max_turns=6)

        assert record["submission"] is None
        assert record["usage"]["llm_calls"] == 4
        assert record["usage"]["max_tokens_truncations"] == 4
        assert record["llm_transcript"][-1].get("continuation_capped") is True
        assert record["status"] == "completed"

    def test_truncation_counter_only_on_max_tokens(self, built_case):
        """Truncation with a tool call counts but injects no continuation."""
        responses = [
            LLMResponse(
                text="Reading config.",
                tool_calls=[
                    ToolCallRequest(id="tc1", name="read_config", arguments={}),
                ],
                stop_reason="tool_use",
                usage=Usage(input_tokens=100, output_tokens=50),
            ),
            LLMResponse(
                text="Checking metrics (truncated but tool call present).",
                tool_calls=[
                    ToolCallRequest(
                        id="tc2", name="query_metrics",
                        arguments={"series": "train_loss"},
                    ),
                ],
                stop_reason="max_tokens",
                usage=Usage(input_tokens=150, output_tokens=60),
            ),
            _submit_response(),
        ]

        client = FakeLLMClient(responses)
        record = _run_llm_trial(built_case, client)

        # All three responses consumed as real calls (no continuation turn
        # was injected), truncation counted once, submission present.
        assert record["usage"]["llm_calls"] == 3
        assert record["usage"]["max_tokens_truncations"] == 1
        assert record["llm_transcript"][1]["truncated"] is True
        assert "truncated" not in record["llm_transcript"][0]
        assert record["submission"] is not None

    def test_default_max_response_tokens_is_8192(self, built_case):
        """The default per-response max_tokens (8192) reaches the client."""
        class CapturingClient:
            def __init__(self, responses):
                self._responses = responses
                self._i = 0
                self.seen_max_tokens: list[int] = []

            def complete(self, messages, tools_schema, *, max_tokens=4096):
                self.seen_max_tokens.append(max_tokens)
                resp = self._responses[self._i]
                self._i += 1
                return resp

        client = CapturingClient([_submit_response()])
        _run_llm_trial(built_case, client)

        assert client.seen_max_tokens == [8192]


class TestOperatorClassNotAnchored:

    def test_schema_operator_class_has_no_fault_name_examples(self):
        """The operator_class description must not list real fault names.

        Example labels in the schema anchor the structured output: a model
        copied 'data_corruption' verbatim for two different faults while its
        reasoning named them correctly.  The description gives neutral
        guidance and documents only 'none'.
        """
        from agents.llm_agent import TOOLS_SCHEMA

        submit = next(t for t in TOOLS_SCHEMA if t["name"] == "submit")
        desc = submit["input_schema"]["properties"]["diagnosis"]["properties"][
            "operator_class"
        ]["description"]

        for banned in (
            "lr_misconfiguration", "data_corruption", "data_leakage",
            "label_corruption", "shape_mismatch",
        ):
            assert banned not in desc, f"schema anchors operator_class with {banned!r}"
        assert "none" in desc  # healthy-case label still documented

    def test_prompt_operator_class_has_no_fault_name_examples(self, built_case):
        """The system prompt must not list real fault names for operator_class."""
        from agents.llm_agent import _build_system_prompt

        case_dir, _ = built_case
        prompt = _build_system_prompt(case_dir)
        for banned in ("lr_misconfiguration", "data_corruption"):
            assert banned not in prompt, f"prompt anchors operator_class with {banned!r}"


class TestSystemPromptAnchor:

    def test_prompt_includes_reference_band(self, built_case):
        """The system prompt states the healthy-run visible-metric band."""
        from agents.llm_agent import _build_system_prompt

        case_dir, _ = built_case
        prompt = _build_system_prompt(case_dir)
        assert "Healthy runs achieve" in prompt
        assert "metric_visible_val_acc" in prompt
        # Range expressed as mean ± 2·std (reference mean 0.856848, std 0.001512).
        assert "healthy range" in prompt
        assert "0.8568" in prompt          # mean
        assert "0.8538" in prompt          # mean - 2*std
        assert "0.8599" in prompt          # mean + 2*std
