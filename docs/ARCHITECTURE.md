# TrainMD — Architecture & How It Works

A visual walkthrough of the benchmark's three phases and the agent loop, with the
integrity guard at each phase called out. Diagrams are inline SVG so they render on
GitHub. Plain-English explanation follows each.

For the file-by-file code guide, see `TrainMD_Codebase_Walkthrough.md`. For the
research framing, see `problem_statement_v0.3.md`. For design decisions, see
`DECISIONS.md`.

---

## The big picture: three phases

TrainMD runs one exam question through three phases. **Build** manufactures a case,
**Run agent** produces a diagnosis and a proposed repair, and **Verify** confirms
whether the repair actually works. The paid step is phase 2 (LLM calls); phase 3 is
free CPU (retraining) — which is why they are kept separate and phase 3 can be
re-run at no cost.

<svg width="100%" viewBox="0 0 680 340" xmlns="http://www.w3.org/2000/svg" role="img" font-family="sans-serif"><title>TrainMD lifecycle overview</title>
<defs><marker id="a1" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<rect x="40" y="60" width="180" height="70" rx="12" fill="#E6F1FB" stroke="#185FA5" stroke-width="0.5"/><text x="130" y="86" text-anchor="middle" font-size="14" font-weight="500" fill="#0C447C">1. Build case</text><text x="130" y="106" text-anchor="middle" font-size="12" fill="#185FA5">workload + operator</text>
<rect x="250" y="60" width="180" height="70" rx="12" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.5"/><text x="340" y="86" text-anchor="middle" font-size="14" font-weight="500" fill="#3C3489">2. Run agent</text><text x="340" y="106" text-anchor="middle" font-size="12" fill="#534AB7">investigate + submit</text>
<rect x="460" y="60" width="180" height="70" rx="12" fill="#EAF3DE" stroke="#3B6D11" stroke-width="0.5"/><text x="550" y="86" text-anchor="middle" font-size="14" font-weight="500" fill="#27500A">3. Verify repair</text><text x="550" y="106" text-anchor="middle" font-size="12" fill="#3B6D11">rerun, score</text>
<text x="235" y="83" text-anchor="middle" font-size="12" fill="#5F5E5A">case</text><line x1="220" y1="95" x2="248" y2="95" stroke="#888780" stroke-width="1.5" marker-end="url(#a1)"/>
<text x="445" y="83" text-anchor="middle" font-size="12" fill="#5F5E5A">repair</text><line x1="430" y1="95" x2="458" y2="95" stroke="#888780" stroke-width="1.5" marker-end="url(#a1)"/>
<rect x="40" y="200" width="180" height="52" rx="8" fill="#F1EFE8" stroke="#5F5E5A" stroke-width="0.5"/><text x="130" y="220" text-anchor="middle" font-size="12" fill="#444441">visible workspace</text><text x="130" y="238" text-anchor="middle" font-size="12" fill="#444441">+ sealed answer key</text><line x1="130" y1="130" x2="130" y2="198" stroke="#888780" stroke-width="1.5" stroke-dasharray="3 3" marker-end="url(#a1)"/>
<rect x="250" y="200" width="180" height="52" rx="8" fill="#F1EFE8" stroke="#5F5E5A" stroke-width="0.5"/><text x="340" y="220" text-anchor="middle" font-size="12" fill="#444441">diagnosis + evidence</text><text x="340" y="238" text-anchor="middle" font-size="12" fill="#444441">scored (3 free axes)</text><line x1="340" y1="130" x2="340" y2="198" stroke="#888780" stroke-width="1.5" stroke-dasharray="3 3" marker-end="url(#a1)"/>
<rect x="460" y="200" width="180" height="52" rx="8" fill="#F1EFE8" stroke="#5F5E5A" stroke-width="0.5"/><text x="550" y="220" text-anchor="middle" font-size="12" fill="#444441">recovered?</text><text x="550" y="238" text-anchor="middle" font-size="12" fill="#444441">4th axis, CPU only</text><line x1="550" y1="130" x2="550" y2="198" stroke="#888780" stroke-width="1.5" stroke-dasharray="3 3" marker-end="url(#a1)"/>
</svg>

