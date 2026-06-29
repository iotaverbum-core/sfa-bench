# GroundLedger — MVP Launch Plan

A bridge from this repository (`sfa` research core) → a sellable MVP → a paid
subscription. The working first slice lives in [`product/`](.) and is validated:
`python -m product.demo` and `python -m unittest discover -s product -t . -p 'test_*.py'`.

---

## 1. Product decision (restated)

- **Strongest market gap:** *Groundedness as defensible, tamper-evident,
  independently-reproducible evidence* — not a dashboard metric — computable
  inside the customer's environment with no data egress. Eval tools (Galileo,
  Ragas, Patronus, LangSmith) sell mutable, nondeterministic LLM-judge
  dashboards; nobody owns the **audit record that survives adversarial inspection**.
- **First paying customer:** Head of AI / founding engineer at a 20–150-person
  vertical-AI company selling a document-grounded assistant into **insurance or
  financial-services** enterprises.
- **Painful problem:** Enterprise deals stall in AI-risk/security review that
  demands hallucination controls + an audit trail, and the team has no
  reproducible, tamper-evident way to prove answers were grounded.
- **Subscription product:** GroundLedger — a deterministic groundedness gate that
  seals every verdict into a tamper-evident, auditor-replayable ledger,
  deployable in the customer's VPC.
- **Core promise:** *Prove your AI didn't make it up — and prove you didn't hide
  the times it did.*
- **Why now:** EU AI Act logging/record-keeping (Art. 12), ISO/IEC 42001, and
  enterprise AI-risk questionnaires are hitting AI vendors this year; current
  tools answer "we monitor it," not "here is reproducible, unalterable proof."

---

## 2. MVP in one sentence

> For a **Head of AI at a vertical RAG company selling into regulated buyers**,
> GroundLedger helps them **pass AI-risk review and answer customer/regulator
> audit requests** by **sealing every assistant answer's groundedness into a
> deterministic, tamper-evident, independently-replayable ledger**, so they can
> **close stalled enterprise deals and produce audit evidence on demand.**

---

## 3. The sellable demo (built: `python -m product.demo`)

- **Scenario:** An insurance policy assistant answers four customer questions.
- **Current pain:** The team can't prove which answers were grounded, and nothing
  stops a bad answer (or a quiet edit of the record) from slipping through review.
- **Input:** Four answers with citations + the policy evidence each used.
- **What it proves:** One answer is grounded (PASS); three fail with named,
  categorized reasons — a fabricated clause citation, a contradicted deductible,
  and an unsupported coverage claim.
- **Output/report:** An audit report (groundedness rate, failure-family
  breakdown) plus an **independent attestation: ATTESTED**, with the exact
  reproduce command.
- **The "aha":** An insider edits a sealed failure to look like a pass. Replay
  immediately returns **TAMPER DETECTED** (`seal_broken` + `verdict_mismatch`).
- **Why not manual:** Determinism + content-addressed seals + a hash chain across
  every answer can't be reproduced by spot-checking in a spreadsheet, and a
  human reviewer can't prove the record wasn't edited.
- **Why monitor continuously:** Source documents, prompts, and models change
  weekly; the audit ledger is only credible if it is live and append-only.

---

## 4. Repo → product architecture

| Layer | v1 choice |
|---|---|
| Existing repo capability | `sfa.verifier` (deterministic judgment), `sfa.families` (classification), `sfa.hashing` (content addressing), history-blind invariants |
| Backend services | `engine` (verify→seal), `store` (per-tenant), `ledger` (hash chain), `replay` (attest), `report` (audit export), `api` (stdlib HTTP) |
| Frontend screens | Landing, signup/login, dashboard, new-run, result/receipt, history/audit, billing (v1: landing + report view are real; rest are thin) |
| Database/storage | Filesystem per tenant in v1 (`store.py`); Postgres later — data contract unchanged |
| Authentication | `X-API-Key` → tenant map in v1; SSO later |
| Billing | Stripe link / manual invoicing for pilots in v1; metered self-serve later |
| Report/export | `report.build_report` JSON + `render_text`; PDF + signed export later |
| CI / integration | Python SDK (thin wrapper over `/v1/verify`) + examples; TS SDK later |
| Admin/internal | CLI replay (`python -m product.groundledger.replay`); admin UI later |

