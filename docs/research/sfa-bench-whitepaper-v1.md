SFA-Bench: A Grammar for Governed Improvement

A deterministic offline harness for evaluating, ratifying, recording, rejecting, and halting proposed AI/system improvements under frozen judgment

Author: Matthew Neal
Project: Iota Verbum Core / SFA-Bench
Release basis: fz-v1.0.0
Status: White Paper Draft 1.0

Abstract

As AI systems become increasingly capable of generating code, proposing changes, repairing workflows, and participating in their own development environments, the central governance problem is no longer simply whether a system can produce an improvement. The deeper problem is whether a proposed improvement can be judged without allowing the proposer to control the conditions of its own approval.

SFA-Bench introduces a deterministic offline governance harness for proposed AI/system improvement. Its purpose is not to demonstrate autonomous self-improving AI, nor to claim proof of alignment or general safety. Its purpose is narrower and more defensible: to separate builder from judge, proposal from promotion, evidence from ratification, and success from lineage. In doing so, it defines a “grammar for governed improvement”: an ordered protocol in which a candidate must be declared, evaluated under protected conditions, classified, ratified by explicit human action, recorded into lineage, or halted by circuit breakers.

The public fz-v1.0.0 release packages this governed improvement loop into a reproducible research release, including a research overview, claims and limits, reproducibility guide, threat model, architecture, reviewer commands, and checklist fixture. The release records that the candidate was verified, scope-audited, human-ratified through pull request review, merged, and post-merge verification passed.

This paper presents the problem, system architecture, milestone chain, threat model, claims, limitations, and future research direction of SFA-Bench as a governance assay for candidate improvement.

1. The Problem: Self-Crowning Improvement

Most AI benchmarks ask whether a model can solve a task. Can it answer a question? Can it generate code? Can it repair a bug? Can it pass a test suite?

Those questions matter, but they are not sufficient for systems that participate in improvement loops.

When an AI-assisted system proposes a change to a codebase, benchmark, policy, evaluator, or governance process, a new danger appears: the candidate may not merely attempt to improve performance; it may alter the conditions under which performance is judged. This is the danger of self-crowning improvement.

A self-crowning improvement loop has a collapsed grammar:

builder → evaluator → approval → memory → promotion

The same actor proposes the change, judges the change, selects the metric, records the result, and declares the improvement. Even when the vocabulary sounds safe—“verified,” “aligned,” “auditable,” “transparent,” “improved”—the order is corrupt. Evidence arrives after promotion. Ratification is assumed rather than given. Memory is edited rather than preserved. The judge is no longer outside the candidate.

SFA-Bench begins from a different premise:

Improvement is legitimate only when the one who proposes the change is not permitted to control the conditions by which the change is judged, remembered, ratified, and promoted.

This is why SFA-Bench is best understood not only as a benchmark, but as a governance grammar.

2. What Is a Grammar for Governed Improvement?

Grammar is not merely vocabulary. Grammar is the order that makes speech intelligible. It determines what governs what, what modifies what, what must come before what, and what may never be collapsed into something else.

In ordinary language, grammar prevents nonsense.

In moral life, grammar prevents self-deception.

In AI governance, grammar prevents self-approval.

A grammar for governed improvement insists on ordered distinctions:

Proposal is not proof.
Builder is not judge.
Evaluation is not ratification.
Passing is not promotion.
Promotion is not lineage until recorded.
Failure is not waste.
Memory is not optional.
A breaker is not an inconvenience.
The crown is not self-given.

The ordered form of governed improvement is:

proposal
→ pre-registration
→ frozen judge
→ evaluation
→ deterministic gate
→ human ratification
→ lineage
→ circuit breaker

SFA-Bench exists to make that order executable.

3. Core Thesis

The core thesis of SFA-Bench is:

Proposed improvements must be governed by a protected sequence in which candidates are evaluated without control over the evaluator, ratified without automatic promotion, and recorded without erasing rejected or halted attempts.

This leads to four controlling design principles.

First, the evaluator must be protected. A candidate cannot be allowed to modify the judge that determines whether it passes.

Second, metrics and conditions must be declared before the result is known. Otherwise, success can be retrofitted after the fact.

