# Problem Statement v0.3 — TrainMD

**Working title:** TrainMD: Evidence-Grounded Diagnosis and Verified Recovery of Controlled ML Training Incidents
**Alternative title:** TrainMD: Can Tool-Using LLM Agents Diagnose and Recover ML Training Incidents?
**Author:** R.K. Pandit
**Status:** v0.3 — aligned with the merged literature review (v1.0, 2026-08-28). Supersedes v0.1.
**Change discipline:** the headline claim, RQ set, and v1 scope below were narrowed in response
to DaiFu, RFT-FaultBench, FT-Dojo/PostTrainBench/Agent² RL-Bench, AgentHPO, and the
autoresearch HPO study. Re-run the kill-check against the watch-list groups before submission.

---

## 1. Motivation

Training agents and human practitioners alike are increasingly asked to inspect logs, metrics,
configurations, and source code after an unsuccessful training run. Existing ML-agent benchmarks
(MLE-bench, MLAgentBench, MLGym, FT-Dojo, PostTrainBench) reward final model quality;
deep-learning debugging datasets (AutoTrainer, DeepFD, DeepDiagnosis, DynFault, Deep4ge)
generally stop at fault detection or diagnosis; verified executable recovery is mature only in
microservice/SRE settings (MicroRemed, AIOpsLab, SREGym). TrainMD evaluates the missing
causal loop for supervised ML training.

## 2. Headline claim (narrowed, "to our knowledge")

> **TrainMD is a controlled benchmark for whether tool-using LLM agents can detect, causally
> diagnose, and recover ML training incidents from bounded observability artifacts. A repair is
> successful only if an isolated evaluator applies it and a fresh rerun recovers a hidden,
> task-specific target under a fixed compute budget.**

To our knowledge, no prior work combines, for supervised PyTorch training workloads:
(1) known injected incident causes with released causal/evidence annotations;
(2) an agent-facing, tool-mediated investigation setting;
(3) diagnosis scoring separate from final recovery;
(4) mechanically verified repair on fresh hidden reruns; and
(5) workload-held-out evaluation.

