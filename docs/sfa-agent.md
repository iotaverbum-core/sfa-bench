# SFA-Agent v0.5

SFA-Agent is a minimal proof of concept that places SFA-Bench around a
swappable model adapter. It is not an agent framework.

The loop is intentionally small:

1. Accept a task, an evidence pack, and a model adapter.
2. Ask the adapter for a `candidate_answer.json`-compatible object.
3. Run the existing deterministic verifier.
4. Return the answer immediately on `PASS`.
5. On `FAIL`, seal the failure artifact, append the occurrence ledger, query
   prior failures in the same family, write a short warning, and retry once.
6. Preserve both attempts in `agent_runs/<run_id>/`.

The verifier is unchanged. It receives only the task input, evidence, candidate,
and verifier rules. It never receives the warning and never reads gold labels.
v0.5 also writes provenance for every attempt, but provenance remains outside
the verifier boundary.

## Demo

Run:

```bash
python agent_demo.py
```

The demo uses `DeterministicFakeAdapter`, which makes no network calls and has
no LLM dependency. The first candidate contradicts the evidence. The agent seals
that failed attempt, appends the occurrence ledger, generates a warning from the
same failure family, and retries once. The second candidate uses the evidence
value and passes.

Each run writes append-only records:

```text
agent_runs/<run_id>/
  attempt_001_raw_source.json
  attempt_001_candidate.json
  attempt_001_provenance.json
  attempt_001_verdict.json
  attempt_001_warning.json
  attempt_001_failure_artifact.json
  attempt_002_raw_source.json
  attempt_002_candidate.json
  attempt_002_provenance.json
  attempt_002_verdict.json
  summary.json
```

Existing run folders are never rewritten. If a `run_id` already exists, the run
fails instead of overwriting records.

## Boundaries

- No network calls.
- No real LLM adapter yet.
- No hidden repair.
- No mutation of sealed artifacts.
- No mutation of previous run records.
- The warning is input to the next adapter call only.
- The verifier remains deterministic and warning-blind.
- Provenance and adapter metadata are never verifier inputs.
