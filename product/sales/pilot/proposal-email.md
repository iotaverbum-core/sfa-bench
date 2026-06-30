# Paid pilot proposal email

Send within an hour of a good call, while it's warm. Keep it skimmable.

Placeholders: `{{FIRST}}` `{{COMPANY}}` `{{ASSISTANT}}` `{{DEAL_OR_REVIEW}}`
`{{RULE_PACK}}` `{{START_DATE}}` `{{FOUNDER_NAME}}` `{{PAYMENT_LINK}}`.

---

**Subject:** GroundLedger pilot - scope + next step

Hi {{FIRST}},

Thanks for the time today - good conversation. Quick recap and a concrete proposal.

**The problem we're solving:** {{COMPANY}}'s assistant ({{ASSISTANT}}) answers from
documents, and you need to *prove* - to {{DEAL_OR_REVIEW}} - that those answers are
grounded and that the record can't be quietly changed. Your current evals can't be
reproduced or handed to an auditor.

**What I recommend: the 2-week Groundedness Audit Pilot.**

- **Scope:** one assistant, the `{{RULE_PACK}}` rule pack tuned for your domain, on
  ~150-300 of your real answers.
- **We check:** fabricated citations, contradictions against your evidence,
  unverifiable answers, and a reproducible groundedness rate - all sealed into a
  tamper-evident ledger.
- **You receive:** a one-page executive summary, severity-ranked findings with
  recommended fixes, the evidence behind each, a signed audit bundle your auditor
  re-runs offline, and a monitoring proposal.
- **Where it runs:** inside your environment (in-VPC Docker or our Python SDK). No
  documents leave; no model or network calls.

**Timeline:** 2 weeks from kickoff. Start {{START_DATE}} once I have ~200 answers +
their evidence.

**Price:** $1,500 (design-partner rate), credited toward your first three months if
you continue to monitoring.

**What I need from you:**
1. ~150-300 real answers and the retrieved evidence each used (CSV/JSONL is fine).
2. One technical contact for a 30-minute kickoff.
3. The prospect/auditor you'd want to show the report to.

**Next step:** reply "go" and I'll send the kickoff invite + payment link
({{PAYMENT_LINK}}). I can hold {{START_DATE}} for you.

Honest note: free-text checks are deterministic and conservative (strongest on
structured/cited answers); the report is evidence you use in your own audit process,
not a compliance certification.

{{FOUNDER_NAME}}
