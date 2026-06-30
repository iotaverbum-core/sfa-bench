# GroundLedger Audit Pilot

**Prove your AI didn't make it up - in two weeks, on your own answers.**

## The problem

Your assistant answers customer and policy questions from documents. Sometimes it
cites a clause that isn't there, or states a number the source contradicts. You
find out when a customer complains - or when a prospect's security team asks how
you prevent and *evidence* it. Your evals can't help: they run a model to grade a
model, the score moves run to run, and no auditor accepts it.

## The pilot

A two-week, fixed-scope engagement that runs deterministic groundedness checks on
your assistant's real answers and produces a tamper-evident report your buyer's
security team can reproduce. It runs in your environment - no documents leave your
walls, no model calls, no network egress.

## What we analyse

- **Fabricated citations** - answers citing source ids not present in the evidence.
- **Contradictions** - a stated rate, fee, deductible, or date that disagrees with the source.
- **Unverifiable answers** - missing citations/claims that make grounding impossible to check.
- **A reproducible groundedness rate** across your real answers, sealed into a tamper-evident ledger.

*Honest scope: free-text checks are deterministic and conservative (they flag
fabricated citations and contradictions on evidence-covered facts and under-report
novel claims); structured, cited answers get the strongest coverage. Tamper-evident,
not tamper-proof; no compliance certification is claimed.*

## What you receive

- A one-page executive summary (groundedness rate + headline risk).
- Severity-ranked findings (critical / high / medium) with recommended actions.
- The evidence behind each finding (sealed receipt + the source it failed against).
- A signed, self-verifying audit bundle your auditor re-runs offline in one command.
- A monitoring recommendation and a subscription proposal.

## Ideal customer

Head of AI / founding engineer at a 20-150 person insurance or fintech company
shipping a document-grounded assistant into regulated buyers, with a deal slowed
by AI-risk review.

## Price

**$2,500 fixed** (design-partner rate **$1,500** for the first three customers),
credited toward your first 3 months if you continue.

## Timeline

**2 weeks.** Start within a day of the discovery call once you share ~150-300 real
answers and the evidence each used.

## Next step

Book a 20-minute pilot call: **{{BOOKING_LINK}}**  ·  **{{FOUNDER_EMAIL}}**