---

## 5. MVP feature list

**Must have for first paid pilot** (all built except SDK packaging + PDF):
- Deterministic groundedness verdict with categorized reason (`engine`).
- Sealed, content-addressed receipt per answer (`engine`).
- Append-only hash-chained ledger (`ledger`, `store`).
- Independent replay / attestation (`replay`).
- Audit report (`report`) — JSON now, PDF next.
- One vertical rule pack (`rule_packs/insurance_v1.json`).
- HTTP API + API-key tenancy (`api`).

**Should have soon after:**
- Thin Python + TS ingestion SDKs; PDF/signed export; rule-pack editor UI;
  groundedness trend dashboard; second rule pack (fintech); webhook ingestion.

**Later enterprise features:**
- In-VPC/on-prem deploy packaging; SSO/RBAC; retention controls; EU AI Act / ISO
  42001 evidence templates; free-text → structured **claim extraction** (sealed,
  replayable); model/prompt failure-profile comparison.

**Do not build yet:**
- Multi-cloud, marketplace, auto-remediation/retry, leaderboards, agent-action
  monitoring, code-gen QA, anything outside document-grounded answers.

---

## 6. First user workflow

| # | Step | User action | System action | Screen | Data stored | Failure case |
|---|---|---|---|---|---|---|
| 1 | Sign up | Request a key | Issue API key → tenant | Signup | tenant, key | dup email → reuse |
| 2 | Connect | POST first answer+evidence to `/v1/verify` | Validate submission, load rule pack | New-run / curl | submission | bad schema → 400 |
| 3 | Analyse | — | Run verifier, classify family | — | — | unknown rule pack → 400 |
| 4 | Find risk | — | Seal receipt, append ledger | Result | receipt, ledger entry | unsafe id → reject |
| 5 | Report | Open audit report | Aggregate + attest | Report | — | tampered record → issues listed |
| 6 | Share | Export report + replay cmd | Emit JSON (+PDF later) | Report | export log | — |
| 7 | Subscribe | Sees reproducible, tamper-evident proof | Show plan limits | Billing | plan | — |

---

## 7. First screens (wireframe intent)

- **Landing** (built: `product/landing/index.html`) — Purpose: convert pain to a
  pilot. Headline "Prove your AI didn't make it up." Primary CTA: book pilot.
  Components: pain trio, benefit trio, how-it-works, pricing, FAQ. Empty/Error: n/a.
- **Signup/login** — Purpose: issue an API key. Headline "Start verifying in 5
  minutes." Primary: create key. Components: email, key reveal, quickstart curl.
  Empty: no projects yet. Error: invalid email.
- **Dashboard** — Purpose: at-a-glance groundedness. Headline "Groundedness this
  week." Primary: new run. Components: rate tile, failure-family bars,
  attestation badge. Empty: "Verify your first answer." Error: data unreadable.
- **New analysis/run** — Purpose: submit/test one answer. Headline "Check an
  answer." Primary: verify. Components: JSON editor, rule-pack picker, result.
  Empty: prefilled example. Error: 400 with field detail.
- **Result/receipt** — Purpose: show verdict + seal. Headline verdict + reason.
  Primary: copy receipt hash. Components: status, category, violations, hashes.
  Empty: n/a. Error: missing record.
- **History/audit** — Purpose: the defensible trail. Headline "Audit ledger."
  Primary: export report. Components: chained entries, attestation, reproduce cmd.
  Empty: "No answers yet." Error: TAMPER DETECTED banner with issues.