Each phase respects **the wall**: the agent only ever sees the visible side, while the
true cause and the hidden test seeds stay sealed on the answer-key side from build
through verification.

---

## Phase 1 — How a case is built

The factory that manufactures one exam question. It copies the clean workload
(allowlisted files only, so nothing leaks), injects exactly one fault with an
operator, runs training once to produce the broken artifacts, then applies a
**build-time guard**: the run must have *completed but failed* (that is what "silent"
means). A fault that crashed the run, or that didn't actually hurt accuracy, is
rejected — it isn't a valid exam question. Only a passing case is split into the
visible workspace and the sealed answer key.

<svg width="100%" viewBox="0 0 680 540" xmlns="http://www.w3.org/2000/svg" role="img" font-family="sans-serif"><title>How a case is built</title>
<defs><marker id="a2" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<rect x="240" y="30" width="200" height="52" rx="8" fill="#E6F1FB" stroke="#185FA5" stroke-width="0.5"/><text x="340" y="50" text-anchor="middle" font-size="14" font-weight="500" fill="#0C447C">Copy clean workload</text><text x="340" y="68" text-anchor="middle" font-size="12" fill="#185FA5">allowlisted files only</text>
<line x1="340" y1="82" x2="340" y2="118" stroke="#888780" stroke-width="1.5" marker-end="url(#a2)"/>
<rect x="240" y="118" width="200" height="56" rx="8" fill="#FAECE7" stroke="#993C1D" stroke-width="0.5"/><text x="340" y="138" text-anchor="middle" font-size="14" font-weight="500" fill="#712B13">Operator injects fault</text><text x="340" y="156" text-anchor="middle" font-size="12" fill="#993C1D">e.g. lr 0.01 to 0.2</text>
<line x1="340" y1="174" x2="340" y2="210" stroke="#888780" stroke-width="1.5" marker-end="url(#a2)"/>
<rect x="240" y="210" width="200" height="56" rx="8" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.5"/><text x="340" y="230" text-anchor="middle" font-size="14" font-weight="500" fill="#3C3489">Run training once</text><text x="340" y="248" text-anchor="middle" font-size="12" fill="#534AB7">produces the artifacts</text>
<line x1="340" y1="266" x2="340" y2="302" stroke="#888780" stroke-width="1.5" marker-end="url(#a2)"/>
<rect x="240" y="302" width="200" height="56" rx="8" fill="#FAEEDA" stroke="#854F0B" stroke-width="0.5"/><text x="340" y="322" text-anchor="middle" font-size="14" font-weight="500" fill="#633806">Build-time guard</text><text x="340" y="340" text-anchor="middle" font-size="12" fill="#854F0B">completed but failed?</text>
<text x="150" y="326" text-anchor="middle" font-size="12" fill="#A32D2D">no: reject</text><path d="M240 330 L120 330 L120 148 L238 148" fill="none" stroke="#A32D2D" stroke-width="1.5" marker-end="url(#a2)"/>
<line x1="340" y1="358" x2="340" y2="398" stroke="#888780" stroke-width="1.5" marker-end="url(#a2)"/><text x="372" y="382" text-anchor="middle" font-size="12" fill="#3B6D11">yes</text>
<rect x="60" y="398" width="250" height="100" rx="12" fill="#F1EFE8" stroke="#5F5E5A" stroke-width="0.5"/><text x="185" y="422" text-anchor="middle" font-size="14" font-weight="500" fill="#2C2C2A">Visible workspace</text><text x="185" y="446" text-anchor="middle" font-size="12" fill="#444441">broken config, logs,</text><text x="185" y="464" text-anchor="middle" font-size="12" fill="#444441">metrics, checkpoint</text><text x="185" y="482" text-anchor="middle" font-size="12" fill="#444441">(what the agent sees)</text>
<rect x="370" y="398" width="250" height="100" rx="12" fill="#EAF3DE" stroke="#3B6D11" stroke-width="0.5"/><text x="495" y="422" text-anchor="middle" font-size="14" font-weight="500" fill="#27500A">Sealed answer key</text><text x="495" y="446" text-anchor="middle" font-size="12" fill="#3B6D11">true cause, evidence,</text><text x="495" y="464" text-anchor="middle" font-size="12" fill="#3B6D11">recovery thresholds</text><text x="495" y="482" text-anchor="middle" font-size="12" fill="#3B6D11">(never shown)</text>
<path d="M340 358 L185 358 L185 396" fill="none" stroke="#888780" stroke-width="1.5" marker-end="url(#a2)"/><path d="M340 372 L495 372 L495 396" fill="none" stroke="#888780" stroke-width="1.5" marker-end="url(#a2)"/>
</svg>

