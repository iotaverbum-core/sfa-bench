# Alpha.2 Release-Preparation Checklist

This checklist does not authorize a merge, tag, release, or frozen amendment.

## Implementation acceptance

- [ ] All required lifecycle transitions and interruption branches pass.
- [ ] Synthetic valid, invalid, timeout, error, partial, binary, metadata, and
      credential cases pass without network or credentials.
- [ ] Exact request/response bytes round-trip and tamper tests pass.
- [ ] Duplicate execution/attempt and concurrent ledger collisions fail closed.
- [ ] Capture, judgment, and review artifacts verify independently.
- [ ] Review bundle is secret-free, excludes raw bodies, and is unratified.
- [ ] Alpha.1 valid-output scores, verdicts, canonical forms, and protected
      result hashes remain unchanged.

## Repository acceptance

- [ ] Focused and full test discovery pass.
- [ ] `campaign_capture_check.py` passes at committed `HEAD`.
- [ ] `verify_all.py`, release gate, and frozen-zone gate pass.
- [ ] Windows/Linux CI definitions remain offline and credential-free.
- [ ] Product tests, demo, reproducibility, and offline wheel build pass.
- [ ] LF and `core.autocrlf=true` clean-clone reproductions pass.
- [ ] Five independent reviewer areas have findings and dispositions.
- [ ] Claims and unsupported-claims wording is complete.

## Human-authorized release preparation

- [ ] A human supplies the frozen-zone amendment token matching a new amendment
      record and sealed zone transition.
- [ ] In one distinct commit, align `sfa.__version__` to `2.0.0a2`, public text
      to `v2.0.0-alpha.2`, frozen release-gate expectation, command headers,
      `README.md`, `CHANGELOG.md`, and `CITATION.cff`.
- [ ] Re-run every acceptance check and audit `origin/main...HEAD`.

Human-only after this task: create/push the PR branch, create the PR, merge,
create the tag, publish the GitHub Release, authorize a real provider campaign,
and later ratify or reject evidence.
