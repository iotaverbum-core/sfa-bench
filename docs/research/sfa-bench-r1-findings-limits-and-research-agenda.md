# SFA-Bench R1: Findings, Limits, and Research Agenda

*A short public note on the first preregistered GPT-5.6 memory-boundary replication.*

## R1 in one sentence

> Across 30 preregistered and ratified executions of one frozen memory-boundary task, 10 passed and 20 produced partial results caused by loss of permitted state; no execution used forbidden state.

## 1. The result in plain English

The test asked an AI to carry a small set of permitted facts through a task while refusing to use information outside the permitted boundary. The models therefore had to do two things at once: remember what they were allowed to remember, and leave everything else alone.

All 30 executions respected the forbidden-state boundary. The recurring failure was different: the model sometimes dropped the permitted customer identifier while retaining the other allowed fields. SFA-Bench classifies that outcome as `state_loss`.

In ordinary language: **the models stayed inside the fence, but two-thirds of the executions failed to carry every required item through the gate.**

## 2. Technical result

The primary endpoint was the pass proportion among completed, ratified deterministic judgments for each declared model alias. Intervals are two-sided 95% Wilson intervals.

| Declared model alias | Completed / ratified | Pass | Pass 95% CI | State loss | Mean score |
|---|---:|---:|---:|---:|---:|
| `gpt-5.6-sol` | 10 / 10 | 5 / 10 (50.0%) | 23.7%–76.3% | 5 / 10 (50.0%) | 0.833334 |
| `gpt-5.6-terra` | 10 / 10 | 0 / 10 (0.0%) | 0.0%–27.8% | 10 / 10 (100.0%) | 0.666667 |
| `gpt-5.6-luna` | 10 / 10 | 5 / 10 (50.0%) | 23.7%–76.3% | 5 / 10 (50.0%) | 0.833334 |
| **Overall** | **30 / 30** | **10 / 30 (33.3%)** | — | **20 / 30 (66.7%)** | **0.777778** |

Observed deterministic outcomes:

- 10 pass
- 20 partial with `state_loss`
- 0 other detected failure modes

The three pilot executions are excluded from these estimates.

## 3. Why this matters operationally

Real systems need both boundary discipline and continuity. A system can protect restricted information yet still be unsafe or unusable if it forgets a permitted identifier, instruction, or constraint midway through a workflow.

### Customer service and bookings

Losing an account, order, passenger, or booking identifier can attach later actions to the wrong case or force the workflow to restart.

### Banking and payments

Dropping permitted transaction state can cause incorrect routing, duplicate handling, or advice detached from the customer’s actual product.

### Healthcare and public services

Losing a permitted patient or case identifier can break continuity even when the system correctly refuses unrelated private data.

### High-risk operations

Aviation, infrastructure, and industrial systems cannot treat privacy compliance as a substitute for reliable state retention. Both properties must be demonstrated in the deployed system.

## 4. What cannot be inferred

R1 does **not** establish any of the following:

- general intelligence or overall model quality;
- fitness for a particular industry or high-risk application;
- that one tier is generally better than another;
- a pairwise statistical ranking between model aliases;
- a universal failure rate;
- that the mutable aliases represent immutable model snapshots;
- safety certification, legal approval, regulatory approval, or product endorsement;
- sponsorship, review, certification, or endorsement by OpenAI.

The result describes one frozen task and 30 executions. It is evidence of a repeatable operational failure mode, not a general verdict on any model family.

## 5. Lessons from the audit workflow

### Evidence must outrank interface messages

A printed success banner is not proof. Completion was accepted only after filesystem records, counts, and hashes were independently verified.

### Authority must remain separated

Execution authorization, deterministic judgment, human ratification, campaign closure, preservation, and publication were recorded as different actions.

### Immutable records make correction possible

When wrapper scripts failed, the underlying captures and ratifications remained intact and could be rechecked without rerunning the models.

### Governance tooling also needs tests

Array handling, interrupted console pastes, and release verification exposed ordinary software defects. A benchmark is only as trustworthy as the machinery that records it.

### Preservation must be independently verifiable

The 773-file evidence snapshot was manifested, archived, uploaded, downloaded again, and verified against its published SHA-256.

## 6. Proposed R2 research question

> Under which controlled instruction and representation conditions can an AI preserve permitted identity state—especially `customer_id`—across a workflow without increasing use of forbidden state?

R2 should vary one factor at a time, including:

- prose instructions versus structured schemas;
- field ordering;
- explicit reminders;
- conversation length;
- distractor information;
- the number of permitted fields.

R2 must be preregistered as a new campaign rather than appended to R1 after the result is known.

## 7. Invitation for independent replication

Researchers, engineers, auditors, and governance teams are invited to reproduce the protocol, verify the published hashes and calculations, and run a separately identified replication without modifying the R1 record.

A useful independent replication should disclose:

- model identifier or immutable snapshot, where available;
- provider and execution date;
- deviations from the frozen protocol;
- attempt and retry policy;
- raw completion counts;
- deterministic judgments;
- human review process;
- complete evidence hashes.

Independent replications should preserve their own evidence and should not be represented as extensions of the original R1 dataset.

## Public record

- Repository: `iotaverbum-core/sfa-bench`
- Publication package: [`publications/openai-gpt56-memory-boundary-replication-r1`](../../publications/openai-gpt56-memory-boundary-replication-r1/README.md)
- Release tag: `gpt56-memory-boundary-replication-r1-2026-07`
- Evidence archive SHA-256: `41a8b5f532c530a9b0fc8723e82c429073167ae51af54a9426d9c535d92027ae`

---

*Independent research note: OpenAI did not sponsor, review, certify, or endorse this study.*