Third, promotion must require explicit human ratification. A green test result may make a candidate eligible for consideration, but it must not automatically crown the candidate.

Fourth, the history of failure must be preserved. Rejections, malformed packets, red gates, and halted runs are not noise. They are governance evidence.

4. What SFA-Bench Is

SFA-Bench is a deterministic offline harness for candidate improvement governance. It evaluates whether proposed changes can be inspected, tested, classified, ratified, recorded, rejected, or halted under protected conditions.

It is designed around a strict separation of roles:

Builder      proposes a candidate.
Harness      creates an evidence packet.
Evaluator    runs protected checks.
Gate         classifies outcome.
Human        ratifies, rejects, or halts.
Lineage      records the result.
Breaker      stops unsafe movement.

The system is intentionally offline and deterministic. Its purpose is not to depend on live model APIs, hidden services, or private state. Its value lies in reproducibility: a reviewer should be able to clone the repository, run the commands, inspect the outputs, and see whether the governance loop behaves as claimed.

The fz-v1.0.0 release positions the system as a reproducible research release, not as a finished commercial product or a claim of general AI safety.

5. What SFA-Bench Is Not

A credible white paper must state limits as clearly as claims.

SFA-Bench is not autonomous self-improving AI.

It does not prove that an AI system is aligned.

It does not guarantee safety.

It does not replace human judgment.

It does not evaluate all possible AI risks.

It does not prevent every form of deception, misuse, or governance failure.

It does not make the builder trustworthy by assumption.

Instead, SFA-Bench provides a constrained experimental environment for a narrower question:

Can a proposed improvement be processed through a reproducible governance loop without allowing the candidate to rewrite its own judge?

That narrower claim is the strength of the project.

6. Milestone Chain

The public releases from fz-v0.7.0 to fz-v1.0.0 form the current evidence chain for the white paper.

6.1 Item 7: End-to-End Runner

The fz-v0.7.0 release added AutoLab Item 7: a frozen end-to-end runner for the full proposal, gate, human ratification, lineage, and breaker sequence. It also added explicit rejection events for red gates, failed human approval, malformed promotion records, and controller or lineage failures, giving circuit-breaker accounting auditable history. The release notes record that PR checks passed and that local LF-worktree verification passed, including the runner demo, full test discovery, verify_all.py, release_gate.py --ci, and frozen_zone_check.py --ci --base origin/main.

This was the governance spine.

6.2 Item 8: Governed Documentation Candidate

The fz-v0.8.0 release added documentation, examples, and a non-frozen fixture explaining the AutoLab Item 7 runner. It records that the candidate was built on PR #32, CI passed, human ratification was recorded on the PR, and post-merge verification passed in an LF worktree.

This was important because it demonstrated the grammar on a low-risk real candidate: build, verify, ratify, merge, release.

6.3 Item 9: External Candidate Harness

The fz-v0.9.0 release added the External Candidate Harness. According to the release notes, Item 9 accepts a branch or commit target, inspects changed files against origin/main, detects frozen-path changes, runs protected verification commands, classifies governed outcomes, and generates candidate-packet artifacts plus a ratification template. The candidate was verified, scope-audited, human-ratified on PR #33, merged through PR, and passed post-merge verification.

This converted the governance loop from a demo into a usable external candidate workflow.

6.4 Item 10: Ratification Packet + Lineage CLI

The fz-v0.10.0 release added the Ratification Packet + Lineage CLI. It consumes a Unit 9 candidate packet, prepares ratification artifacts, requires explicit human action for ratify, reject, or halt, and writes a lineage record. The release records smoke testing, scope audit, human ratification through PR #34, merge, and post-merge verification.

This made the human ratification step explicit and executable.

6.5 Item 11: Adversarial Candidate Suite

The fz-v0.11.0 release added the Adversarial Candidate Suite. It runs controlled trials for safe docs candidates, frozen-path tampering, release-gate failure, non-promotion ratification attempts, and malformed packets. The candidate was verified, scope-audited, human-ratified through PR #35, merged, and passed post-merge verification.

This moved SFA-Bench from workflow into pressure testing.

6.6 Item 12: v1.0 Research Release Pack

