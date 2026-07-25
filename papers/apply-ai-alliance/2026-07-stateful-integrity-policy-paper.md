# From Boundary Compliance to Stateful Integrity
## A policy standard for evaluating stateful and agentic AI in Europe
**Evidence from a preregistered 48-execution study and recommendations for the Apply AI Alliance**

**Matthew Neal**
SFA-Bench project | Independent policy contribution
25 July 2026 | Version 1.0

> **Policy decision requested**
>
> The Apply AI Alliance should convene a six-month technical working group to draft and pilot a Stateful AI Evaluation Protocol. The protocol should produce a core state-contract schema, minimum reporting requirements, three sector pilots, a public-procurement model clause and a formal contribution to European AI standardisation.

## Executive summary
The policy problem is no longer limited to whether an AI model can produce a correct answer. In strategic-sector deployments, the relevant question is whether an AI system can carry obligations through time. A citizen-service assistant must remember the authorised case identifier without importing a prohibited field. A healthcare workflow must preserve a clinically relevant instruction while respecting access boundaries. A financial or industrial agent must update permissions, expiry conditions and task state correctly across tools, hand-offs and interruptions.

Existing AI benchmarks have moved beyond isolated question answering toward interactive environments, tool use and long-horizon tasks. They have exposed failures in consistency, long-term reasoning, context use and rule following. What remains under-specified in policy is a narrower but operationally important distinction: a system may respect an information boundary and still fail because it loses information it was authorised and required to retain.

SFA-Bench R2 isolated that distinction in a frozen memory-boundary task. Across 48 preregistered and separately ratified executions, 12 outcomes lost the required permitted field customer_id while none used forbidden state. The strongest descriptive signal was not the representation format. It was the presence of an explicit retention reminder: complete preservation was observed in all 24 reminder executions and in 12 of 24 no-reminder executions. The result is task-specific and descriptive. It does not justify a provider-level safety conclusion. It does show why model-only assurance is insufficient: a small change in operational scaffolding materially altered observed reliability.

The European Union already has the legal and institutional foundations for better evaluation. The AI Act requires continuous risk management and testing against prior-defined metrics for high-risk systems; it requires appropriate accuracy and robustness and encourages the development of benchmarks and measurement methodologies; it requires state-of-the-art model evaluation for general-purpose AI models with systemic risk; and it requires post-market monitoring. The Apply AI Strategy is intended to accelerate adoption in strategic sectors while considering benefits and risks. The Apply AI Alliance is expressly designed to bring papers, recommendations, operational challenges and possible policy measures into Commission policy-making.

This paper recommends one concrete action: establish a Stateful AI Evaluation Protocol (SAEP). SAEP should not create a new legal category or prescribe a particular memory architecture. It should define a minimum evidence standard for any deployment whose correct output or action depends on state carried across two or more stages. The standard should require: a declared state contract; sequence-based test cases; separate metrics for required-state preservation and prohibited-state exclusion; disclosure of the evaluated system configuration; repeated trials; immutable evidence records; independent or separated judgement; and re-evaluation after material changes.

The immediate route should be a Commission-convened working group under the Apply AI Alliance, followed by pilots through AI Testing and Experimentation Facilities, regulatory sandboxes and public procurement. Results should feed into CEN-CENELEC JTC 21 work on risk management, record keeping, accuracy, robustness, quality management and conformity assessment. The objective is not another leaderboard. It is a credible answer to a procurement and governance question: what evidence shows that an AI system can maintain the right state, reject the wrong state, and do both reliably over the full workflow?

## Abstract
Europe’s AI policy increasingly depends on evidence that systems perform consistently across a lifecycle and in the conditions in which they are deployed. Yet common evaluation practice still compresses reliability into a task-success rate, a model score, or a one-off demonstration. That approach is incomplete for stateful and agentic systems, whose correct operation depends on preserving, updating and excluding information across a sequence of interactions.