Claims to avoid (per review §11): "real training failures" (use "controlled, empirically
informed incidents"); "the first benchmark for training-failure diagnosis"; "verified
remediation is new"; "LLM agents beat HPO"; "real cloud-submitted failures" when mocked.

## 3. Incident design

**Operational definition of a silent incident (required for every case):**
1. A known-good reference configuration produces a distribution of valid metrics over fixed seeds.
2. Exactly one controlled incident operator is introduced.
3. The faulty run completes but fails a predeclared quality/calibration/efficiency condition
   relative to the reference distribution.
4. A candidate repair is independently rerun on fresh hidden seeds; recovery means the hidden
   metric falls within a prespecified tolerance of the clean-reference distribution, with the
   immutable evaluation untouched.

**Verifiers differ by incident type:** crash → completion + hidden metric within tolerance;
silent quality → hidden validation/test metric vs. reference; leakage → hidden untouched test
set + immutable split checks; efficiency → throughput target AND no quality regression.

## 4. v1 scope (24–48 instances)

- **Workload families (3):** tabular classification, small image classification, text classification.
- **Silent incident operators (4):** bad LR/warmup; preprocessing/normalization mismatch;
  label mapping/corruption in the data pipeline; broken sampler/class-weight logic.
- **Execution operators (2):** resume/checkpoint incompatibility; one locally reproducible
  storage/access-policy failure.
- **Healthy controls:** ≥1 per workload family and observability regime (penalize
  "always declare failure").
- **Variants:** vary dataset, architecture, and symptom strength without changing the causal operator.
- **Framing:** "containerized / cloud-inspired execution," not "real SageMaker failures."

**Deferred to Phase II:** real AWS IAM/quota/capacity errors; CUDA wheel/image mismatch across
heterogeneous hardware; distributed/NCCL/straggler incidents; genuine S3 streaming; data leakage
(until the hidden-evaluation design is proven); dataloader performance incidents (until a
quality-preserving throughput oracle exists).

## 5. Research questions (neutral, controlled)

- **RQ1 — Incident modality.** How do detection, causal diagnosis, evidence retrieval, and
  verified recovery differ among crash, silent-quality, and healthy-control runs?
- **RQ2 — Tool-mediated investigation.** Does bounded interactive access to logs, metrics, run
  diffs, configuration, and code improve verified recovery over a static full-context baseline
  at equal model and budget?
- **RQ3 — Transfer.** How much does performance drop from IID incident variants to
  workload-held-out instances, and which evidence modalities transfer?
- **RQ4 — Diagnosis–repair coupling.** What fraction of correct diagnoses produce a successful
  repair? Use an oracle-diagnosis baseline to separate diagnosis failure from repair-execution
  failure.
- **RQ5 — Diagnosis versus search.** On the predefined subset of configuration/optimization
  incidents, how do random search, Optuna/TPE or ASHA, an LLM agent restricted to the same
  configuration space, and a hybrid compare under equal accelerator-time and trial budgets?
  Report a budget curve (1/3/5/10 retry-equivalents). No directional hypothesis: a plausible
  and interesting outcome is HPO winning on pure hyperparameter incidents while diagnosis wins
  on data-/code-/configuration-cause incidents.

## 6. Scoring (four separate targets per case)

1. **Detection** — was there an incident? (healthy controls included)
2. **Localization/identification** — component and incident class.
3. **Evidence retrieval** — structural annotations only: artifact ID, line/range, metric-series
   window, config key, code location. No LLM judge as primary ground truth; small human audit
   validates evidence sufficiency.
4. **Recovery** — evaluator-confirmed repair meets the recovery oracle within budget.

Headline metric: macro-average across incident classes. Any frequency-weighted score is
secondary, with sampling limitations stated.

## 7. Integrity and anti-leakage requirements

Read-only datasets and baseline artifacts; separate hidden evaluator container; no access to
hidden labels, seeds, answer manifests, or scoring code; constrained patch/submission interface;
fresh execution from an immutable base image; rejection of edits outside approved paths.
Report both an IID instance split and a workload-held-out split (DynFault warning).

## 8. Required baselines

No-op/healthy control; regex/rule baseline for crash signatures; AutoTrainer-style constrained
repair rules for overlapping optimization pathologies; static-context LLM (no tools); tool-using
LLM agent at the same action budget; random search and Optuna/TPE/ASHA on the tuning-compatible
subset only; optional oracle-diagnosis baseline. Identical patch/edit permissions across methods.

## 9. Taxonomy: empirically informed coverage, not frequency

Stage 1: anchor top-level coverage in established empirical studies (Zhang et al. ICSE 2020
Philly; L4; Meta cluster study; TensorFlow bug studies). Stage 2: mine GitHub/Stack Overflow/
re:Post for mechanisms and vocabulary; manually audit a stratified sample with inter-annotator
agreement. Public issue counts are NOT frequency estimates for managed training.

## 10. Case-card schema

case_id · workload_family · incident_layer · incident_operator · healthy_reference_protocol ·
permitted_observability_tools · permitted_edit_paths · agent_budget · public_artifacts ·
hidden_evidence_annotations · hidden_verification_protocol · forbidden_mutations

## 11. Deliverables and open-science rules

Open-source harness + 24–48-case dataset (Apache-2.0), hidden-evaluator design documented,
leaderboard page, arXiv preprint, submission targeted at SE/ML-systems/datasets-and-benchmarks
venues and workshops. Public GitHub repo from week one; this document committed; every case
seeded, Dockerized, one-command reproducible; mining pipeline and audited sample released.

## 12. Descope ladder (updated)

1. Drop the second execution operator (keep checkpoint/resume only).
2. Reduce to 2 workload families (drop image), keeping the workload-held-out split.
3. RQ5 reduced to random search + one Optuna sampler vs. the constrained agent.
4. 24 cases minimum; healthy controls and hidden verification are never cut.

**Scientific core that survives any descope:** silent incidents with operational verifiers,
evidence-grounded scoring, hidden-evaluator verified recovery, and the held-out split.

## 13. Pre-submission checks

- Re-run the kill-check against the PKU/Alibaba (RFT-FaultBench/MicroRemed) and UIUC/Toronto
  (AIOpsLab/SREGym) groups.
- Verify primary PDFs for all 2026 preprints cited (FT-Dojo, PostTrainBench, Agent² RL-Bench,
  DynFault, Deep4ge, SREGym).
- Cite published ACM/IEEE/PMLR versions where available; never ResearchGate/alphaXiv.