The fz-v1.0.0 release packages the governed improvement loop into a reproducible research release. It includes the v1 research overview, claims and limits, reproducibility guide, threat model, architecture, reviewer commands, and checklist fixture. The release records that the candidate was verified, scope-audited, human-ratified through PR, merged, and passed post-merge verification.

This is the whitepaper moment.

7. System Architecture

At the highest level, SFA-Bench v1.0.0 can be represented as:

external candidate
→ candidate harness
→ candidate packet
→ protected verification
→ outcome classification
→ ratification packet
→ explicit human action
→ lineage record
→ adversarial pressure

Each stage exists to prevent a specific collapse.

The external candidate is the proposed change. It may come from a human, Codex, another model, a branch, or a commit. It is not trusted by default.

The candidate harness inspects the candidate against a base reference. It identifies changed files, checks for frozen-path contact, runs protected verification commands, and produces an evidence packet.

The candidate packet is the structured evidence object. It records what was tested, against what base, with what files changed, what commands ran, what passed, what failed, and what outcome was assigned.

Protected verification is the reproducible command path. It exists so that the candidate’s claims are not accepted merely because the builder can explain them persuasively.

Outcome classification converts command results into governance states such as promotion-ready, rejected by tests, rejected by release gate, rejected by frozen-zone check, or halted by preflight.

The ratification packet prepares the evidence for human review. It does not promote automatically.

Explicit human action is required to ratify, reject, or halt. This is not decorative. It is the point at which a responsible reviewer binds a judgment to a specific target.

The lineage record preserves the outcome. It prevents the system from narrating only successful candidates.

The adversarial suite then tests whether unsafe or malformed flows are rejected or halted in predictable ways.

8. The Candidate Lifecycle

A governed SFA-Bench candidate moves through five major states.

8.1 Proposed

A builder proposes a candidate. At this stage, the candidate has no authority. It is merely an object to be judged.

8.2 Packeted

The external candidate harness inspects the candidate and creates a candidate packet. This packet becomes the evidence basis for review.

8.3 Classified

The system runs protected checks and classifies the candidate. It may be promotion-ready, rejected, or halted.

8.4 Ratified, Rejected, or Halted

The human reviewer acts explicitly. The system must not infer human approval from a passing check.

8.5 Recorded

The ratification packet and lineage CLI write the result into structured history. The system remembers not only what passed, but what failed or was halted.

This lifecycle is the practical form of the grammar.

9. Threat Model

SFA-Bench v1.0.0 is designed around a practical threat model for candidate improvement.

9.1 Frozen-Path Tampering

A candidate may attempt to modify the evaluator, release gate, ledger, frozen-zone manifest, or other protected governance files. This threatens the independence of judgment.

The correct response is not ordinary evaluation. The correct response is halt.

9.2 Metric Gaming

A candidate may attempt to define success after seeing results. This turns evaluation into rationalisation.

The response is pre-registration and sealed evaluation criteria.

9.3 Dirty Release Artifacts

A candidate may leave untracked outputs, generated artifacts, temporary files, or staged runtime material in the working tree. This threatens reproducibility.

The response is release-gate rejection.

9.4 Malformed Candidate Packets

A candidate packet may omit required fields, corrupt evidence shape, or present an incomplete record.

The response is packet rejection.

9.5 Ratification Misuse

A human or tool may attempt to ratify a candidate that is not promotion-ready.

The response is refusal.

9.6 Lineage Spoofing

A system may attempt to create a lineage record without valid evidence or explicit human action.

The response is structured validation and refusal to record improper promotion.

9.7 Erased Failure Memory

A system may attempt to discard failed attempts, red gates, or halted runs.

The response is auditable rejection and halt history.

9.8 Repeated Unsafe Proposals

A system may repeatedly attempt to alter frozen files, exploit metrics, or bypass ratification.

The response is breaker accounting and halt conditions.

10. Adversarial Testing

The adversarial suite is a decisive part of the v1.0.0 research story because it tests not only the happy path, but the grammar under pressure.

The suite introduced in fz-v0.11.0 runs controlled trials across five categories: safe docs candidates, frozen-path tampering, release-gate failure, non-promotion ratification attempts, and malformed packets.

The point is not merely that SFA-Bench can pass its own normal checks. The stronger point is that it can produce expected failures. A governance system that cannot fail closed is not a governance system. It is a performance ritual.