This paper proposes “stateful integrity” as a distinct evaluation property: the capacity of an AI system to preserve information that is authorised and required, exclude information that is prohibited, apply state changes correctly, and maintain those distinctions through a multi-step workflow. It reports a preregistered 2 × 2 study of one frozen memory-boundary task. Forty-eight executions were completed and separately ratified, varying public-state representation (prose or JSON) and the presence of an explicit retention reminder. Complete permitted-state preservation occurred in 36 of 48 executions. The 12 partial outcomes all involved omission of the required permitted field customer_id. No forbidden-state use was observed. Reminder conditions achieved complete preservation in 24 of 24 executions, compared with 12 of 24 without reminders. The pooled JSON-minus-prose difference was −0.083333 and the pooled reminder-minus-no-reminder difference was +0.500000. No significance test was performed, and the study does not establish general model quality, safety, fitness or provider ranking.

The policy implication is not that regulators should prescribe reminders. It is that reliability claims for stateful systems should be bound to the deployed configuration and supported by sequence-based tests, separate state-preservation and boundary-compliance metrics, repeated trials, change-triggered re-evaluation and an auditable evidence chain. The paper recommends that the European Commission, through the Apply AI Alliance, develop and pilot a Stateful AI Evaluation Protocol for strategic-sector adoption, public procurement, testing facilities, regulatory sandboxes and European standardisation work.

**Keywords:** stateful AI; agentic AI; AI evaluation; reliability; AI Act; Apply AI Alliance; robustness; public procurement; evidence governance

## 1. Policy position
The European Commission should establish a minimum evidence standard for stateful and agentic AI systems used in strategic sectors and public services. The standard should require evaluators to test whether an AI system preserves authorised and required information, excludes prohibited information, applies state changes correctly and maintains those distinctions across a complete workflow.

The proposed instrument is a Stateful AI Evaluation Protocol (SAEP). It should begin as practical Commission guidance and a multi-sector pilot under the Apply AI Alliance, not as a new statutory category. Its outputs should then inform public-procurement guidance, sectoral assurance practices, AI Testing and Experimentation Facilities, regulatory sandboxes, post-market monitoring and European harmonised standards.

The central policy claim is deliberately narrow:

An AI system should not be described as reliable merely because it completes a task once or avoids a prohibited disclosure. For stateful work, reliability also requires evidence that the authorised state needed to complete the task survives the sequence.

This claim fits the Commission’s current adoption agenda. The Apply AI Strategy promotes AI uptake in strategic sectors and the public sector while expressly coupling adoption with consideration of benefits and risks. The Apply AI Alliance is the Commission’s coordination forum for stakeholder papers, recommendations, sectoral challenges and possible policy measures (European Commission, 2025a; European Commission, 2025b). SAEP would give that governance structure a concrete measurement project: define what must be evidenced before a state-dependent AI workflow is trusted, purchased or scaled.

## 2. The evaluation gap
2.1 From capability scores to system reliability

Traditional benchmarks usually ask whether a model can produce a correct output for a bounded input. That remains useful, but agentic deployment shifts the unit of analysis. The deployed object is a system: a model combined with prompts, memory, retrieval, tools, permissions, validation logic, retry policies, human hand-offs and changing external state.

Research benchmarks have begun to reflect this shift. AgentBench evaluates language-model agents in interactive, multi-turn environments and identifies long-term reasoning, decision-making and instruction following as major obstacles (Liu et al., 2023a). GAIA and SWE-bench test assistants and coding agents on tasks that require browsing, tool use, long contexts and coordinated actions (Mialon et al., 2023; Jimenez et al., 2023). τ-bench evaluates tool-using agents in dynamic user interactions and explicitly measures reliability over repeated trials rather than treating one success as sufficient (Yao et al., 2024). Work on long-context models has separately shown that access to relevant information can degrade depending on where it appears in the context (Liu et al., 2023b).

These developments point in the same direction: the reliability of an interactive AI system cannot be inferred from a static capability score. However, most evaluations still report overall task completion, policy compliance or final database state. They do not always separate two failure classes that matter differently for governance:

• boundary failure: the system uses information it was not authorised to use; and
• preservation failure: the system omits information it was authorised and required to retain.

A system can pass the first test and fail the second.

2.2 Stateful integrity

This paper proposes “stateful integrity” as an evaluation property, not a new legal classification. A stateful AI system is one whose correct output or action depends on preserving, updating or excluding information across two or more interactions, stages or decisions.

Stateful integrity has four components:

1. preservation — required authorised state remains available when needed;
2. exclusion — prohibited, revoked or out-of-scope state is not used;
3. transition correctness — additions, updates, expiry and revocation are applied as instructed; and
4. traceability — the evidence shows what state was available, what changed and why the final action followed.

This property is distinct from factual accuracy, cybersecurity and privacy, although it interacts with all three. A workflow may produce a plausible answer while omitting a required identifier. It may respect confidentiality while losing the information necessary to act. It may also preserve information that should have expired. These are not merely “memory” errors in the colloquial sense. They are failures to maintain a state contract.

2.3 Why the distinction matters in strategic sectors

The distinction is operational in the sectors covered by the Apply AI Strategy. In public administration, case handling depends on retaining the correct authorised record while excluding information from another person or case. In healthcare administration, medication, consent and referral state may change across a workflow. In energy, manufacturing and transport, an agent may need to carry equipment status, authorisation limits and safety conditions across tools and shifts. In finance, a system may need to preserve customer, mandate and transaction state while enforcing segregation and revocation.

The harm pathways differ. Forbidden-state use can create confidentiality, rights and security risks. Required-state loss can cause delay, misrouting, duplicate work, unsafe omission, financial loss or an incorrect administrative action. A single combined success score obscures which control failed and which remedy is appropriate.

## 3. The European policy opening
The EU AI Act already supplies the legal and institutional hooks for a stateful evaluation protocol.

Article 9 requires a documented, continuous and iterative risk-management process for high-risk AI systems. It requires testing against prior-defined metrics and probabilistic thresholds appropriate to the intended purpose. Article 15 requires appropriate accuracy, robustness and cybersecurity throughout the lifecycle and directs the Commission, working with relevant stakeholders and benchmarking authorities, to encourage benchmarks and measurement methodologies. Article 72 requires active and systematic post-market monitoring of performance and compliance. For general-purpose AI models with systemic risk, Article 55 requires model evaluation using standardised protocols and tools reflecting the state of the art, including documented adversarial testing. Article 40 connects conformity with harmonised standards to a presumption of conformity where those standards cover the relevant requirements (European Union, 2024).

The Commission’s current standardisation programme is developing harmonised standards in ten areas, including risk management, record keeping, accuracy, robustness, quality management and conformity assessment. CEN and CENELEC are conducting this work through JTC 21 (European Commission, 2026a). The GPAI Code of Practice is also evidence that the Commission can use a voluntary, multi-stakeholder instrument to translate broad legal duties into operational practices before harmonised standards mature (European Commission, 2025c).

The gap is not a lack of authority to evaluate. It is a measurement specification. “Accuracy” and “robustness” do not automatically tell an evaluator how to test the integrity of state across a workflow. “Model evaluation” does not determine whether the unit of evaluation is the base model or the deployed system. “Post-market monitoring” does not specify how to detect required-state loss that produces a superficially plausible output.

SAEP would therefore be an implementation instrument. It would give deployers, providers, testing facilities and procuring authorities a common way to describe the state contract, build sequence-based cases, report orthogonal failure modes and preserve the evidence needed for review.

## 4. SFA-Bench R2: study design
4.1 Research question

The preregistered research question was:

How do public-state representation and an explicit retention reminder affect preservation of permitted identity state, particularly customer_id, without increasing forbidden-state use?

The study was classified as a preregistered balanced 2 × 2 permitted-state mechanism study. It tested one frozen memory-boundary task under one declared mutable provider alias. The evaluated system used no tools, no automatic retry, no replacement execution and one attempt per authorised slot. Sampling and reasoning used the provider defaults. The task, scoring mode, condition prompts and execution order were frozen before R2 provider responses were observed (Neal, 2026a; Neal, 2026b).

4.2 Conditions and allocation

The two factors were:

• public-state representation: prose or JSON; and
• explicit retention reminder: absent or present.

There were four conditions with 12 executions each:

• prose, no reminder;
• JSON, no reminder;
• prose, reminder; and
• JSON, reminder.

The 48 executions were arranged in 12 four-slot blocks. Each condition appeared three times in every ordinal position across the design. The sample size was selected for exact balance and operational feasibility, not as a formal power calculation.

4.3 Endpoints

The primary endpoint was complete permitted-state preservation: every required permitted field had to be preserved and no forbidden state could be used.

Secondary endpoints included:

