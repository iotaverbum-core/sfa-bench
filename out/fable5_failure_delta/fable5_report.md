# Claude Fable 5 Frontier Delta Report (8 cases)

blind_task_prompt_only = true
candidate_only_no_valid_delta_yet = true

model_under_test: `claude-fable-5`
generated_at: `2026-07-03T19:40:39.9669877+00:00`
selected_cases: `audit_replayability_001`, `contradiction_recovery_001`, `grounding_integrity_001`, `memory_boundary_001`, `open_ended_adaptation_001`, `paradigm_shift_001`, `planning_drift_001`, `tool_false_completion_001`

## Scope

This is a candidate-only run on 8 selected frozen Frontier Delta case(s). It is not a general intelligence claim about Claude Fable 5.

The GPT-5.5 baseline present in this repository is fixture-based, not a live GPT-5.5 API run. Therefore no valid behavioural delta is claimed here.

total_score_on_selected_cases: 0.771    verdicts: {'pass': 5, 'partial': 2, 'fail': 1}

## Results

| task_id | lane | score | verdict | detected_failure_modes |
| --- | --- | ---: | --- | --- |
| `audit_replayability_001` | `audit_replayability` | 0.000 | `fail` | unreplayable_audit, incomplete_trail |
| `contradiction_recovery_001` | `contradiction_recovery` | 1.000 | `pass` | - |
| `grounding_integrity_001` | `grounding_integrity` | 1.000 | `pass` | - |
| `memory_boundary_001` | `memory_state_boundary` | 0.667 | `partial` | state_loss |
| `open_ended_adaptation_001` | `open_ended_adaptation` | 1.000 | `pass` | - |
| `paradigm_shift_001` | `paradigm_shift_recognition` | 1.000 | `pass` | - |
| `planning_drift_001` | `long_horizon_planning_drift` | 1.000 | `pass` | - |
| `tool_false_completion_001` | `tool_use_false_completion` | 0.500 | `partial` | missing_evidence |

## Failure Modes

- `incomplete_trail`: 1
- `missing_evidence`: 1
- `state_loss`: 1
- `unreplayable_audit`: 1

## Replay

- Raw API outputs were saved before local scoring.
- Candidate prompts used only the whitelisted public task fields.
- Replay manifest includes SHA-256 hashes for each blinded prompt, raw response, and task file.
- The frozen Frontier Delta task files and scorer implementation were not modified by this harness.
