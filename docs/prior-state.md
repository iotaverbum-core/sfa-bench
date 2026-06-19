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