• omission of customer_id, recorded as state loss;
• forbidden-state use, recorded as a boundary violation;
• deterministic score;
• refusal, malformed output and transport failure; and
• descriptive pooled contrasts for representation and reminder status.

The report specified two-sided 95% Wilson intervals for per-condition proportions. It explicitly prohibited null-hypothesis significance testing, pairwise model ranking, provider endorsement, certification and general model-performance claims.

4.4 Evidence governance

All 48 authorised executions were completed and separately ratified. The study retained the preregistration, slot plan, capture records, deterministic judgements, ratification records, closure specification, closure record, lineage record, descriptive report, evidence manifest and immutable snapshot record. The public release binds the evidence archive by filename, byte size and SHA-256 digest.

This governance structure matters to the policy argument. A benchmark score without a frozen plan, execution lineage and change history is difficult to audit. R2 treats the evidence chain as part of the result rather than as an optional repository detail.

## 5. Results
All 48 executions completed and were separately ratified. Thirty-six achieved complete permitted-state preservation. Twelve were partial outcomes caused by omission of customer_id. No refusal, malformed output, transport failure or forbidden-state use was observed.

The no-reminder conditions produced 12 complete outcomes in 24 executions. The reminder conditions produced 24 complete outcomes in 24 executions. The preregistered pooled reminder-minus-no-reminder difference was therefore +0.500000.

Across reminder status, prose produced 19 complete outcomes in 24 executions and JSON produced 17 in 24. The pooled JSON-minus-prose difference was −0.083333. The descriptive representation-by-reminder difference-in-differences was +0.166667. No significance test was performed.

The per-condition Wilson intervals are wide because each cell contains 12 observations. In particular, observing zero forbidden-state uses in a condition does not establish a zero underlying rate; the reported upper bound of the 95% Wilson interval was approximately 0.2425 for each 0/12 cell. The proper conclusion is “no forbidden-state use was observed in these executions,” not “the system cannot violate the boundary.”

### Table 1. Preregistered R2 results

| Condition | n | Complete preservation | 95% Wilson interval | customer_id loss | Forbidden-state use |
|---|---|---|---|---|---|
| Prose, no reminder | 12 | 7/12 (58.3%) | 31.95–80.67% | 5/12 | 0/12 |
| JSON, no reminder | 12 | 5/12 (41.7%) | 19.33–68.05% | 7/12 | 0/12 |
| Prose, reminder | 12 | 12/12 (100%) | 75.75–100% | 0/12 | 0/12 |
| JSON, reminder | 12 | 12/12 (100%) | 75.75–100% | 0/12 | 0/12 |
| Total | 48 | 36/48 (75.0%) | — | 12/48 | 0/48 |

## 6. Interpretation
6.1 Boundary compliance and workflow reliability are not the same claim

The most important result is the coexistence of perfect observed boundary compliance and incomplete task reliability. The system did not use forbidden state in any execution, yet it lost a required permitted identifier in 12 executions. A privacy-oriented assessment that reported only “no prohibited state used” would miss the operational failure. A task-success score would identify failure but not reveal that the boundary control remained intact.

Policy and assurance should therefore require both measures. They answer different questions and point to different controls.

6.2 Operational scaffolding is part of the evaluated system

The reminder result demonstrates why assurance must bind to the complete deployed configuration. In this task, the observed completion rate changed from 50% without reminders to 100% with reminders. The study does not establish that reminders are a universal solution. It establishes that an apparently small prompt-level control changed the result enough that a model-only reliability statement would be misleading.

A procurement dossier should therefore state whether the evaluated system used reminders, retrieval, external memory, validation, retries, tools, human confirmation and error recovery. A claim such as “Model X achieved 100%” is incomplete when the achieved rate depends on an undisclosed wrapper or control.

6.3 Structured representation is not a substitute for evidence

The preregistered representation hypothesis expected JSON to preserve required state at least as often as prose. The observed pooled result went in the opposite direction by 8.3 percentage points, driven by the no-reminder condition. This is not evidence that prose is generally superior. It is evidence against a policy shortcut: structured input should not be treated as presumptively reliable without task-specific testing.

The relevant regulatory object is the demonstrated system behaviour, not the aesthetic plausibility of the representation.

6.4 The result is a measurement demonstration, not a provider verdict