**Guard:** completed-but-failed. **The wall is created here:** visible workspace vs.
sealed answer key.

---

## Phase 2 — The LLMAgent ReAct loop

The agent never touches the case directly. It sends the conversation to the model;
the model asks to use a tool; the harness runs that tool against the sealed case and
appends the result; the loop repeats until the model calls `submit`. Tokens are
counted into the record immediately after each model call — so a crash never loses
tokens already paid for. Turn and token caps stop a model that never submits from
looping forever.

<svg width="100%" viewBox="0 0 680 560" xmlns="http://www.w3.org/2000/svg" role="img" font-family="sans-serif"><title>LLMAgent ReAct loop</title>
<defs><marker id="a3" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<rect x="240" y="30" width="200" height="52" rx="8" fill="#F1EFE8" stroke="#5F5E5A" stroke-width="0.5"/><text x="340" y="50" text-anchor="middle" font-size="14" font-weight="500" fill="#2C2C2A">Start trial</text><text x="340" y="68" text-anchor="middle" font-size="12" fill="#444441">system prompt + tools</text>
<line x1="340" y1="82" x2="340" y2="118" stroke="#888780" stroke-width="1.5" marker-end="url(#a3)"/>
<rect x="240" y="118" width="200" height="56" rx="8" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.5"/><text x="340" y="138" text-anchor="middle" font-size="14" font-weight="500" fill="#3C3489">Call the model</text><text x="340" y="156" text-anchor="middle" font-size="12" fill="#534AB7">count tokens now</text>
<line x1="340" y1="174" x2="340" y2="210" stroke="#888780" stroke-width="1.5" marker-end="url(#a3)"/>
<rect x="250" y="210" width="180" height="56" rx="8" fill="#FAEEDA" stroke="#854F0B" stroke-width="0.5"/><text x="340" y="230" text-anchor="middle" font-size="14" font-weight="500" fill="#633806">Model responds</text><text x="340" y="248" text-anchor="middle" font-size="12" fill="#854F0B">submit, or a tool?</text>
<text x="205" y="292" text-anchor="middle" font-size="12" fill="#5F5E5A">tool call</text><path d="M250 244 L150 244 L150 320" fill="none" stroke="#888780" stroke-width="1.5" marker-end="url(#a3)"/>
<rect x="60" y="320" width="180" height="56" rx="8" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/><text x="150" y="340" text-anchor="middle" font-size="14" font-weight="500" fill="#085041">Run tool in harness</text><text x="150" y="358" text-anchor="middle" font-size="12" fill="#0F6E56">sealed case only</text>
<line x1="150" y1="376" x2="150" y2="416" stroke="#888780" stroke-width="1.5" marker-end="url(#a3)"/>
<rect x="60" y="416" width="180" height="56" rx="8" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/><text x="150" y="436" text-anchor="middle" font-size="14" font-weight="500" fill="#085041">Append result</text><text x="150" y="454" text-anchor="middle" font-size="12" fill="#0F6E56">to conversation</text>
<text x="345" y="405" text-anchor="middle" font-size="12" fill="#5F5E5A">loop back</text><path d="M150 472 L150 516 L340 516 L340 174" fill="none" stroke="#1D9E75" stroke-width="1.5" marker-end="url(#a3)"/>
<text x="500" y="238" text-anchor="middle" font-size="12" fill="#5F5E5A">submit called</text><path d="M430 244 L540 244 L540 320" fill="none" stroke="#888780" stroke-width="1.5" marker-end="url(#a3)"/>
<rect x="450" y="320" width="180" height="56" rx="8" fill="#EAF3DE" stroke="#3B6D11" stroke-width="0.5"/><text x="540" y="340" text-anchor="middle" font-size="14" font-weight="500" fill="#27500A">Finalize record</text><text x="540" y="358" text-anchor="middle" font-size="12" fill="#3B6D11">score + save</text>
<line x1="340" y1="266" x2="340" y2="300" stroke="#888780" stroke-width="1.5" stroke-dasharray="3 3" marker-end="url(#a3)"/>
<rect x="250" y="300" width="180" height="34" rx="6" fill="#F1EFE8" stroke="#5F5E5A" stroke-width="0.5"/><text x="340" y="317" text-anchor="middle" font-size="12" fill="#444441">also stops at turn / token cap</text>
</svg>

