# TrainMD — Literature and Design Review (v1.0, merged final)

**Reviewed:** 2026-08-28  
**Purpose:** independent assessment of the TrainMD problem statement and its literature positioning.  
**Scope of this review:** primary sources were checked across ACM/IEEE proceedings and arXiv through 2026-08-28. This is a rigorous targeted review, not a PRISMA-style systematic review; re-check all preprints and venues immediately before submission.

## Bottom-line verdict

This is a good and viable independent-research direction. The strongest version is **not** “the first benchmark for ML training failures” and not simply “LLM agents versus HPO.” Those claims are now too broad.

The credible contribution is:

> **TrainMD is a controlled benchmark for whether tool-using LLM agents can detect, causally diagnose, and recover ML training incidents from bounded observability artifacts. A repair is successful only if an isolated evaluator applies it and a fresh rerun recovers a hidden, task-specific target under a fixed compute budget.**

No work found in this review combines all of the following for **supervised PyTorch training workloads**:

1. known injected incident causes plus a released causal/evidence annotation;
2. an agent-facing, tool-mediated investigation setting;
3. diagnosis scoring separate from final recovery;
4. a mechanically verified repair on a fresh rerun and hidden evaluation; and
5. workload-held-out evaluation that tests transfer beyond a memorized fault fingerprint.

That is a real gap. It is also narrower, more defensible, and more publishable than a “first end-to-end training-repair benchmark” claim.

The original idea should proceed, but with three major changes:

- Make the first paper a **small, high-integrity benchmark**, not a 120–200-case cloud/MLOps universe.
- Treat public issue mining as a **coverage and realism study**, not an estimate of incident frequency.
- Turn the HPO comparison into a neutral, well-controlled question: **when does diagnosis add value beyond black-box optimization?** Do not hypothesize that an agent must beat HPO.

## 1. What the original review gets right

The existing review correctly identified several central neighbors:

- **RFT-FaultBench / RFT-FM** is the closest recent training-dynamics benchmark with detection, diagnosis, intervention, and post-intervention revalidation. Its scope is reinforcement fine-tuning, however, and its remediation metric is reduction in anomaly severity rather than recovery to a task-performance oracle.
- **L4** is important evidence that real large-scale training failures are worth studying and that training logs support useful diagnosis. It is not an agent-repair benchmark.
- **AutoTrainer**, **DeepDiagnosis**, **DeepFD**, **DynFault**, and **Deep4ge** establish a mature deep-learning debugging and fault-diagnosis literature. TrainMD cannot imply that diagnosis or silent training faults are unexplored.
- **MicroRemed**, **AIOpsLab**, and **SREGym** are useful methodological analogues for executable remediation and a problem-specific recovery oracle.
- The Microsoft/Philly empirical study is an appropriate source for the claim that training-job failures include substantial platform/environment components, not only model-code bugs.

The existing review is especially right that silent/degraded behavior, rather than obvious exceptions alone, is where the scientific value lies.

## 2. Important corrections and omissions

### 2.1 The “first” claim needs to be substantially narrower

Several prior systems already perform some form of training repair and re-execution:

- **AutoTrainer** detects and repairs a limited set of DNN training problems by changing architecture or hyperparameters and continuing training. It is not an LLM-agent benchmark, but it is a direct predecessor for verified training repair.
- **DaiFu** presents in-situ crash recovery for DL systems and evaluates on a seven-scenario crash benchmark. It is not an LLM-agent diagnosis benchmark and does not address silent degradation, but it makes a broad “first crash recovery benchmark” statement unsafe.
- **RFT-FM** reruns after a diagnosis-conditioned intervention. Its success criterion is a lower anomaly-severity score, not full recovery of a hidden task metric, but it is still a real closed-loop training-failure-management predecessor.

Therefore avoid:

> “The first benchmark for ML training-failure diagnosis and verified remediation.”

Use:

> “To our knowledge, the first benchmark that jointly evaluates tool-using LLM agents on evidence-grounded diagnosis and mechanically verified recovery of controlled incidents in supervised PyTorch training, with held-out-workload evaluation.”

Even this should remain “to our knowledge” and be rechecked before submission.

### 2.2 The review misses the strongest current agent-training benchmarks

These works do not inject labeled training incidents, but they are directly relevant because agents iteratively modify and rerun training workflows:

- **FT-Dojo**: interactive, end-to-end autonomous LLM fine-tuning across 13 tasks and five domains.
- **PostTrainBench**: agents autonomously post-train a base LLM under a bounded compute budget.
- **Agent² RL-Bench**: agents design, implement, debug, and execute RL post-training pipelines under a fixed budget.
- **MLE-bench**, **MLAgentBench**, and **MLGym**: broad ML-engineering or ML-research-agent benchmarks where debugging and iterative experimentation may occur but faults are not causal benchmark targets.

These works weaken a generic “agents cannot be evaluated on iterative training” claim. They do **not** remove TrainMD’s niche because they optimize end outcomes rather than evaluate whether an agent correctly diagnoses a known incident from logs, metrics, configurations, and code.

### 2.3 RQ5 is no longer an unclaimed comparison

The existing review calls “evidence-grounded agentic repair versus black-box HPO under an equal retrain budget” essentially unclaimed. That is too strong.

- **AgentHPO** already proposes an LLM agent that iteratively optimizes hyperparameters from trial history.
- **Can LLMs Beat Classical Hyperparameter Optimization Algorithms? A Study on autoresearch** directly compares LLM-driven optimization with classical HPO under the same 24-hour compute budget. In its fixed-space setting, classical CMA-ES and TPE outperform pure LLM methods; a hybrid is strongest.
- **Repairing DNN Architecture: Are We There Yet?** compares repair-oriented approaches with search baselines and finds that random search can be competitive.

TrainMD can still make a distinct contribution if RQ5 is specifically:

> Given an already observed, instrumented training incident, does causal diagnosis improve recovery efficiency over black-box search on the subset of incidents that are actually repairable by tuning?

This is different from unconstrained HPO, but it must be tested rather than assumed. A credible result may be that HPO wins on pure hyperparameter incidents while an agent wins on data-, code-, or configuration-cause incidents. That interaction is scientifically more interesting than a blanket “agent wins” result.

### 2.4 RFT-FaultBench is not a general LLM-agent benchmark

RFT-FM calls its remediation module “Agentic Training Intervention,” but the paper does not evaluate a general-purpose LLM agent performing open-ended log/code/tool investigation. Its intervention is part of the authors’ structured failure-management framework. Distinguish it carefully:

- It is highly relevant as a **closed-loop RFT failure-management** benchmark.
- It is not a direct test of a general tool-using coding agent.
- Its remediation metric is reduction in anomaly severity after revalidation, not recovery to a hidden downstream-performance threshold.

This makes it a strong methodological predecessor, not a reason to abandon TrainMD.

### 2.5 The current source quality needs cleanup

The existing document mixes primary sources with ResearchGate, alphaXiv, and secondary fetches. For a paper:

- Cite the published ACM/IEEE/PMLR version when available.
- Otherwise cite the arXiv version and date/version explicitly.
- Do not rely on ResearchGate or alphaXiv for claims about methods, datasets, or results.
- Separate peer-reviewed work from 2025–26 preprints in the related-work prose.

## 3. Closest-work comparison

| Work | Controlled training incidents | General LLM agent evaluated | Causal diagnosis | Repair applied and rerun | What it means for TrainMD |
|---|---:|---:|---:|---:|---|
| AutoTrainer (ICSE 2021) | Yes, limited | No | Yes | Yes | Nearest non-LLM training-repair predecessor; cite directly. |
| DaiFu (2025 preprint) | Crash cases | No | Limited/implementation-oriented | Yes | Prevents a broad crash-recovery novelty claim. |
| RFT-FaultBench / RFT-FM (2026 preprint) | Yes, RFT | No general-purpose LLM agent | Yes | Yes, severity-based | Strongest recent training-dynamics neighbor; scope and oracle differ. |
| DynFault (2026 preprint) | Yes | No | Yes | No | Shows why workload-held-out evaluation is necessary. |
| Deep4ge (2026 preprint) | Yes | No | Yes | No | Strong reusable silent-fault dataset, but TensorFlow/Keras and no repair. |
| L4 (FSE 2025) | Production reports/logs | No | Yes | No | Validates importance of training-log diagnosis at scale. |
| DeepDiagnosis / DeepFD (ICSE 2022) | Study-specific faults | No | Yes | No automatic verified fix | Essential non-agent diagnosis/fix-recommendation baselines. |
| FT-Dojo / PostTrainBench / Agent² RL-Bench (2026) | No causal fault suite | Yes | Not the target | Iterative outcome verification | Nearest agent-training environments; TrainMD must explain its causal diagnostic focus. |
| AgentHPO and autoresearch HPO study | No incident suite | Yes | Not the target | Iterative trials | RQ5 must be scoped to diagnosis-informed recovery, not generic HPO. |
| MicroRemed / AIOpsLab / SREGym | Non-ML systems | Yes in some settings | Yes | Yes | Good templates for isolation, action constraints, and recovery oracles. |