The adversarial suite asks:

Does a harmless candidate pass?
Does a frozen-path tamper halt?
Does a dirty release condition reject?
Does ratification refuse a non-promotion candidate?
Does a malformed packet fail?

If all five behave predictably, the system begins to demonstrate not only capability, but constraint.

11. Evidence and Reproducibility

SFA-Bench’s whitepaper claim depends on reproducibility.

A reviewer should be able to run a command path such as:

git clone --config core.autocrlf=false https://github.com/iotaverbum-core/sfa-bench.git
cd sfa-bench

py -3 verify_all.py
py -3 autolab_runner_demo.py
py -3 external_candidate_harness.py --help
py -3 ratification_packet_cli.py --help
py -3 adversarial_candidate_suite.py --ci
py -3 release_gate.py --ci
py -3 frozen_zone_check.py --ci --base origin/main

The LF checkout detail is not incidental. Frozen-zone attestation is byte-sensitive. If line endings drift, the frozen-zone hash can fail even when the logic appears unchanged. The reproducibility discipline therefore includes not merely commands, but working-tree hygiene.

The fz-v1.0.0 release records that the v1 research release pack includes reviewer commands and a reproducibility guide.

12. Claims

SFA-Bench v1.0.0 supports the following claims.

Claim 1: SFA-Bench Defines a Reproducible Governance Loop

SFA-Bench provides a public, deterministic workflow for processing proposed improvements through evidence generation, classification, human ratification, and lineage recording.

Claim 2: SFA-Bench Separates Builder From Judge

The system is designed to prevent ordinary candidate promotion when the candidate attempts to touch protected governance surfaces.

Claim 3: SFA-Bench Supports External Candidate Evaluation

Item 9 added a harness that accepts a branch or commit target, inspects changed files, detects frozen-path changes, runs protected verification, classifies outcomes, and generates candidate-packet artifacts.

Claim 4: SFA-Bench Requires Explicit Human Ratification

Item 10 added a CLI that consumes a candidate packet, prepares ratification artifacts, requires explicit human action, and writes a lineage record.

Claim 5: SFA-Bench Can Test Unsafe and Malformed Flows

Item 11 added adversarial trials for safe candidates, frozen-path tampering, release-gate failure, non-promotion ratification attempts, and malformed packets.

Claim 6: SFA-Bench v1.0.0 Is Packaged as a Research Artifact

The v1.0.0 release includes the overview, claims and limits, reproducibility guide, threat model, architecture, reviewer commands, and checklist fixture.

13. Limits

SFA-Bench v1.0.0 does not establish that a model is aligned.

It does not prove that a model will not deceive.

It does not guarantee that a human reviewer will make the right decision.

It does not cover every attack surface in real-world AI deployment.

It does not solve interpretability.

It does not eliminate the need for institutional governance, external audit, or domain-specific safety review.

It does not prove that future autonomous systems will remain safe under open-ended self-improvement.

Its claim is narrower:

In this repository and under its defined command path, SFA-Bench demonstrates a reproducible grammar for governing proposed improvements without allowing ordinary candidates to rewrite the judge, bypass ratification, or enter lineage automatically.

That limit is not a weakness. It is what makes the claim credible.

14. Why This Matters

The future of AI development will not be only about models answering questions. It will be about models participating in code generation, evaluation, repair, optimisation, and governance workflows.

The crucial question will not be:

Can the model improve the system?

The deeper question will be:

Can the proposed improvement remain under judgment outside itself?

SFA-Bench matters because it treats this as an architectural question rather than a slogan. It refuses to let “improvement” mean merely “a change the builder calls better.” It demands order:

proposal before proof
proof before ratification
ratification before promotion
promotion before lineage
lineage before memory
memory before further improvement

The system is built around the refusal of self-crowning intelligence.

15. Theological and Philosophical Frame

Although SFA-Bench is technical, its deepest insight is philosophical: language alone is not enough. Systems can use the right words in the wrong order. They can say “safe,” “verified,” “transparent,” or “aligned” while placing judgment under the control of the candidate.

The problem is not only vocabulary. It is syntax, authority, and placement.

This is why the phrase “grammar for governed improvement” is more than metaphor. It names the structure by which improvement becomes meaningful.

