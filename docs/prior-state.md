# Prior State

Prior State is the project's lightweight run-start reminder: before beginning a
release gate, name the previous procedural failure, the correction, and the rule
that prevents recurrence.

See [Prior State Memory: Why AI Needs Memory Before the Next Mistake](prior-state-memory.md)
for the public conceptual framing of Prior State.

## Recorded release lesson

Earlier release runs created new implementation files but left them untracked.
The acceptance summary appeared clean because it relied on:

```bash
git diff --name-only
```

That command reports tracked-file changes; it does not report untracked files.
The required release inspection is:

```bash
git status --short --untracked-files=all
```

The check is required before staging, after staging, and immediately before
release clearance. New implementation files must be staged before the release
gate can pass.

The general engineering rule is that a release gate must inspect the invisible
failure path, not only repeat tests that already pass. Automated checks should
encode known procedural failures so the same omission cannot produce another
false-green summary.

`release_gate.py` implements this discipline at repository level. It explicitly
reports whether untracked files remain and fails release clearance when they do.
`git diff --name-only` remains useful for reviewing tracked edits, but it is never
used as sufficient evidence of a clean release state.

## Recorded version-of-record lesson

A second invisible failure path is a stale version of record. The package version
in `sfa/__init__.py` was left at `0.9.0` while the README, changelog, command
headers, and the release gate's `EXPECTED_RELEASE` all declared `v1.0.0`. Every
test and the release gate stayed green because nothing compared the package's
declared version against the release.

The same rule applies: a release gate must inspect the invisible inconsistency,
not only repeat passing tests. `release_gate.py` now reads `sfa.__version__` and
fails when `v{__version__}` does not equal `EXPECTED_RELEASE`, and it requires
every command header to declare that same release. `invariant_suite.py` re-checks
the same consistency through `assert_repository_version_consistency`, so the drift
is caught on the offline CI path as well as at the gate. The package version is
the single machine-readable source of truth for the release; the gate and the
invariant make any divergence fail closed instead of producing another
false-green summary.