## 4. Revised problem framing

### Recommended title

**TrainMD: Evidence-Grounded Diagnosis and Verified Recovery of Controlled ML Training Incidents**

Alternative if “MD” must imply a training doctor:

**TrainMD: Can Tool-Using LLM Agents Diagnose and Recover ML Training Incidents?**

Avoid “Real ML Training Failures” unless every case is a naturally occurring, independently reproduced failure. Fault-injected cases can be realistic and valuable, but they are still controlled incidents.

### Recommended abstract-level claim

> Training agents are increasingly asked to inspect logs, metrics, configurations, and source code after an unsuccessful training run. Existing ML-agent benchmarks reward final model quality, while deep-learning debugging datasets generally stop at fault detection or diagnosis. TrainMD evaluates the missing causal loop: an agent receives bounded observability artifacts from a controlled faulty run, identifies the incident and supporting evidence, proposes a repair, and is scored only after an isolated evaluator applies the repair and verifies recovery on fresh runs and hidden evaluation data. The benchmark separates crash, silent-quality, and efficiency incidents, includes healthy controls, and reports both in-distribution and workload-held-out performance.

### A sharper scope boundary

The original proposal combines three different research problems:

| Track | Example | Recommended treatment |
|---|---|---|
| Training dynamics | wrong LR/warmup, wrong normalization, label mapping, sampler bug | **Core v1.** These are the most coherent silent incidents. |
| Training-system execution | checkpoint incompatibility, storage policy, volume exhaustion | Small separate crash track, reproduced locally. |
| Real cloud operations | IAM, S3, quota/capacity, managed-service image mismatch, distributed NCCL | **Phase II.** Include only if the environment truly reproduces the semantics. |

If MinIO, Docker volume quotas, or mocked credentials are used, call the setting “containerized/cloud-inspired,” not “real cloud-submitted SageMaker failures.” Actual cloud quota/capacity errors are neither stable nor generally reproducible.

## 5. The key scientific design choices

### 5.1 Define “silent incident” operationally

“Training completed but the model is bad” is not enough. A benchmark instance needs a measurable counterfactual:

1. A known-good reference configuration produces a distribution of valid metrics over fixed seeds.
2. One controlled incident is introduced.
3. The faulty run completes but fails a predeclared quality, calibration, or efficiency condition relative to the reference.
4. The candidate repair is independently rerun on fresh hidden seeds.

For a quality case, a safe verifier is:

> completion succeeds, immutable evaluation is untouched, and the repaired model’s hidden metric is within a prespecified tolerance of the clean-reference distribution.

Use a reference distribution or multiple seeds where possible. A single arbitrary target invites flukes, early stopping, and metric gaming.

Different outcomes need different verifiers:

| Incident type | Do not score only | Suggested verification |
|---|---|---|
| Crash | process exits 0 | completion plus hidden evaluation metric within tolerance of clean reference |
| Silent quality regression | training loss improves | hidden validation/test metric, calibration if relevant, and clean-reference comparison |
| Data leakage | visible validation score | performance on a hidden, untouched test set and immutable split checks |
| Efficiency regression | runtime alone | throughput/resource target **and** no significant quality regression |

### 5.2 Separate diagnosis from recovery

An outcome-only score cannot tell whether an agent found the cause or got lucky. Each case should have a machine-readable incident card with four different targets:

1. **Detection:** was there an incident? Include healthy controls so “always declare failure” is penalized.
2. **Localization/identification:** which component and incident class caused it?
3. **Evidence retrieval:** which log spans, metric windows, configuration keys, or code regions support the diagnosis?
4. **Recovery:** does the evaluator-confirmed repair meet the recovery oracle within the compute budget?

Do not use an LLM judge as the primary ground-truth scorer. Evidence annotations should be structural: artifact ID, line/range, metric-series time interval, config key, and code location. A small human audit can validate that the designated evidence is genuinely sufficient rather than merely correlated.

