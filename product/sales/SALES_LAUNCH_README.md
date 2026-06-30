# GroundLedger - Sales Launch Pack

Everything you need to start selling the **2-week Groundedness Audit Pilot** today.
Open this file, replace the placeholders, send the first 20 messages, book calls,
run the demo, send the proposal, close the pilot.

> Honest-selling rules baked into every asset: no compliance certifications, no
> tamper-*proof* claims (it's tamper-*evident*), no fake customers/logos, no
> buzzwords. We sell the pilot and ask for money.

---

## Positioning (the 30-second version)

- **Product / pilot:** GroundLedger Groundedness Audit Pilot.
- **Buyer:** Head of AI / founding engineer / CTO at a 20-150 person insurance or
  fintech company shipping a document-grounded assistant into regulated buyers.
- **Pain:** "A prospect's security review wants proof our assistant is grounded and
  an audit trail - we don't have one, and the deal is stalling."
- **One-line promise:** Prove your AI didn't make it up - in two weeks, on your own
  answers, with a report your buyer's auditor can reproduce.
- **Duration / price:** 2 weeks · $2,500 ($1,500 design-partner rate, first 3),
  credited toward the first 3 months.
- **Core deliverable:** a signed, self-verifying audit report of their real answers.
- **Subscription path:** Team ($1,900/mo) for continuous monitoring; pilot fee credited.

---

## What's in this pack

```
product/sales/
  SALES_LAUNCH_README.md          <- you are here
  landing/pilot.html              <- pilot landing page (host this)
  pilot/
    one-pager.md / one-pager.html <- one-page sheet (md source + printable HTML)
    proposal-email.md             <- send after a good call
    agreement-outline.md          <- FOR LAWYER REVIEW before use
    kickoff-checklist.md
    delivery-checklist.md         <- keeps the pilot software, not consulting
    report-outline.md             <- structure of the final report
    subscription-conversion-email.md
  outreach/
    cold-email-sequence.md        <- 5-email sequence
    linkedin-sequence.md          <- connection + DMs
    warm-intro.md                 <- forwardable intro request
    voice-note-and-breakup.md
  calls/
    demo-script-15min.md
    discovery-script.md
    discovery-questions.md        <- 20 questions (5 starred)
    objection-handling.md
    close-script.md
  crm/
    prospects.csv                 <- spreadsheet-compatible tracker
    README.md                     <- pipeline stages + how to work it
scripts/
  sales-preview.sh                <- open landing + one-pager
  pilot-pdf.sh                    <- export one-pager.html -> PDF (needs Chrome/Chromium)
```

## Replace these placeholders before sending anything

Search-and-replace across `product/sales/`:

- `{{BOOKING_LINK}}` - your calendar link (e.g. cal.com / Calendly).
- `{{FOUNDER_EMAIL}}` - the reply-to email.
- `{{FOUNDER_NAME}}` - your name.
- `{{COMPANY}}` `{{FIRST}}` `{{VERTICAL}}` `{{ASSISTANT}}` - per-prospect, filled in as you send.
- `{{PAYMENT_LINK}}` - a Stripe payment link / invoice link for the pilot fee.

Quick check for anything you missed:
```bash
grep -rn "{{" product/sales/ | grep -v SALES_LAUNCH_README
```

---

## How to use it

1. **Landing page:** open `landing/pilot.html`, replace `{{BOOKING_LINK}}` and
   `{{FOUNDER_EMAIL}}`, then host the single file anywhere (GitHub Pages, a Netlify
   drop, S3). Preview locally: `./scripts/sales-preview.sh`.
2. **One-pager:** edit `pilot/one-pager.md` (source of truth). For a PDF to attach,
   run `./scripts/pilot-pdf.sh` (uses headless Chrome/Chromium) or open
   `pilot/one-pager.html` and Print > Save as PDF.
3. **Outreach:** copy a template from `outreach/`, fill the per-prospect blanks,
   send from your real address. Log it in `crm/prospects.csv`.
4. **CRM:** track every prospect in `crm/prospects.csv`; see `crm/README.md` for the
   9 pipeline stages. Delete the two `<EXAMPLE>` rows first.
5. **Demo call:** drive `calls/demo-script-15min.md` while running the real product
   demo: `./scripts/demo.sh` then open `product/data/demo/report.html`.
6. **Proposal:** after a good call, send `pilot/proposal-email.md` + the one-pager.
7. **Deliver:** run the pilot with `pilot/kickoff-checklist.md` and
   `pilot/delivery-checklist.md`. Build the report with the product
   (`python -m product.groundledger.export build ...`) using `pilot/report-outline.md`.
8. **After a win:** send `pilot/subscription-conversion-email.md` to move to monthly.

---

## Booking page copy (paste into Cal.com / Calendly)

- **Meeting title:** GroundLedger pilot call (20 min)
- **Description:** A short call to see if a two-week groundedness audit fits your
  assistant. We'll look at how you evidence groundedness today, I'll show a
  10-minute demo, and if it's relevant we'll scope a pilot on your real answers.
  No prep needed.
- **Who should book:** Heads of AI, founding/lead engineers, or CTOs shipping a
  document-grounded assistant into regulated buyers.
- **What we'll cover:** your current eval/audit approach, a live demo, and pilot
  scope + pricing.
- **Bring (optional):** one example answer your assistant gives and the source it
  used - makes the call concrete.
- **Duration:** 20 minutes.
- **Confirmation message:** Booked - thank you. I'll keep it to 20 minutes and come
  ready to show the demo. If you can, jot down one assistant answer + its source
  beforehand. - {{FOUNDER_NAME}}

---

## First-week sales execution plan (results, not prep)

**Day 1 - Set up & list.** Prospecting: build a list of 20 real prospects in
`crm/prospects.csv` (5 ideal-buyer profiles x ~4 each). Outreach: replace
placeholders; publish the landing page. Asset: set the booking link. Follow-up: -.
Reflect: are these the right titles/industries?

**Day 2 - First send.** Prospecting: verify emails/LinkedIn for the 20. Outreach:
send Cold Email 1 to the 10 best + LinkedIn connection requests to the other 10.
Asset: export the one-pager PDF. Follow-up: log every send. Reflect: any instant replies?

**Day 3 - Warm paths.** Prospecting: list 5 mutual contacts for warm intros.
Outreach: send `warm-intro.md` to all 5. Asset: record a 20-sec founder voice note.
Follow-up: reply fast to any Day-2 responses; book calls. Reflect: which angle got replies?

**Day 4 - Follow up.** Prospecting: add 5 more prospects. Outreach: Cold Email 2 to
non-repliers; first DM to new LinkedIn connections. Asset: tweak the subject line
that's underperforming. Follow-up: confirm/booked-call reminders. Reflect: reply rate so far.

**Day 5 - Demos.** Prospecting: -. Outreach: Cold Email 3 to remaining non-repliers.
Asset: -. Follow-up: run booked demos with `demo-script-15min.md`; send proposals
same day. Reflect: did the demo land? where did interest spike?

**Day 6 - Push to proposal.** Outreach: send proposals to anyone demoed; Email 4
(objection) to stalled threads. Follow-up: chase verbal yeses for a start date.
Reflect: how many proposals out vs. target?

**Day 7 - Close & learn.** Outreach: Email 5 (breakup) to dead threads - it often
revives one. Follow-up: confirm any pilot starts + payment. Reflect: write down the
top 3 objections and the one message that worked best; adjust next week.

---

## First-week success metrics

| Metric | Target |
|---|---|
| Prospects identified | 20-25 |
| Prospects contacted | 20 |
| Reply rate | >= 15% (3+ replies) |
| Discovery calls booked | 2-4 |
| Demos completed | 1-3 |
| Pilot proposals sent | 1-3 |
| Pilots closed (paid) | 0-1 (1 is excellent in week 1) |
| Learning milestone | top 3 objections + best-performing message documented |

**Change the offer if:** 20 contacts yield 0 replies (subject/pain is off - rewrite
Email 1); calls happen but nobody names a stalled deal or budget owner (wrong buyer
- shift industries/titles); demos land but price stalls everyone (test the $1,500
rate harder or tighten scope). **Kill/pivot signal:** ~15 qualified calls and zero
name a stalled deal or budget owner -> pivot to the in-VPC reproducible-groundedness
(privacy) angle before building more.

---

## Founder checklist

- [ ] Replace `{{BOOKING_LINK}}`, `{{FOUNDER_EMAIL}}`, `{{FOUNDER_NAME}}`, `{{PAYMENT_LINK}}`.
- [ ] Publish `landing/pilot.html`.
- [ ] Export the one-pager PDF (`./scripts/pilot-pdf.sh`).
- [ ] Set up the booking link with the copy above.
- [ ] Fill `crm/prospects.csv` with 20 real prospects (delete the example rows).
- [ ] Send the first 20 messages (cold email + LinkedIn).
- [ ] Book the first calls.
- [ ] Run a demo (`./scripts/demo.sh` -> `report.html`).
- [ ] Send a pilot proposal (`pilot/proposal-email.md`).
- [ ] Get `pilot/agreement-outline.md` reviewed by a lawyer.
- [ ] Close the first paid pilot.