R2 used one task, one declared mutable alias, one execution period and 12 observations per condition. It did not test tools, long production trajectories, multiple providers or sectoral harms. It performed no significance test. The provider alias may change over time and is not an immutable identity attestation.

The study therefore supports a policy position about what should be measured. It does not support a general conclusion about the quality or safety of a provider or model family.

## 7. Proposed Stateful AI Evaluation Protocol
SAEP should define the minimum evidence required to make a reliability claim about a state-dependent workflow. It should be technology-neutral and proportionate to deployment risk. It should not prescribe a particular model, prompt format, memory store or agent framework.

7.1 A declared state contract

Before testing, the evaluator should define the state that the workflow is expected to manage. At minimum, each relevant field should be classified as:

• required and permitted — must be retained or retrieved for task completion;
• optional and permitted — may be used but is not required;
• forbidden — must not be used in the relevant decision;
• conditional — permitted only when a stated condition is met;
• derived — produced from authorised inputs under a documented rule; or
• expired or revoked — previously available but no longer valid.

The contract should also define the expected state transition after each material event. This prevents an evaluator from deciding after the run which omissions or uses “count.”

7.2 Sequence-based cases

Tests should represent the full workflow rather than a single prompt. Cases should include, where relevant:

• multiple turns or process stages;
• context switches and interruptions;
• tool calls and returned records;
• human hand-offs;
• corrections, revocation and expiry;
• conflicting or duplicated information;
• recovery after a failed step; and
• delayed use of information introduced earlier in the sequence.

The test length should reflect the deployment. A two-turn case is not evidence for a 40-step operational process.

7.3 Orthogonal outcome measures

At minimum, reports should separate:

1. required-state preservation;
2. forbidden-state exclusion;
3. transition correctness;
4. final-task correctness;
5. recovery and escalation behaviour; and
6. evidence completeness.

A combined pass may be reported, but the component outcomes must remain visible. This is essential because the same final failure can arise from very different mechanisms.

7.4 System configuration disclosure

The evaluated configuration should be recorded with sufficient precision to reproduce the assurance claim. The dossier should identify:

• model identifier and whether it is immutable or a mutable alias;
• system and user prompts;
• memory and retrieval architecture;
• state representation;
• tools and permissions;
• validation rules;
• retry and replacement policy;
• human intervention points;
• sampling and reasoning settings where available; and
• date, version and deployment environment.

Commercially sensitive material need not be made public. It must, however, be available to the appropriate evaluator or authority, and public claims should disclose which classes of controls were present.

7.5 Repeated trials and reliability distributions

One successful trajectory should not establish reliability. SAEP should require repeated trials, fixed stopping rules and outcome-independent ordering. Reports should show the distribution of failure modes and, where appropriate, reliability over repeated use. τ-bench’s use of repeated-trial metrics illustrates the value of measuring consistency rather than only first-pass success (Yao et al., 2024).

The number of trials should be proportionate, but the protocol should prevent cherry-picking, silent retries and replacement of failed runs.

7.6 Evidence chain and separated judgement

For higher-impact deployments, the evidence package should include:

• a preregistered plan or frozen evaluation specification;
• a canonical case and state schema;
• raw execution records;
• deterministic or documented scoring;
• human judgement where semantic assessment is unavoidable;
• separation between execution, judgement and approval where practicable;
• a closure record listing included and excluded runs;
• hashes or equivalent integrity controls; and
• a final report that states limitations and disallowed claims.

Independent evaluation is valuable, but independence is not binary. Where a fully external laboratory is not proportionate, separated roles, immutable records and transparent rules can still reduce discretion.

7.7 Change-triggered re-evaluation

A stateful evaluation should expire when material elements of the system change. Re-evaluation triggers should include:

• model or provider-alias change;
• prompt or policy change;
• memory or retrieval change;
• new tool or permission;
• altered retry or escalation logic;
• sectoral data change;
• a new serious incident or failure mode; or
• deployment in a materially different context.

This requirement aligns stateful evaluation with lifecycle risk management and post-market monitoring rather than treating the benchmark as a permanent certificate.

## 8. Commission implementation pathway
8.1 Convene an Apply AI Alliance working group

