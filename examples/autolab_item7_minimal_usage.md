# AutoLab Item 7 Minimal PowerShell Flow

This flow starts from the released `fz-v0.7.0` state, creates a candidate branch,
makes a non-frozen documentation change, verifies the repository, commits, and
records the candidate SHA.

```powershell
# 1. Fetch the release tag and verify the released state.
git fetch origin --tags
git switch --detach fz-v0.7.0
py -3 verify_all.py
py -3 release_gate.py --ci
py -3 frozen_zone_check.py --ci

# 2. Create the candidate branch from current main.
git switch -c candidate/item-8-docs-example origin/main

# 3. Make a non-frozen change. Keep candidate edits outside autolab/, sfa/,
# frozen_zone_check.py, release_gate.py, invariant_suite.py, and holdout/.
New-Item -ItemType Directory -Force docs | Out-Null
Set-Content -Path docs/item8_candidate_note.md `
  -Value "# Item 8 Candidate Note`n`nThis is a non-frozen documentation candidate."

# 4. Verify again before committing.
py -3 verify_all.py
py -3 release_gate.py --ci
py -3 frozen_zone_check.py --ci --base origin/main

# 5. Confirm that only allowed files changed.
git diff --name-only

# 6. Commit and record the candidate SHA.
git add docs/item8_candidate_note.md
git commit -m "Docs: add Item 8 candidate note"
git rev-parse HEAD
```

Record the final SHA from `git rev-parse HEAD` in the PR body or candidate
checkpoint notes.