- **Billing** — Purpose: pick a plan. Headline "Plans." Primary: subscribe.
  Components: tiers, usage meter. Empty: free tier. Error: payment failed.

---

## 8. Landing page copy

Implemented verbatim in `product/landing/index.html`. Highlights:
- **Hero:** "Prove your AI didn't make it up."
- **Subhead:** tamper-evident, independently-replayable audit trail, runs in your
  environment, no documents leave your walls.
- **Primary CTA:** Book a 2-week paid pilot. **Secondary:** See the 5-minute demo.
- **Pain:** deals stall in AI risk review · evals can't be reproduced · data
  can't go to a SaaS.
- **Benefits:** deterministic verdicts · tamper-evident by design · runs in your VPC.
- **How it works / Who it's for / Pricing / FAQ / Final CTA** all present.

---

## 9. Pricing for v1

| Tier | Price | Usage | Seats | Reports/history | Integrations | Support | Upgrade trigger |
|---|---|---|---|---|---|---|---|
| Dev | $0 | 1k verdicts/mo | 1 | 7-day, local replay | API | Community | Need retained history |
| Starter | $399/mo | 50k/mo | 3 | 90-day ledger, 1 export/mo | API + Python SDK | Email | Need unlimited exports / SSO |
| Team | $1,900/mo | 500k/mo | 10 | 1-year ledger, unlimited exports | + webhooks | Slack, next-day | Need in-VPC / retention / DPA |
| Enterprise | from $45k/yr | metered | unlimited | unlimited, signed exports | in-VPC deploy | SLA + security-review help | — |

**Sell first:** the **Team-priced paid pilot** (§13). The buyer's pain is a
stalled 6-figure deal, so $1–2k/mo is trivial; Starter is the self-serve landing
spot once the pilot proves value.

---

## 10. Build backlog (status: ✅ done in this slice)

- **Product foundation** ✅ — `product/` package, gitignored runtime data.
- **Core analysis engine** ✅ — `engine.py`. *AC:* four categories correctly
  assigned. *Validate:* `EngineTests`.
- **API/backend** ✅ — `api.py` (`/v1/verify`, `/receipts`, `/audit-report`,
  `/replay`). *AC:* verify→report roundtrip + auth. *Validate:* `ApiTests`.
- **Database** ✅(v1 fs) — `store.py`. *AC:* safe ids, submission+receipt+ledger
  persisted. *Validate:* replay tests.
- **Frontend** ✅(landing) — `landing/index.html`. Later: dashboard/report views.
- **Reports/exports** ✅ — `report.py`. *AC:* groundedness rate + attestation.
- **Authentication** ✅(v1) — API-key→tenant in `api.py`. *AC:* missing key → 401.
- **Billing** ⬜ later — Stripe link for pilots.
- **Reports/exports** ✅✅ — `report.py` + `export.py` (signed, self-verifying
  bundle + printable HTML). *Validate:* `ExportTests`.
- **Tests** ✅ — `tests/test_groundledger.py` (19 passing).
- **Deployment** ✅ — `product/Dockerfile` + env-config API + `.dockerignore`.
- **Documentation** ✅ — `product/README.md`, this plan.

- **SDK** ✅ — `sdk/` (embedded + HTTP transports). *Validate:* `test_sdk` (4).

Follow-on backlog (each: goal / files / AC / validation):
1. **Free-text claim extraction** — `extract.py` — AC: text→{claims,citations}
   sealed + replayable; verifier stays deterministic — `test_extract`. (next)
2. **Stripe billing + usage metering** — `billing.py` — AC: plan limits enforced.
3. **Dashboard / report view UI** — `product/web/` — AC: renders audit report.

---

## 11. Build order (10 steps; smallest input→report path first)