The Commission should convene a time-limited technical working group under the Apply AI Alliance with representation from strategic-sector deployers, SMEs, public procurers, AI providers, testing laboratories, civil society, metrology and benchmarking experts, and CEN-CENELEC JTC 21 participants.

The first deliverable should be a common vocabulary and a draft SAEP core profile. The group should distinguish stateful integrity from privacy, factual accuracy, cybersecurity and general task completion, while mapping overlaps with existing AI Act requirements.

8.2 Pilot through testing facilities and regulatory sandboxes

The core profile should be tested in at least three materially different settings:

• a public-sector case-management workflow;
• a regulated or safety-relevant sector such as healthcare, finance, energy or transport; and
• a tool-using enterprise agent performing a long-horizon operational task.

AI Testing and Experimentation Facilities and regulatory sandboxes are appropriate venues because they can combine technical evaluation with deployment context. The pilot should publish reusable case templates, failure taxonomies and reporting schemas, while allowing confidential evidence handling.

8.3 Introduce a public-procurement evidence clause

Public-sector procurement can create demand for better evidence before harmonised standards are complete. The Commission should develop a model clause requiring suppliers of state-dependent AI systems to provide a deployment-specific evaluation dossier.

The clause should not require a perfect score. It should require disclosure of failure rates, failure classes, controls, residual risks, change triggers and monitoring. Procurers need evidence for a decision, not a marketing certificate.

8.4 Feed results into European standardisation

The pilot should be formally transmitted into the standardisation work on risk management, record keeping, accuracy, robustness, quality management and conformity assessment. Stateful integrity is cross-cutting: it concerns what the system must remember, what it must reject, how behaviour is recorded and how consistent operation is demonstrated.

Article 15(2) is a particularly direct route because it calls for benchmarks and measurement methodologies for accuracy, robustness and other relevant performance metrics. Article 40 supplies the path by which mature requirements may support harmonised standards and legal certainty.

8.5 Track sectoral evidence through the AI Observatory

The AI Observatory should track anonymised stateful failure modes across sectors. Useful indicators would include required-state loss, forbidden-state use, incorrect revocation, unrecovered tool-state divergence and the proportion of deployments with change-triggered re-evaluation.

The purpose should be learning, not a public provider ranking. Aggregated failure data can identify where sector guidance, standards or technical support are needed.

### Table 2. Proposed implementation roadmap

| Period | Action | Deliverable |
|---|---|---|
| 0–6 months | Apply AI Alliance working group | Vocabulary, state-contract schema, core SAEP draft, confidentiality model |
| 6–12 months | Open reference implementation | Evaluation harness, reporting schema, reusable sequence cases, SME guidance |
| 12–18 months | Sector pilots | Public sector plus two strategic-sector pilots through TEFs or sandboxes |
| 18–24 months | Procurement and standards pathway | Model procurement clause; submission to JTC 21 workstreams |
| Ongoing | AI Observatory and post-market learning | Anonymised failure taxonomy, change-triggered re-evaluation indicators |

## 9. Proportionality, SMEs and confidential evidence
A serious evaluation regime can become counterproductive if it demands laboratory-scale evidence from every small deployment. SAEP should therefore use proportionate profiles rather than one universal burden.

Low-impact internal systems may use a concise state contract, a small sequence suite and documented change control. Systems affecting access to services, money, employment, health, safety or legal position should require larger and more representative case sets, separated judgement and formal monitoring. High-risk systems and systemic-risk GPAI obligations remain governed by the AI Act; SAEP should support, not replace, those legal classifications.

To reduce costs, the Commission should fund an open reference harness, common schemas and example sector cases. SMEs should be able to access testing support through European Digital Innovation Hubs, AI Testing and Experimentation Facilities and sandboxes. Evidence should be reusable across procurement and conformity processes where the system and deployment remain materially unchanged.

Confidentiality can be protected without abandoning auditability. Raw prompts, logs and business rules may remain in a controlled evidence room. Public reports can disclose methods, aggregate results, version bindings and cryptographic digests. Authorities and accredited evaluators can receive the more detailed record under applicable confidentiality protections.

## 10. Limitations and research agenda
The empirical study reported here is intentionally narrow. It evaluates one frozen task under one mutable provider alias, with 12 executions per condition. It does not establish a statistically significant treatment effect, universal benefit from reminders or general provider performance. It does not test external tools, memory stores, long production trajectories, adversarial users or sector-specific harms. No observed forbidden-state use does not establish absence of risk.