**Guard:** sealed case + turn/token caps + immediate token capture. **This is the
paid phase.**

---

## Phase 3 — How the evaluator verifies a repair

The sealed grader that makes "verified repair" real. It first validates the proposed
fix (legal key, in range); an illegal repair is rejected with no rerun. Then — the
security-critical step — it builds a **fresh workspace from the trusted source** (never
the agent's, which could be tampered), re-applies the fault and the fix from the
hidden manifest, and retrains on each hidden seed the agent never saw. Recovery counts
only if *every* seed clears the healthy tolerance.

<svg width="100%" viewBox="0 0 680 560" xmlns="http://www.w3.org/2000/svg" role="img" font-family="sans-serif"><title>How the evaluator verifies a repair</title>
<defs><marker id="a4" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
<rect x="240" y="30" width="200" height="56" rx="8" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.5"/><text x="340" y="50" text-anchor="middle" font-size="14" font-weight="500" fill="#3C3489">Validate repair</text><text x="340" y="68" text-anchor="middle" font-size="12" fill="#534AB7">legal keys + range?</text>
<text x="150" y="45" text-anchor="middle" font-size="12" fill="#A32D2D">illegal</text><path d="M240 58 L120 58 L120 500 L238 500" fill="none" stroke="#A32D2D" stroke-width="1.5" marker-end="url(#a4)"/><text x="175" y="516" text-anchor="middle" font-size="12" fill="#A32D2D">rejected: no rerun</text>
<line x1="340" y1="86" x2="340" y2="122" stroke="#888780" stroke-width="1.5" marker-end="url(#a4)"/>
<rect x="240" y="122" width="200" height="56" rx="8" fill="#E6F1FB" stroke="#185FA5" stroke-width="0.5"/><text x="340" y="142" text-anchor="middle" font-size="14" font-weight="500" fill="#0C447C">Fresh workspace</text><text x="340" y="160" text-anchor="middle" font-size="12" fill="#185FA5">from trusted source</text>
<line x1="340" y1="178" x2="340" y2="214" stroke="#888780" stroke-width="1.5" marker-end="url(#a4)"/>
<rect x="240" y="214" width="200" height="56" rx="8" fill="#FAECE7" stroke="#993C1D" stroke-width="0.5"/><text x="340" y="234" text-anchor="middle" font-size="14" font-weight="500" fill="#712B13">Re-apply fault + fix</text><text x="340" y="252" text-anchor="middle" font-size="12" fill="#993C1D">from hidden manifest</text>
<line x1="340" y1="270" x2="340" y2="306" stroke="#888780" stroke-width="1.5" marker-end="url(#a4)"/>
<rect x="240" y="306" width="200" height="56" rx="8" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.5"/><text x="340" y="326" text-anchor="middle" font-size="14" font-weight="500" fill="#3C3489">Retrain on a seed</text><text x="340" y="344" text-anchor="middle" font-size="12" fill="#534AB7">hidden: 100, 101, 102</text>
<text x="512" y="290" text-anchor="middle" font-size="12" fill="#5F5E5A">more seeds</text><path d="M440 334 L540 334 L540 250 L442 250" fill="none" stroke="#534AB7" stroke-width="1.5" marker-end="url(#a4)"/>
<line x1="340" y1="362" x2="340" y2="398" stroke="#888780" stroke-width="1.5" marker-end="url(#a4)"/>
<rect x="240" y="398" width="200" height="56" rx="8" fill="#FAEEDA" stroke="#854F0B" stroke-width="0.5"/><text x="340" y="418" text-anchor="middle" font-size="14" font-weight="500" fill="#633806">All seeds pass?</text><text x="340" y="436" text-anchor="middle" font-size="12" fill="#854F0B">above tolerance?</text>
<path d="M240 426 L150 426 L150 468" fill="none" stroke="#A32D2D" stroke-width="1.5" marker-end="url(#a4)"/><path d="M440 426 L540 426 L540 468" fill="none" stroke="#3B6D11" stroke-width="1.5" marker-end="url(#a4)"/>
<rect x="60" y="468" width="180" height="44" rx="8" fill="#FCEBEB" stroke="#A32D2D" stroke-width="0.5"/><text x="150" y="490" text-anchor="middle" font-size="14" font-weight="500" fill="#791F1F">not recovered</text>
<rect x="450" y="468" width="180" height="44" rx="8" fill="#EAF3DE" stroke="#3B6D11" stroke-width="0.5"/><text x="540" y="490" text-anchor="middle" font-size="14" font-weight="500" fill="#27500A">recovered</text>
</svg>

**Guard:** validate + fresh trusted rebuild + all-seeds-pass. **This is the free
(CPU) phase**, re-runnable on demand from a saved submission.

---

## Why this is trustworthy

A real model investigates a real fault, proposes a fix, and an independent sealed
grader confirms the fix works on data the model never touched — with an integrity
guard at every phase and the wall holding from build through verification. That
end-to-end integrity, demonstrated on a real trial, is the contribution.

| Phase | Produces | Integrity guard | Cost |
|---|---|---|---|
| 1. Build | visible workspace + sealed key | completed-but-failed | CPU |
| 2. Run agent | diagnosis, evidence, repair | sealed case + caps + token capture | **paid (LLM)** |
| 3. Verify | recovered / not recovered | validate + trusted rebuild + all-seeds | CPU |

---

## The experiment layer (as of pre-sweep commit 75b6e2d)

The three phases above are one *trial*. Around them sits the experiment layer that turns trials
into a pre-registered, cost-capped sweep — and the pieces that make the comparison meaningful.

**Two contestant agents** (they differ in ONE thing — how they investigate — sharing prompt
text, submit schema, reference band, and healthy-runs guidance verbatim, so a score gap is
attributable to tools, not wording):

| | ReAct agent | Static baseline (the H6 control) |
|---|---|---|
| Investigation | a tool loop (read → reason → repeat) | one prompt with the whole run, one call |
| Reads | on demand, through the sealed tools | all artifacts up front, through the sealed tools |
| Cost | multiple calls; tokens grow with turns | one call |
| Question it answers | how well an agent *investigates* | how far *seeing everything at once* gets you |

**Three tiers of case** (the `layer` field): **dynamics** (silent — completes but bad),
**execution** (crash — fails to complete), and **control** (healthy — no fault; a submitted
repair is a scored *false intervention*, so over-eagerness is measurable). Trusted probe agents
(oracle, degenerate) and an untrusted `always_broken` baseline are the floors/ceilings the gates
check against; they never enter an aggregate (the `trusted` flag excludes them).

**The pipeline** (each stage is free except "run agents"; every gate exits nonzero on a real
problem and writes a dated table to `docs/audits/`):

```
gate-known-answer  →  sweep plan  →  (commit the plan)  →  run --phase agents  →  run --phase verify  →  report
   (certify GT)      (pre-register)    (pre-registration)      (PAID, capped)         (free, CPU)        (H1–H6)
        │                                                          │
   audit-index ──────────── refuse to aggregate over a broken index ┘
```

`plan` writes the committed pre-registration (build_id-pinned cells + cost estimate); `run
--phase agents` refuses unless the gates are green, the plan matches the built cases, and the plan
is committed, then runs the paid trials with a hard cost cap, resume, and a circuit breaker;
`run --phase verify` does the free recovery reruns; `report` computes the hypothesis metrics.
The tracked `sweeps/<name>_manifest.yaml` is the paper's compute statement.