### 5.3 Prevent evaluator and benchmark leakage

The agent must not be able to “repair” the evaluator. Use:

- read-only datasets and baseline artifacts;
- a separate hidden evaluator container;
- no access to hidden labels, hidden seeds, answer manifests, or scoring code;
- a constrained patch/submission interface;
- fresh execution from an immutable base image;
- explicit rejection of edits outside approved training/configuration paths.

Report two splits at minimum:

- **IID instance split:** new seeds/variants of seen incident operators.
- **Workload-held-out split:** the same incident family on unseen training programs.

DynFault’s program-held-out results are a direct warning: runtime traces can encode program identity rather than transferable fault information. A benchmark without this split will be vulnerable to the same criticism.

### 5.4 Do not use public issue counts as real-world frequency

GitHub, Stack Overflow, re:Post, and framework issue trackers are useful sources of examples, vocabulary, and candidate incident mechanisms. They are not a representative denominator for managed-training incidents:

- issue sources have different reporting incentives;
- framework repository issues overrepresent library defects;
- public questions overrepresent local developer errors;
- duplicate reports and unreproducible reports are common.

Use a two-stage process:

1. Start with established empirical taxonomies and production studies to define top-level coverage.
2. Mine public reports to discover case mechanisms and language, then manually audit a stratified sample with inter-annotator agreement.

Call the result an **empirically informed coverage taxonomy**, not a frequency estimate. Make macro-average performance the headline metric; put any frequency-weighted score in a secondary analysis with its sampling limitations stated.

## 6. A feasible v1 benchmark

### Recommended v1

Build a 24–48-instance benchmark before expanding.

- **Three workload families:** tabular classification, small image classification, and text classification.
- **Four silent incident operators:** bad LR/warmup, preprocessing/normalization mismatch, label mapping/corruption introduced in the data pipeline, and broken sampler/class-weight logic.
- **Two execution operators:** resume/checkpoint incompatibility and one locally reproducible storage/access-policy failure.
- **Healthy controls:** at least one per workload family and observability regime.
- **Variants:** change dataset, architecture, and symptom strength without changing the causal operator.

This gives a coherent first paper. It supports silent-failure analysis, agent investigation, repair, and workload-held-out testing without pretending to cover every MLOps incident.

### Defer from v1

- Real AWS IAM/quota/capacity failures.
- CUDA wheel/image mismatch across heterogeneous hardware.
- Distributed training, NCCL, and straggler incidents.
- Genuine S3 streaming behavior.
- Data leakage unless the hidden-evaluation design is already robust.
- Dataloader performance incidents unless a quality-preserving throughput oracle is ready.

These are good extensions, but each has a different observability model and verification problem. Adding them early risks making the benchmark shallow.

### Why the original 120–200 estimate is risky

A case count is not the real unit of cost. Each serious case needs:

- a clean reference;
- a fault injection and deterministic reproduction;
- a validation run;
- agent trials and retries;
- fresh-seed verification;
- at least one baseline;
- documentation and a human audit.

At 100+ cases, this becomes hundreds or thousands of training runs even before multiple agent systems and HPO baselines. A smaller benchmark with strong isolation, artifacts, splits, and documentation is much more likely to be trusted and adopted.

## 7. Revised research questions

Replace directional or weakly controlled questions with the following.

**RQ1 — Incident modality.** How do detection, causal diagnosis, evidence retrieval, and verified recovery differ among crash, silent-quality, and healthy-control runs?

**RQ2 — Tool-mediated investigation.** Does bounded interactive access to logs, metrics, run diffs, configuration, and code improve verified recovery over a static full-context baseline at equal model and budget?

**RQ3 — Transfer.** How much performance drops from IID incident variants to workload-held-out instances, and which evidence modalities transfer?

**RQ4 — Diagnosis–repair coupling.** What fraction of correct diagnoses produce a successful repair? Use an oracle diagnosis-to-repair baseline, if practical, to separate diagnosis failure from repair-execution failure.

**RQ5 — Diagnosis versus search.** On the predefined subset of configuration/optimization incidents, how do random search, Optuna/TPE or ASHA, an LLM agent restricted to the same configuration space, and a hybrid method compare under equal accelerator-time and trial budgets?

RQ5 should report a budget curve, for example 1, 3, 5, and 10 retry-equivalents. Three retries can be a realistic point, but it is too small to be the only experiment for a serious HPO conclusion.

