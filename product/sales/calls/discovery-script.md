# Discovery call script (20-30 min)

Goal: qualify pain and sell the pilot. Not to educate endlessly. If it isn't a
fit, say so and move on - that's a win too.

---

## Opening (30s)

> "Thanks for the time. I'll keep this short: I want to understand how you handle
> groundedness and audit questions today, show you a ten-minute version, and if
> it's relevant, propose a two-week pilot on your own answers. If it's not a fit,
> I'll tell you. Sound good?"

## Qualify (2-3 min)

- "Tell me about your assistant - what does it answer, and from what documents?"
- "Customer-facing or internal? Roughly what volume of answers?"
- "Do answers cite sources, or is it free text?"

## Pain (5-7 min) - spend the most time here

- "Walk me through the last enterprise security or AI-risk review. What did they
  ask about hallucinations or audit trails?"
- "When the assistant gets something wrong, how do you find out today?"
- "What do you do right now to evidence that an answer was grounded - and who built
  it?"

## Current workflow (3 min)

- "What's in your eval/QA setup today - LLM-as-judge, manual review, something else?"
- "Could you reproduce a specific answer's groundedness verdict from three weeks ago
  if a customer asked?"

## Risk / compliance (2-3 min)

- "Are you pursuing SOC 2 / ISO 42001, or answering EU AI Act questions?"
- "Has a prospect ever asked for an audit trail of AI decisions? What did you send?"
- "Can customer documents leave your environment, or must they stay in your VPC?"

## Budget / ownership (2 min)

- "If this unblocked a stalled deal, who would own it - you, security, compliance?"
- "What would you normally spend to de-risk a deal stuck in security review?"

## Demo (10 min)

Run the 15-minute demo script (condensed). Mirror their words from the pain section.

## Close

> "Based on what you've seen - if we ran this on ~200 of your real answers and the
> report surfaced fabricated citations or contradictions, would that change how that
> review goes?"

> "Here's what I'd propose: two weeks, $2,500 - or our $1,500 design-partner rate,
> two slots left - credited to your first three months if you continue. You give us
> ~200 answers and their evidence; you get a report your prospect's auditor can
> reproduce. Can we start {{DAY}}? I'll send a one-page scope today."

## If not a fit

> "Honestly, this is strongest when your assistant cites sources and you've got
> external audit pressure. It doesn't sound like that's you right now, so I won't
> push it. If that changes, you know where I am."
