# Paid pilot agreement - outline

> **FOR LAWYER REVIEW BEFORE USE.** This is a founder-friendly outline of terms,
> not legal advice and not a contract. Have a qualified attorney turn it into a
> signed agreement (or a mutual order form + your MSA) before relying on it.

Placeholders: `{{PROVIDER}}` (your company), `{{CUSTOMER}}`, `{{START_DATE}}`,
`{{PRICE}}`, `{{RULE_PACK}}`.

## 1. Parties & term
- Provider: {{PROVIDER}}. Customer: {{CUSTOMER}}.
- Term: 2 weeks from kickoff ({{START_DATE}}), with an optional 1-week extension by
  mutual written agreement.

## 2. Scope of services
- Deploy GroundLedger in the Customer's environment (in-VPC container or SDK).
- Tune one rule pack ({{RULE_PACK}}) for the Customer's domain (one tuning pass).
- Verify ~150-300 Customer-supplied answers and seal them into a hash-chained ledger.
- Produce one audit report (HTML + signed self-verifying bundle) and one review call.

## 3. Deliverables
- Executive summary, severity-ranked findings with recommended actions, evidence per
  finding, the signed audit bundle, and a monitoring/subscription proposal.

## 4. Customer responsibilities
- Provide ~150-300 real answers and the evidence each used, in an agreed format.
- Provide one technical contact and timely access for a 30-minute kickoff and review.
- Review and approve the rule-pack mapping during the tuning pass.

## 5. Exclusions
- Custom connectors/integrations, new check types, additional rule packs, more than
  one tuning pass, more than one assistant, or production system integration.
- Anything not listed in Scope is a separate paid engagement.

## 6. Data handling (assumptions - confirm with counsel)
- The software runs in the Customer's environment; Provider does not require copies
  of Customer documents to leave that environment.
- If Customer chooses to share sample data with Provider for setup, it is used only
  to deliver the pilot and deleted on request at the end of the term.
- No third-party subprocessors are required to run the core checks (stdlib-only, no
  network egress). Confirm any exceptions in writing.

## 7. Payment
- {{PRICE}}, due at kickoff. Creditable toward the first three months of a
  subsequent subscription if the Customer converts within 30 days of the final
  report.

## 8. Renewal path
- Conversion to a monthly subscription (Starter/Team/Enterprise) is offered, not
  required. No auto-renewal of the pilot; no auto-conversion to a subscription.

## 9. Cancellation
- Either party may end the pilot in writing. If Provider has not yet delivered the
  report, fees paid for undelivered work are refundable on a pro-rata basis (define
  the exact basis with counsel).

## 10. Limitations (state plainly; refine with counsel)
- The checks are deterministic and rule-based; free-text extraction is conservative
  and may not surface every claim. "Tamper-evident" means covered edits break an
  integrity check; it is not tamper-proof or non-repudiation.
- The report is evidence for the Customer's own audit/procurement process and is
  **not** a compliance certification, legal opinion, or warranty of model behaviour.
- Standard limitation-of-liability and warranty-disclaimer language to be added by
  counsel.