## 8. Required baselines

At minimum, include:

1. **No-op/healthy control** for false-positive detection and evaluator sanity.
2. **Regex/rule baseline** for obvious crash signatures.
3. **AutoTrainer-style constrained repair rules** for the overlapping optimization pathologies.
4. **Static-context LLM** that cannot use investigation tools.
5. **Tool-using LLM agent** with the same action budget.
6. **Random search and Optuna/TPE/ASHA** only on the tuning-compatible subset.
7. **Optional oracle diagnosis baseline** to measure whether the bottleneck is identifying the cause or carrying out a known correct repair.

Keep patch/edit permissions identical when comparing methods. HPO cannot fairly compete on a label-corruption or credential incident that lies outside its allowed search space.

## 9. Recommended case-card schema

Every released case should contain public metadata plus hidden evaluator data.

    case_id
    workload_family
    incident_layer
    incident_operator
    healthy_reference_protocol
    permitted_observability_tools
    permitted_edit_paths
    agent_budget
    public_artifacts
    hidden_evidence_annotations
    hidden_verification_protocol
    forbidden_mutations

The public artifacts should make a real investigation possible, not merely disclose the answer. The hidden verifier should record completion, quality recovery, compute spent, and integrity checks.

## 10. A concise related-work section you can reuse

Prior work on deep-learning debugging has established that training failures can be detected, localized, and sometimes repaired. AutoTrainer automatically detects and repairs a limited set of DNN training problems, while DeepDiagnosis and DeepFD diagnose faults and recommend or localize actionable fixes. Mutation-testing and dataset efforts such as DeepCrime, DynFault, and Deep4ge provide controlled fault operators or labeled training trajectories, but they do not evaluate general-purpose LLM agents that investigate artifacts and produce mechanically verified repairs. The empirical study of 4,960 Microsoft deep-learning-job failures and the L4 study of production large-scale LLM-training failures further show that training incidents span model, data, environment, and platform layers.

Recent work has also begun to evaluate autonomous agents that iteratively modify training workflows. MLE-bench, MLAgentBench, MLGym, FT-Dojo, PostTrainBench, and Agent² RL-Bench assess ML engineering, fine-tuning, or post-training under bounded compute budgets. These benchmarks primarily score final model quality or improvement, however, rather than whether an agent identifies a known causal incident and grounds its diagnosis in specific evidence. RFT-FaultBench is the closest training-dynamics benchmark: it studies fine-grained reinforcement-fine-tuning anomalies and evaluates a diagnosis-conditioned intervention, but it targets RFT rather than general supervised training and defines mitigation by anomaly-severity reduction rather than recovery to a task-specific hidden-performance oracle.

Executable recovery has been studied more deeply in microservice and SRE benchmarks such as AIOpsLab, MicroRemed, and SREGym, which motivate isolated execution and problem-specific recovery checks. TrainMD adapts these evaluation principles to controlled supervised-ML training incidents. Its focus is not open-ended model optimization; it is whether a tool-using LLM agent can detect an incident, identify the causal fault and supporting evidence, produce an admissible repair, and recover a clean reference behavior on fresh hidden evaluation runs.

## 11. Recommended claims and claims to avoid

| Use | Avoid |
|---|---|
| “controlled, empirically informed incidents” | “real training failures” |
| “to our knowledge, no prior benchmark jointly evaluates…” | “the first benchmark for training failure diagnosis” |
| “mechanically verified recovery on fresh runs” | “verified remediation is new” |
| “diagnosis-informed recovery versus black-box search” | “LLM agents beat HPO” |
| “containerized/cloud-inspired execution track” | “real cloud-submitted failures” when services are mocked |
| “workload-held-out generalization” | only random instance splits |

## 12. Publication realism

A careful 24–48-instance benchmark with a strong artifact, primary baselines, workload-held-out split, and a clear empirical result is plausible as an independent project. It is better aligned with software-engineering, ML-systems, and datasets/benchmarks venues than with a broad claim of a new general agent architecture.

A 120–200-case benchmark plus issue-mining study, cloud track, multiple agents, HPO study, and distributed incidents is likely a multi-person or multi-phase effort. It should be the roadmap, not the minimum viable paper.

## 13. Merged from the first-pass review (retained material)

### 13.1 Broader adjacent-benchmark landscape (context for related work and the talk)