The next research phase should extend the state contract beyond retention of one required identifier. Priority cases include:

• permission changes and revocation;
• temporal expiry;
• conflicting records;
• role-based access;
• human correction and override;
• state carried across tool calls;
• state compression and summarisation;
• cross-session retrieval;
• recovery after interrupted execution; and
• deployment drift after model or wrapper updates.

Replication should include multiple model families, immutable model versions where available, different agent frameworks, longer horizons and independent evaluators. Sector pilots should define harm-relevant thresholds rather than relying only on generic benchmark scores.

These limitations do not weaken the policy need. They define it. Europe should not wait for one benchmark to become universal. It should establish the measurement discipline that allows many task- and sector-specific evaluations to be compared, audited and improved.

## 11. Conclusion
Europe is moving from AI experimentation to strategic-sector adoption. That transition changes what must be proven. A model’s ability to answer a question is not evidence that a deployed system can preserve the right information, exclude the wrong information and maintain those distinctions across a workflow.

SFA-Bench R2 offers a bounded demonstration. The system showed no forbidden-state use in 48 executions, yet lost required permitted state in 12. A retention reminder changed observed complete preservation from 12/24 to 24/24, while representation format had a much smaller descriptive effect. The finding is not a provider verdict. It is evidence that system configuration and state integrity must be visible in the assurance claim.

The Commission does not need to prescribe a reminder, a prompt style or a memory architecture. It should require evidence: a state contract, sequence-based cases, separate preservation and exclusion metrics, repeated trials, configuration disclosure, change-triggered re-evaluation and an auditable chain from preregistration to closure.

The Apply AI Alliance is the right forum to begin. A Stateful AI Evaluation Protocol would give Europe a practical bridge between trustworthy-AI principles and deployed-system evidence. The objective is not another leaderboard. It is to establish what it means for an AI system to carry obligations through time.

## Declarations
Author contribution. Matthew Neal conceived the policy question, designed and operated the SFA-Bench R2 study, governed the evidence closure and publication process, interpreted the findings and approved this paper.

Funding. This paper is an independent SFA-Bench policy contribution. No external funding is declared.

Competing interests. None declared. The paper makes no provider endorsement, ranking, certification, legal approval or regulatory approval claim.

AI-assisted drafting. A generative AI assistant was used for editorial drafting, source organisation and document preparation under the author’s direction. The author remains responsible for the argument, evidence selection, accuracy and final approval.

Legal status. This is a stakeholder policy contribution for the Apply AI Alliance. It is not legal advice, a conformity assessment or a claim of compliance with Regulation (EU) 2024/1689.

## Data and evidence availability
The complete publication package is available in the SFA-Bench repository under publications/openai-gpt56-sol-memory-boundary-r2. The immutable evidence archive is attached to the GitHub release gpt56-sol-memory-boundary-r2-2026-07.

Repository binding: 972ad7ef838dde49601f0b093fbbbc4b6c3d8c82
Publication merge commit: c3e766f6db63857bed6fa84ffbfd503570dbeac3
Evidence archive SHA-256: 336d244a4865c6b88c52a89fddecba177f681dab26e40d0d9b7f336f1dd8e1c6
Evidence archive size: 1,020,719 bytes

## References

