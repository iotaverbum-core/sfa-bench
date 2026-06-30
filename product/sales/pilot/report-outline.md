# Final pilot report - outline

The product generates most of this (`report.html` + signed `bundle.json`). You add
a one-page business summary on top. Useful to both the CISO and the engineer.

## 1. Executive summary (1 page, non-technical)
- Groundedness rate on the real answers (e.g., "82% grounded; 6 critical findings").
- The single headline risk in plain English.
- Verification status: **VERIFIED** (the record was reproduced independently).

## 2. Systems / workflows analysed
- Which assistant, question set, number of answers, rule pack + version, evidence
  source, run dates.

## 3. Key risks found
- Each finding: what we detected, the question, the assistant's actual answer, and
  the evidence it conflicts with.

## 4. Severity ranking
- Critical (fabricated citation, contradiction) / High (unsupported claim) /
  Medium (missing or malformed). Counts up top.

## 5. Evidence / examples
- The sealed receipt (content hash) per finding, the offending citation/claim, and
  the source it failed against.

## 6. Business impact
- Plain-language consequence per severity (e.g., "a contradicted deductible is a
  likely complaint or claim dispute").

## 7. Recommended fixes
- The per-finding recommended action (block + human review; constrain citations to
  retrieved ids; require the answer schema; etc.).

## 8. Monitoring recommendation
- Where to wire GroundLedger in (pre-send gate, CI eval, production sampling) and
  what to watch over time.

## 9. Subscription proposal
- Tier, price, what continuous monitoring covers, and the pilot-fee credit.

## 10. Appendix (technical)
- The full sealed ledger, the one-line replay command for the auditor, the rule
  pack used, and the honest coverage note: free-text conservatism; tamper-evident
  is not tamper-proof; HMAC signing is keyed integrity, not public-key
  non-repudiation; this is evidence for your audit process, not a certification.
