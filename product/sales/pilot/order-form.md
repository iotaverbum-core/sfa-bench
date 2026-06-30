# GroundLedger Audit Pilot - Order Form

> Commercial order form (one page). It records the scope, price, and sign-off for
> the pilot. It is **not legal advice** and is **subject to the GroundLedger Pilot
> Agreement** (`agreement-outline.md` - have a lawyer turn it into your signed
> agreement / order form before relying on it).

Placeholders the provider fills before sending: `{{PROVIDER}}` `{{PROVIDER_EMAIL}}`
`{{PRICE}}` `{{START_DATE}}` `{{RULE_PACK}}` `{{PAYMENT_LINK}}`.

---

**Provider:** {{PROVIDER}}  ·  {{PROVIDER_EMAIL}}
**Customer:** ______________________________  (legal name)

## Service
**GroundLedger Audit Pilot** - a 2-week, fixed-scope engagement that runs
deterministic groundedness checks on the Customer's real assistant answers and
delivers a tamper-evident audit report the Customer can independently reproduce.

## Commercial terms

| | |
|---|---|
| **Price** | {{PRICE}} (one-time, fixed). Credited toward the Customer's first 3 months if they subscribe within 30 days of the final report. |
| **Term** | 2 weeks from kickoff (optional 1-week extension by mutual written agreement). |
| **Start date** | {{START_DATE}} (begins once the Customer delivers the data below). |
| **Payment** | Due at kickoff via {{PAYMENT_LINK}}. |

## Scope (included)
- One assistant; the **{{RULE_PACK}}** rule pack tuned for the Customer's domain (one tuning pass).
- ~150-300 Customer-supplied answers, each verified and sealed into a hash-chained ledger.
- Deliverables: executive summary, severity-ranked findings with recommended actions,
  evidence per finding, a signed self-verifying export bundle, and a subscription proposal.

## Excluded
Custom connectors/integrations, new check types, additional rule packs, more than
one tuning pass, more than one assistant, and production system integration. Anything
not listed above is a separate engagement.

## Customer provides
- ~150-300 real answers and the evidence each used (CSV/JSONL).
- One technical contact for a 30-minute kickoff and a review call.
- The buyer/auditor the report will be shown to (for the success check).

## Success criteria
A reproducible groundedness baseline on the Customer's real answers, a report whose
verdicts replay identically on a clean machine, and the report accepted as evidence
by the Customer's named buyer/auditor.

## Data & limits (summary; full terms in the Pilot Agreement)
Runs in the Customer's environment; no documents are required to leave it. The
checks are deterministic and rule-based; free-text coverage is conservative.
"Tamper-evident" means a covered edit breaks an integrity check - **not**
tamper-proof, not non-repudiation, and **not** a compliance certification. The
report is evidence for the Customer's own audit/procurement process.

## Sign-off

By signing, the Customer orders the pilot above under the GroundLedger Pilot
Agreement.

| Customer | Provider |
|---|---|
| Name: ____________________ | Name: ____________________ |
| Title: ____________________ | Title: ____________________ |
| Signature: ________________ | Signature: ________________ |
| Date: ____________________ | Date: ____________________ |
