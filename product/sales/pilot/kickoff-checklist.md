# Pilot kickoff checklist

Run this on (or just before) the 30-minute kickoff call. Goal: leave with data,
a deployment choice, and a date - so the pilot doesn't drift.

## Before kickoff
- [ ] Payment received (or PO/commitment in writing).
- [ ] One-page scope signed/approved.
- [ ] Technical contact named and on the invite.
- [ ] Base rule pack chosen: `insurance_v1` / `fintech_v1` / custom.

## On the kickoff call
- [ ] Confirm the assistant in scope and the question types.
- [ ] Confirm answer format: structured (JSON + citations) or free text.
- [ ] Confirm the evidence shape: documents (ids) + facts (subject/value).
- [ ] Pick deployment: in-VPC Docker **or** embedded Python SDK.
- [ ] Agree the data hand-off: ~150-300 answers + evidence, format (CSV/JSONL), by when.
- [ ] Define the success metric in their words (e.g., "report accepted by {{PROSPECT}}").
- [ ] Name everyone who should see the final report.
- [ ] Set the end date and the review-call slot.

## Data the customer must provide
- [ ] ~150-300 real answers from the assistant.
- [ ] For each answer: the retrieved evidence (source documents with ids + key facts).
- [ ] Optional: the original question per answer (improves the report's readability).

## Immediately after kickoff
- [ ] Send recap email with the agreed data spec + dates.
- [ ] Share the ingest template (columns: answer_id, question, answer_text or
      structured candidate, evidence documents, evidence facts).
- [ ] Calendar hold for the review call.
