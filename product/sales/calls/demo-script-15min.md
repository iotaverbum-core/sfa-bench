# 15-minute demo script

Goal: by minute 15, the buyer wants to run it on *their* workflow. Run the real
demo (`./scripts/demo.sh`) on screen, then open `product/data/demo/report.html`.

---

## Minute 0-2: Frame the problem

> "Before I show anything - your assistant answers from documents, right? The risk
> I care about isn't crashes. It's the answer that cites a clause that isn't there,
> or states a number the source contradicts. It looks fine, it ships, and you hear
> about it from a customer or a security review. That's what this catches. I'll
> show it on sample insurance data, then we'll talk about your data."

## Minute 2-5: Confirm their workflow

> "Quick so I show the right thing: are your answers structured - JSON with explicit
> citations - or free text? And what's the source: policy docs, disclosures,
> contracts? Who's asking you the hard groundedness questions today - a specific
> prospect, your own compliance, both?"

(Listen. Mirror their words back in the reveal.)

## Minute 5-10: Show the demo

1. Run `./scripts/demo.sh`. Four answers verified live.
   > "One passes. Three fail - and notice it tells you *why*: this one cites
   > clause_9z, which isn't in the evidence. That's a fabricated citation. This one
   > says the deductible is $500; the source says $1,000 - a contradiction."
2. Open `report.html`.
   > "This is the artifact. Top line: 25% grounded. Findings ranked by severity,
   > each with what we detected, why it matters, and the recommended fix. This is
   > what you'd hand a buyer's security team."
3. The proof moment - edit a sealed failure to look like a pass, re-run replay.
   > "Now watch. I'll quietly change a failed answer to look like it passed... and
   > re-run the check. TAMPER DETECTED. Your auditor runs this themselves. Nobody -
   > including you - can rewrite the record without it showing."

## Minute 10-13: Explain the pilot

> "Here's how we'd do this on yours. Two weeks. You give us ~200 real answers and
> the evidence each used. We deploy in your environment - nothing leaves - tune a
> rule pack for your domain, and produce exactly this report on your data. You walk
> away with findings and a record your prospect's auditor can reproduce."

## Minute 13-15: Close for next step

> "It's $2,500 fixed - and we have two design-partner slots at $1,500, credited to
> your first three months if you continue. If we run it and it surfaces fabricated
> citations or contradictions in your answers, does that change how your current
> deal review goes?"

(If yes -)

> "Then let's start. I'll send a one-page scope today; can you get me ~200 answers
> and their evidence by {{DAY}}? We'll have findings inside two weeks."