The v0.2 closest-work table is the right one for the paper. The wider landscape below is retained for the related-work paragraph on evaluation methodology and for interview defense ("what else is out there?"):

| Benchmark | Domain | Scoring style | Verified fix loop |
|---|---|---|---|
| RCAEval (WWW 2025) | Microservice RCA, 735 cases, 11 fault types | Root-cause service + indicator | No |
| OpenRCA | Microservice RCA, 335 cases | Final-answer only | No |
| AIOps2025 + RCA100 / AgenticOpsEval (2026) | Microservices, 500+ expert-labeled cases | Localization / Identification / Reason (evidence-grounded) | No |
| ITBench (ICML 2025) | Kubernetes SRE/CISO/FinOps, ~94-102 scenarios | RCA + resolution | Partial |
| AIOpsLab (MLSys 2025) | Kubernetes, 48 (~86 current) problems | Detect/Localize/RCA/Mitigate | Yes (live-health oracle; self-healing caveat) |
| MicroRemed (2025) | Microservices, 421 fault-recovery pairs | Remediation accuracy/latency/tokens | Yes (playbook exec + status verification) |
| SREGym (2026) | Live K8s, 90 problems | Diagnosis + mitigation | Yes (recovery-to-healthy oracle) |
| Who&When (ICML 2025) | Multi-agent failure logs | Agent + step attribution | No |
| AgentDebug / AgentErrorBench, TraceElephant, AgentDebugX | LLM-agent trajectories | Attribution, closed-loop recover-rerun (trajectories) | Partial |
| MLE-Dojo (NeurIPS 2025 D&B) | 200+ Kaggle challenges | Interactive outcome verification | No injected faults |
| SWE-bench family | GitHub code bugs, 2,294 tasks | Test pass/fail | Yes (apply patch, run tests) |

### 13.2 Empirical motivation anchors (motivation only — NOT frequency weights, per Section 5.4)

- Zhang et al. (ICSE 2020, Microsoft Philly, 4,960 failures): 48.0% of deep-learning job failures occur in interaction with the platform rather than in code logic, largely from local-vs-platform environment discrepancies; DL-specific failures (13.5%) driven by inappropriate model parameters/structures and framework API misunderstanding. Canonical citation for the local-vs-cloud framing.
- Chen et al. (arXiv 2504.03887): GPU clusters at Microsoft and Meta see roughly 9% of DL training tasks fail due to OOM. Useful single-number motivation for the OOM class.
- Meta (arXiv 2410.21680): 11 months across ~24k A100 GPUs; job-level failure taxonomy and NCCL-timeout differential diagnosis — source of realistic "red-herring" signals for case design.
- Gao et al. (Microsoft, ICSE 2024): average GPU utilization <=50% across 400 studied jobs — motivation for the (deferred) efficiency-incident track.

### 13.3 Watch list before submission

Two author clusters are actively extending training-failure management; re-run the kill-check against them immediately before arXiv submission:

- Peking University / Alibaba group (MicroRemed, RFT-FaultBench): if RFT-FaultBench is extended from RFT to supervised training, pivot differentiation to the silent data-fault tier + the diagnosis-vs-search analysis, which it lacks.
- UIUC / Toronto group (AIOpsLab, SREGym): watch for any move from SRE workloads toward ML training workloads.

### 13.4 Verification and provenance note

- v0.2's two most consequential new citations were independently verified on 2026-08-28: DaiFu (arXiv 2507.01628; in-situ crash recovery with a 7-scenario crash benchmark — accurately characterized) and Ferreira et al., "Can LLMs Beat Classical HPO? A Study on autoresearch" (arXiv 2603.24647; 9 HPO methods, fixed 24h GPU budget, 3 seeds; CMA-ES/TPE beat LLM agents in a fixed space; code-editing agents narrow but do not close the gap; hybrid strongest — accurately characterized).
- Remaining 2026 preprints (FT-Dojo, PostTrainBench, Agent(2) RL-Bench, DynFault, Deep4ge, SREGym) still need primary-PDF verification before the related-work section is finalized.
- Decisions adopted from v0.2 over the first-pass review: narrowed headline claim; RQ5 reframed as neutral diagnosis-vs-search with budget curves; issue mining demoted from frequency estimate to coverage study; v1 scoped to 24-48 instances with cloud/distributed tracks deferred; hidden-evaluator isolation and workload-held-out split added as requirements.

