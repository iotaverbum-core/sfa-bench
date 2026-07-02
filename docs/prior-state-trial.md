# Prior State Trial

A controlled measurement of whether a **matured lesson** ("prior") injected into
the proposer actually improves outcomes — scored entirely by the deterministic
SFA verifier. It operationalizes the Prior State thesis: a system may learn from
failure, but the benefit must be real, not laundered.

## Arms

- **`true_prior`** — the matured lesson matching the task's failure family (the
  real generator-side directive from `sfa.policy.DIRECTIVES`).
- **`placebo_prior`** — a length- and format-matched, content-irrelevant lesson
  drawn from an *unrelated* family. Same shape and size, wrong content.
- **`baseline`** — no prior.

The **headline** result is `true_prior − placebo_prior`. Beating the baseline is
not enough: a lesson must beat a matched-but-irrelevant control to show its
*content* (not its mere presence) caused the improvement.

## Invariants

- **Proposer ≠ verifier.** The prior only shapes the proposer's candidate. Every
  score is `verifier.verify(input, evidence, candidate, rules)` — a pure
  deterministic function. No proposer output participates in a verdict. (The
  repository call-site guard enforces that the verifier receives no
  prior/policy/model metadata.)
- **Deterministic replay.** All randomness is derived from one integer `seed` via
  SHA-256, so `run_trial(config)` is a pure function of `config`. No wall-clock
  time enters the sealed report. `replay <report>` re-derives it byte-for-byte.
- **Offline by default.** The `stub` proposer makes no model or network call. A
  live model runs only behind the CLI `--live` flag with a user-supplied adapter
  and key, and never in CI.

## Metrics (stated exactly)

For arm `a` over `n` sampled tasks, let `s_a[i] ∈ {0, 1}` be the verifier score of
sample `i` (`1` iff `PASS`).

- **Per-arm mean:** `mean(a) = (1/n) · Σ_i s_a[i]`.
- **Win/Loss/Draw** of arm `a` vs `b`: for each `i`, win if `s_a[i] > s_b[i]`,
  loss if `<`, draw if `=`.
- **Headline paired delta:** `δ[i] = s_true[i] − s_placebo[i]`;
  `Δ = (1/n) · Σ_i δ[i] = mean(true) − mean(placebo)`.
- **Bootstrap 95% CI on Δ** (fixed `bootstrap_seed`): for `B` resamples, draw `n`
  indices with replacement (indices from `SHA-256(seed, "bootstrap", b, i)`),
  compute the resample mean of `δ`; the CI is the empirical 2.5th and 97.5th
  percentiles of the `B` means. `significant = ci_low > 0`.

Default `n = 30`, `B = 2000`.

## The stub proposer (illustrative)

By default the proposer is `stub-prior-model-v0`. For sample `i` in arm `a` it
draws `u = SHA-256(seed, "propose", task_id, a, i) / 2^64` and returns the
*corrected* candidate iff `u < p(a)`, else the *flawed* candidate, where
`p(true_prior) = 0.85` and `p(placebo_prior) = p(baseline) = 0.25`. The verifier
then scores the returned candidate.

This is a **mechanism model**, like the fingerprint fixture model ids — it makes
the harness, metric, and replay deterministically testable. It is **not** a claim
about any real model. Point `--live` at a real model (your adapter + key) to
measure reality; the harness and metrics are unchanged.

## Sealed report schema (`sfa.prior_state_trial.v1`)

```
{
  "schema": "sfa.prior_state_trial.v1",
  "config": { model_id, seed, n, arms, bootstrap, pool_size,
              stub_probabilities, task_pool_hash, sampled_task_hash },
  "arms":   { <arm>: { n, passes, mean_score } },
  "comparisons": { "<a>_vs_<b>": { win, loss, draw } },
  "headline": { metric, comparator, delta_mean, ci95_low, ci95_high,
                bootstrap_samples, bootstrap_seed, significant },
  "runs":   [ { seq, arm, index, task_id, prior_id, prior_hash,
                candidate_hash, status, category, family, score,
                verdict_hash, prev_hash, entry_hash } ],   # hash-chained
  "runs_root_hash": "<last entry_hash>",
  "report_sha": "<sha256 of the report minus report_sha>"
}
```

Each run is chained (`prev_hash`/`entry_hash`) like the occurrence ledger, so a
sealed report is append-only and tamper-evident; `report_sha` seals the whole.

## CLI

```bash
python prior_state_trial.py                                 # stub dry-run + determinism + replay checks
python prior_state_trial.py --n 30 --arms true,placebo,baseline --out report.json
python prior_state_trial.py replay report.json              # offline deterministic replay
python prior_state_trial.py --model <id> --live             # user-supplied live adapter (never in CI)
```

`--live` fails closed: no provider is bundled, so a live run requires a
user-supplied model adapter and key. CI and `verify_all.py` only ever run the
offline stub.