1. Engine: submission → deterministic verdict (done).
2. Seal receipt + hash (done).
3. Per-tenant store (done).
4. Hash-chained ledger (done).
5. Replay/attestation (done).
6. Audit report + render (done).
7. HTTP API + API-key tenancy (done).
8. Insurance rule pack + examples + demo (done).
9. Tests across all of the above (done).
10. Landing page + pilot CTA (done). Signed self-verifying audit export +
    in-VPC Dockerfile (done). Python SDK (embedded + HTTP) (done).
    **Next:** free-text claim extraction.

---

## 12. Sales validation (14 days)

**20 targets by category:** 8 insurance-AI startups, 6 fintech/RAG startups, 3
healthcare-doc-AI (secondary), 3 enterprise AI-risk/procurement reviewers (to
confirm acceptable evidence).

**Outreach (cold):**
> "You sell a document assistant into regulated buyers. When their security team
> asks how you prevent and *evidence* hallucinations, what do you send today? I'm
> testing a tool that turns each answer's groundedness into a tamper-evident
> audit trail an auditor can reproduce. Worth 20 minutes?"

**Discovery questions:** walk me through your last AI-risk review · what do you do
today to evidence groundedness, and who built it · has a buyer asked for an audit
trail · who owns this budget · if it reproduced your verdicts for an auditor,
what would you pay monthly?

**Demo script:** run `python -m product.demo` → PASS/FAIL with reasons → audit
report ATTESTED → forge a pass → TAMPER DETECTED. Then "this runs in your VPC."

**Strong demand:** ≥6/12 unprompted cite stalled/lost deals; ≥3 offer real data;
≥2 commit to a paid pilot/LOI; a reviewer says the export would satisfy their ask.

**Weak demand:** "SOC 2 / our evals cover it"; interest only in *improving* the
model, not *proving/recording*; no named budget owner or dollar figure.

**If they don't care:** drop the audit framing, reposition as an in-VPC
deterministic groundedness gate (privacy + reproducibility). If structured-output
is the blocker for everyone, claim-extraction is the real product — reorder the
build, keep the customer.

---

## 13. First pilot offer

- **Name:** GroundLedger Audit Pilot.
- **Duration:** 2 weeks (option to extend to 4).
- **Price:** $1,500 fixed (credited to first 3 months if they convert).
- **Customer gets:** in-VPC deploy on one assistant, a custom rule pack for their
  domain, a sealed ledger of their real answers, one exported audit report, and a
  reviewer replay walkthrough.
- **Customer provides:** ~200 real answers with citations + the evidence chunks,
  one technical contact, and one target buyer/auditor to show the report to.
- **Success criteria:** the exported audit report is **accepted as evidence by
  one of their own buyers or auditors**, and replay reproduces every verdict on a
  clean machine.
- **Renewal path:** convert to Team ($1,900/mo) for continuous verification, or
  Starter ($399/mo) for lighter volume; pilot fee credited.

---

## 14. Founder instruction

- **First thing to build:** ✅ built — the input→verdict→sealed ledger→audit
  report→replay path, plus the signed self-verifying export bundle and the
  one-command in-VPC Docker image a pilot buyer shows their auditor, and a thin
  Python SDK (embedded + HTTP) for afternoon integration (`product/`).
  **Next:** free-text claim extraction to widen beyond structured/cited answers.
- **First thing to sell:** the **$1,500 2-week Audit Pilot** to one insurance-AI
  startup whose deal is stuck in security review.
- **First thing to measure:** does one customer's **buyer/auditor accept the
  exported report as evidence** (the only proof that matters).
- **Biggest risk:** v1 needs **structured, cited answers**; most RAG output is
  free text, and extracting claims deterministically is unsolved (an LLM
  extractor reintroduces the nondeterminism you sell against). Mitigation: target
  JSON-mode/function-calling RAG now; build sealed, replayable claim extraction as
  the wedge-expander.
- **Fastest way to prove it deserves to exist:** get one stalled deal unblocked by
  a GroundLedger audit report inside 60 days. If 12 founders can't name a stalled
  deal or a budget owner, the pain is real but not *bought* — pivot to the in-VPC
  reproducible-groundedness framing before building more.