## Primary sources

### Deep-learning failures, diagnosis, repair, and taxonomy

- Ru Zhang et al., [An Empirical Study on Program Failures of Deep Learning Jobs](https://dl.acm.org/doi/10.1145/3377811.3380362), ICSE 2020.
- Md. Johirul Islam et al., [Repairing Deep Neural Networks: Fix Patterns and Challenges](https://dl.acm.org/doi/10.1145/3377811.3380378), ICSE 2020.
- Xiaoyu Zhang et al., [AutoTrainer: An Automatic DNN Training Problem Detection and Repair System](https://ieeexplore.ieee.org/document/9402077/), ICSE 2021.
- Nargiz Humbatova et al., [DeepCrime: Mutation Testing of Deep Learning Systems Based on Real Faults](https://dl.acm.org/doi/10.1145/3460319.3464825), ISSTA 2021.
- Mohammad Wardat et al., [DeepDiagnosis: Automatically Diagnosing Faults and Recommending Actionable Fixes in Deep Learning Programs](https://dl.acm.org/doi/10.1145/3510003.3510071), ICSE 2022.
- Jialun Cao et al., [DeepFD: Automated Fault Diagnosis and Localization for Deep Learning Programs](https://dl.acm.org/doi/10.1145/3510003.3510099), ICSE 2022.
- Jinhan Kim et al., [Repairing DNN Architecture: Are We There Yet?](https://arxiv.org/abs/2301.11568), 2023.
- Zhihan Jiang et al., [L4: Diagnosing Large-Scale LLM Training Failures via Automated Log Analysis](https://arxiv.org/abs/2503.20263), FSE 2025.
- Zilong He et al., [DaiFu: In-Situ Crash Recovery for Deep Learning Systems](https://arxiv.org/abs/2507.01628), 2025 preprint.
- Sigma Jahan, [Evaluation-Strategy Gap in Fault Diagnosis of Deep Learning Programs](https://arxiv.org/abs/2606.26492), 2026 preprint.
- Sigma Jahan, [Deep4ge: DNN Training Trajectories for Fault Detection and Diagnosis](https://arxiv.org/abs/2607.12868), 2026 preprint.
- [Towards Robust LLM Post-Training: Automatic Failure Management for Reinforcement Fine-Tuning](https://arxiv.org/abs/2605.04431), 2026 preprint.

### ML-agent and post-training benchmarks

- Jun Shern Chan et al., [MLE-bench: Evaluating Machine Learning Agents on Machine Learning Engineering](https://arxiv.org/abs/2410.07095), 2024/ICLR 2025.
- Qian Huang et al., [MLAgentBench: Evaluating Language Agents on Machine Learning Experimentation](https://proceedings.mlr.press/v235/huang24h.html), ICML 2024.
- Deepak Nathani et al., [MLGym: A New Framework and Benchmark for Advancing AI Research Agents](https://arxiv.org/abs/2502.14499), 2025.
- Qizheng Li et al., [FT-Dojo: Towards Autonomous LLM Fine-Tuning with Language Agents](https://arxiv.org/abs/2603.01712), 2026 preprint.
- Ben Rank et al., [PostTrainBench: Can LLM Agents Automate LLM Post-Training?](https://arxiv.org/abs/2603.08640), 2026 preprint.
- Wanyi Chen et al., [Agent² RL-Bench: Can LLM Agents Engineer Agentic RL Post-Training?](https://arxiv.org/abs/2604.10547), 2026 preprint.

### HPO and verified remediation methodology

- Siyi Liu et al., [Large Language Model Agent for Hyper-Parameter Optimization](https://arxiv.org/abs/2402.01881), 2024.
- Fabio Ferreira et al., [Can LLMs Beat Classical Hyperparameter Optimization Algorithms? A Study on autoresearch](https://arxiv.org/abs/2603.24647), 2026 preprint.
- Yinfang Chen et al., [AIOpsLab: A Holistic Framework to Evaluate AI Agents for Enabling Autonomous Clouds](https://arxiv.org/abs/2501.06706), MLSys 2025.
- [MicroRemed: Benchmarking LLMs in Microservices Remediation](https://arxiv.org/abs/2511.01166), 2025 preprint.
- [SREGym: A Live Benchmark for AI SRE Agents with High-Fidelity Failure Scenarios](https://arxiv.org/abs/2605.07161), 2026 preprint.

