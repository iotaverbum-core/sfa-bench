# Subscription conversion email

Send a day or two after the final review, once the report has landed. The pilot
proved value; this makes continuing the obvious next step.

Placeholders: `{{FIRST}}` `{{RATE}}` `{{N_CRITICAL}}` `{{HEADLINE_FINDING}}`
`{{TIER}}` `{{MONTHLY}}` `{{FOUNDER_NAME}}` `{{PAYMENT_LINK}}`.

---

**Subject:** keeping the audit record live

Hi {{FIRST}},

The pilot found {{N_CRITICAL}} critical issues - the clearest being
{{HEADLINE_FINDING}}. You now have a reproducible, tamper-evident report for that
point in time.

The catch with a point-in-time report: your content, prompts, and models change
weekly, so it's stale by the next sprint. The audit record is only credible if it's
live.

**What I'd recommend: {{TIER}} at {{MONTHLY}}/mo.** Every answer your assistant
ships gets a sealed verdict, the ledger stays append-only, and you can export a
report your buyer's auditor reproduces any day. Your pilot fee ({{RATE}}) credits
toward the first three months.

Where teams usually wire it in first:
- a pre-send gate (block fabricated citations / contradictions before the customer sees them), or
- a CI check on a fixed question set (catch regressions before release).

Want me to set up the first one this week? Reply "go" and I'll send onboarding +
the link ({{PAYMENT_LINK}}).

{{FOUNDER_NAME}}
