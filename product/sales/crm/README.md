# CRM / prospect tracking

`prospects.csv` is a spreadsheet-compatible tracker. Open it in Excel / Google
Sheets / Numbers, or edit as text. The two rows marked `<EXAMPLE - replace this
row>` are templates - delete them and add real prospects. **Do not invent
companies; only enter prospects you've actually identified.**

## Columns

| Column | What goes in it |
|---|---|
| company | Prospect company |
| contact_name | Person you're selling to |
| title | Their role (Head of AI, CTO, ...) |
| email | Direct email |
| linkedin | Profile URL |
| industry | Insurance / Fintech / Healthcare / Legal / ... |
| trigger_event | Why now (stalled deal, ISO 42001, prospect asked for audit trail) |
| pain_hypothesis | Your one-line guess at their pain (test it in discovery) |
| outreach_status | Current pipeline stage (see below) |
| last_touch | Date of last contact |
| next_action | The single next thing to do |
| interest_level | Cold / Low / Medium / High |
| objection | The main pushback heard |
| pilot_fit | High / Medium / Low (cited answers + audit pressure = High) |
| expected_value | Likely subscription tier value if they convert |
| notes | Anything useful (answer format, who else is involved) |

## Pipeline stages (use these in `outreach_status`)

1. **Target identified** - in the list, not yet contacted.
2. **Contacted** - first message sent.
3. **Replied** - they responded (any response).
4. **Discovery booked** - call on the calendar.
5. **Demo completed** - they've seen the 15-minute demo.
6. **Pilot proposed** - proposal email sent.
7. **Pilot won** - paid, kickoff scheduled.
8. **Pilot lost** - no for now (record the reason in `objection`).
9. **Subscription converted** - moved to a monthly plan.

## How to work it

- Sort by `next_action` daily; do the next action for every active row.
- Keep `last_touch` current so follow-ups don't slip.
- Move a row to **Pilot lost** quickly when it's a no - a clean no is better than a
  slow maybe. Note why; the reasons are your product feedback.