- **European Commission (2025a).** Apply AI Strategy. Shaping Europe’s digital future, 8 October 2025. https://digital-strategy.ec.europa.eu/en/policies/apply-ai
- **European Commission (2025b).** Apply AI Alliance. Shaping Europe’s digital future. https://digital-strategy.ec.europa.eu/en/policies/european-ai-alliance
- **European Commission (2025c).** The General-Purpose AI Code of Practice. https://digital-strategy.ec.europa.eu/en/policies/contents-code-gpai
- **European Commission (2026a).** Standardisation of the AI Act. https://digital-strategy.ec.europa.eu/en/policies/ai-act-standardisation
- **European Union (2024).** Regulation (EU) 2024/1689 of the European Parliament and of the Council of 13 June 2024 laying down harmonised rules on artificial intelligence (Artificial Intelligence Act). https://eur-lex.europa.eu/eli/reg/2024/1689/oj
- **Jimenez, C. E., Yang, J., Wettig, A., Yao, S., Pei, K., Press, O. and Narasimhan, K. (2023).** SWE-bench: Can Language Models Resolve Real-World GitHub Issues? arXiv:2310.06770. https://arxiv.org/abs/2310.06770
- **Liu, N. F., Lin, K., Hewitt, J., Paranjape, A., Bevilacqua, M., Petroni, F. and Liang, P. (2023b).** Lost in the Middle: How Language Models Use Long Contexts. arXiv:2307.03172. https://arxiv.org/abs/2307.03172
- **Liu, X. et al. (2023a).** AgentBench: Evaluating LLMs as Agents. arXiv:2308.03688. https://arxiv.org/abs/2308.03688
- **Mialon, G., Fourrier, C., Swift, C., Wolf, T., LeCun, Y. and Scialom, T. (2023).** GAIA: A Benchmark for General AI Assistants. arXiv:2311.12983. https://arxiv.org/abs/2311.12983
- **National Institute of Standards and Technology (2024).** Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile. NIST AI 600-1. https://doi.org/10.6028/NIST.AI.600-1
- **Neal, M. (2026a).** SFA-Bench R2 preregistration: openai-gpt56-sol-memory-boundary-r2. https://github.com/iotaverbum-core/sfa-bench/tree/main/publications/openai-gpt56-sol-memory-boundary-r2
- **Neal, M. (2026b).** SFA-Bench R2 preregistered descriptive report and immutable evidence release. https://github.com/iotaverbum-core/sfa-bench/releases/tag/gpt56-sol-memory-boundary-r2-2026-07
- **Nolte, H., Rateike, M. and Finck, M. (2025).** Robustness and Cybersecurity in the EU Artificial Intelligence Act. arXiv:2502.16184. https://arxiv.org/abs/2502.16184
- **Yao, S., Shinn, N., Razavi, P. and Narasimhan, K. (2024).** τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains. arXiv:2406.12045. https://arxiv.org/abs/2406.12045

## Appendix A. Minimum Stateful Evaluation Dossier

| Component | Minimum content |
|---|---|
| Scope | Intended purpose, users, affected persons, sector, workflow boundaries |
| State contract | Required, optional, forbidden, conditional, derived, expired and revoked fields |
| System binding | Model/version or alias, prompts, memory, retrieval, tools, permissions, retries, human controls |
| Test design | Sequence cases, repetitions, fixed stopping rule, ordering, deployment-relevant conditions |
| Outcomes | Preservation, exclusion, transition correctness, final-task correctness, recovery and escalation |
| Evidence | Raw records, scoring, judgement, ratification or approval, closure, integrity hashes |
| Limitations | Generalisation limits, uncertainty, untested conditions and disallowed claims |
| Lifecycle | Expiry date, change triggers, post-market monitoring and incident-driven re-evaluation |

## Appendix B. Apply AI Alliance submission metadata
Suggested Apply AI Alliance title:
From Boundary Compliance to Stateful Integrity: A Policy Standard for Evaluating Stateful and Agentic AI in Europe

Suggested platform summary:
Europe’s AI adoption strategy requires evidence that systems remain reliable across real workflows, not only that models answer benchmark questions. This paper reports a preregistered 48-execution study in which a frontier language-model system used no forbidden state but lost a required permitted identifier in 12 executions. An explicit retention reminder changed observed complete preservation from 12/24 to 24/24, while representation format had a much smaller descriptive effect. The result is task-specific and does not support a provider-level safety or performance claim. It demonstrates a measurement gap: boundary compliance and required-state preservation are distinct properties, and both must be evaluated.

The paper proposes a Stateful AI Evaluation Protocol for the Apply AI Alliance. It recommends a declared state contract, sequence-based tests, separate preservation and exclusion metrics, system-configuration disclosure, repeated trials, immutable evidence records and change-triggered re-evaluation. The Commission should pilot the protocol through AI Testing and Experimentation Facilities, regulatory sandboxes and public procurement, then feed the results into CEN-CENELEC JTC 21 standardisation work.

Suggested tags:
AI evaluation; agentic AI; AI Act; robustness; public procurement; strategic sectors; standardisation; post-market monitoring; trustworthy AI.