A false grammar says:

I propose.
I judge.
I approve.
I remember.
I crown.

A governed grammar says:

I propose.
Another judges.
Evidence is preserved.
A human ratifies.
Lineage records.
A breaker can halt.

In this sense, SFA-Bench is not simply a technical project. It is an argument about order.

16. Relationship to AI Safety and Evaluation

Many AI evaluation approaches focus on capability, benchmark performance, task success, or error rates. Those remain important. But SFA-Bench introduces a complementary concern: governability under improvement pressure.

A model that can solve tasks may still be dangerous if it cannot remain under an external judge when asked to improve the system that judges it.

A model that can generate patches may still be unsafe if it attempts to change the evaluator, hide failure, or promote itself without ratification.

A model that passes ordinary tests may still require rejection if the working tree is dirty, the packet is malformed, the lineage is spoofed, or the ratification state is invalid.

SFA-Bench therefore belongs to a family of evaluation tools concerned not only with performance, but with process integrity.

Its fundamental question is:

Can candidate improvement be made auditable, rejectable, haltable, and memorable?

17. Future Work

SFA-Bench v1.0.0 should be treated as the first complete research release, not the endpoint.

The next phase should focus on external credibility.

17.1 Third-Party Reproduction

The project should invite independent users to clone the repository, run the reproducibility commands, and report whether the published claims reproduce on fresh machines.

17.2 Multi-Model Candidate Trials

Future trials should submit candidates generated by different builders: Codex, Claude, Gemini, DeepSeek, local models, and human contributors. The point is not to crown a best model, but to classify how different builders behave under frozen governance.

17.3 Stronger Adversarial Suite

The adversarial suite should expand beyond the initial five cases to include metric gaming, lineage spoofing, packet replay, stale base references, hidden generated artifacts, repeated rejected proposals, and attempted amendment-channel abuse.

17.4 Formal Ratification Semantics

Future releases should strengthen the semantics of ratification: what exactly is being approved, by whom, under which evidence, with what scope, and with what rollback implications.

17.5 Public Governance Reports

SFA-Bench should generate human-readable governance reports for each candidate, making it easier for reviewers to understand why a candidate was classified as promotion-ready, rejected, or halted.

17.6 DOI and Archival Release

For academic credibility, the repository and v1.0.0 release should eventually be archived through a persistent research archive with a DOI.

18. Conclusion

SFA-Bench v1.0.0 is not a claim that AI can safely improve itself.

It is a claim that proposed improvement requires grammar.

It argues that the danger of self-improvement is not only capability, but self-approval. A system becomes dangerous when it proposes the change, controls the evaluator, selects the metric, edits the memory, and crowns the result.

SFA-Bench answers with order.

The builder may propose, but may not judge.

The candidate may be tested, but may not rewrite the test.

A passing result may become eligible, but may not promote itself.

A human may ratify, reject, or halt, but must bind that action to evidence.

Lineage must record not only success, but failure.

Circuit breakers must be allowed to stop motion.

This is the grammar for governed improvement.

The crown is not self-given.

Appendix A: Milestone Summary
fz-v0.7.0   End-to-end runner
fz-v0.8.0   Governed documentation candidate
fz-v0.9.0   External Candidate Harness
fz-v0.10.0  Ratification Packet + Lineage CLI
fz-v0.11.0  Adversarial Candidate Suite
fz-v1.0.0   Research Release Pack
Appendix B: Minimal Reproduction Commands
git clone --config core.autocrlf=false https://github.com/iotaverbum-core/sfa-bench.git
cd sfa-bench

py -3 verify_all.py
py -3 autolab_runner_demo.py
py -3 external_candidate_harness.py --help
py -3 ratification_packet_cli.py --help
py -3 adversarial_candidate_suite.py --ci
py -3 release_gate.py --ci
py -3 frozen_zone_check.py --ci --base origin/main
Appendix C: Clean Whitepaper Claim

SFA-Bench v1.0.0 is a deterministic offline governance harness for candidate improvement. It separates builder from judge, evidence from ratification, and promotion from lineage, so that proposed AI/system changes can be evaluated, rejected, halted, or explicitly ratified without allowing ordinary candidates to rewrite the conditions of their own approval.