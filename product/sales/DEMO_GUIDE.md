# GroundLedger Demo Guide (for the person selling it)

A plain-language, step-by-step manual for learning and running the demo. No deep
technical knowledge needed. If you can copy and paste a line into a terminal, you
can run this demo.

> Commands are written for **Windows** (they also work on Mac/Linux). If `python`
> ever says "not found", try `python3` instead. Slashes: `product/examples/...`
> works on all systems.

---

## 1. The 30-second idea (say this in your own words)

Companies put AI assistants in front of customers to answer questions from their
documents (policies, disclosures, plans). Sometimes the assistant **makes things
up** - it cites a document section that doesn't exist, or states a number the
source contradicts. That's a hallucination, and it's a real risk in regulated
industries.

**GroundLedger checks every answer against the documents it was supposed to use,
and keeps a permanent, tamper-proof-ish record you can prove to an auditor.** It
runs on the customer's own computers, so their documents never leave.

That's the whole pitch. The demo makes it real in about five minutes.

---

## 2. The story your demo tells (three beats)

1. **We catch the bad answers.** Four sample answers go in; one is fine, three are
   wrong - and it says *exactly why* (fabricated citation, wrong number, etc.).
2. **We turn that into evidence.** Each verdict is sealed into a report your
   customer's auditor can re-check themselves.
3. **Nobody can quietly fudge it.** We edit a failed answer to look like it
   passed - and the system catches it: **TAMPER DETECTED.**

If you can walk someone through those three beats, you can demo GroundLedger.

---

## 3. Words you'll hear (quick glossary)

- **Grounded** - the answer is backed by the source documents. "Not grounded" =
  made up or wrong.
- **Citation** - the document/section the answer points to (e.g. `clause_3a`).
- **Fabricated citation** - the answer points to a section that doesn't exist.
- **Contradiction** - the answer states a value that disagrees with the source
  (e.g. says the deductible is $500 when the document says $1,000).
- **Receipt** - a sealed record of one answer's verdict, like a store receipt you
  can't secretly change.
- **Ledger** - the running list of all those receipts, chained together so nothing
  can be deleted or reordered without it showing.
- **Groundedness rate** - the percentage of answers that were grounded.
- **Tamper-evident** - if someone edits the record, a check breaks and it shows.
  (Not the same as "impossible to edit" - be honest about that.)
- **Replay / attest** - re-checking the whole record from scratch to confirm the
  verdicts are real. This is the "prove it yourself" part.

---

## 4. One-time setup

You need three things:

1. **A computer** (Windows, Mac, or Linux).
2. **Python 3.11 or newer.** Check it:
   ```
   python --version
   ```
   You should see `Python 3.11.x` or higher. If not, install Python from
   python.org (tick "Add to PATH" during install on Windows).
3. **The GroundLedger code** on your computer. You already have it in the
   `sfa-bench` folder.

Open a terminal **inside the `sfa-bench` folder**:
- Windows: open the folder in File Explorer, type `cmd` in the address bar, press
  Enter. (Or right-click the folder > "Open in Terminal".)
- Mac/Linux: open Terminal and `cd` into the folder.

That's it. There is **nothing to install** - no accounts, no keys, no internet.

---

## 5. Run the demo (the main event)

Type this one line and press Enter:

```
python -m product.demo
```

You'll see the story play out on screen. Here is what each part means:

**Part A - the four answers get checked:**
```
[PASS] ans_grounded_001: grounded in evidence
[FAIL] ans_fabricated_002: fabricated_entity - cited evidence id(s) not present ...
[FAIL] ans_contradicts_003: contradicts_evidence - claim 'deductible=$500' ...
[FAIL] ans_unsupported_004: unsupported_claim - claim about 'rental_reimbursement' ...
```
One answer is good. Three are caught, each with the reason in plain terms.

**Part B - the report:**
It prints a summary like "1 of 4 answers (25%) were grounded" and lists the
**findings ranked by severity** (Critical / High / Medium), each with a
recommended action. This is what a customer's security team wants to see.

**Part C - the files it saved:**
```
report : product/data/demo/report.html   (open in a browser)
bundle : product/data/demo/bundle.json    (signed, verifies offline)
```
`report.html` is the pretty version you can show or print. `bundle.json` is the
"prove it yourself" file for their auditor.

**Part D - the moment that sells it** (see section 6).

If you got here, you've run the demo. Congratulations - that's 90% of it.

---

## 6. The moment that sells it (tamper detected)

At the end, the demo does this on purpose:
```
Now an insider quietly edits a sealed failure to look like a pass...
  edited ans_fabricated_002.json: FAIL -> PASS (without re-sealing)

  re-attestation: TAMPER DETECTED
```

**What just happened, in plain terms:** someone tried to cheat - to make a bad
answer look good in the records. The system re-checked everything and caught it.

**What to say to a buyer:** *"Your evals live in a dashboard you could edit. This
is a record your auditor re-runs themselves - and if anyone changes it, it shows.
That's the difference between a metric and evidence."*

That line is the heart of the sale.

---

## 7. Show the pretty report in a browser (optional wow)

The `report.html` file from the demo opens in any browser (double-click it). But
to show the **live** version the way a customer would use it:

1. Load some sample answers into the system:
   ```
   python -m product.groundledger.ingest product/examples/batch.jsonl --tenant demo-tenant --data-root product/data
   ```
2. Start the local app:
   ```
   python -m product.groundledger.api
   ```
3. Open your browser to **http://127.0.0.1:8000/**, type the key `demo-key`, and
   click "View audit report". You'll see the groundedness rate, the findings, and
   a green **VERIFIED** badge.
4. When done, go back to the terminal and press **Ctrl + C** to stop the app.

Everything is running on your own computer - nothing goes to the internet. That's
a selling point: say *"this runs entirely inside your environment."*

---

## 8. Prove it's trustworthy (the reproducibility check)

Run:
```
python -m product.groundledger.verification
```
You'll see:
```
reproducibility : PASS
tamper detection: PASS
final status: VERIFIED
```

**What to say:** *"The same inputs always produce the exact same result - I can
prove it, and so can you. And it catches a corrupted file. That's why an auditor
will accept it."*

(On Mac/Linux you can also type `make verify` as a shortcut. On Windows use the
line above.)

---

## 9. Run it on real answers (when a customer gives you data)

The demo uses sample answers. To run it on a batch of real ones, put them in a
file (JSONL or CSV - the `product/examples/batch.jsonl` and `batch.csv` files show
the exact shape), then:

```
python -m product.groundledger.ingest their-answers.jsonl --tenant acme --data-root product/data
```

It prints how many were grounded and the findings. Then show the report in the
browser (section 7, using `--tenant acme` and the matching key) or export a
report file. This is exactly what a paid pilot does - on ~150-300 of their answers.

---

## 10. Running a live demo call

Keep it to ~15 minutes. The full word-for-word script is in
`product/sales/calls/demo-script-15min.md`. The short version:

1. **Frame the problem** (1 min): "Your assistant answers from documents; the risk
   is the answer that cites something that isn't there."
2. **Run `python -m product.demo`** (3-4 min): walk through the four answers and
   the findings.
3. **The tamper moment** (1 min): "Watch - I'll fake a pass... TAMPER DETECTED."
4. **Show the browser report** (2 min, optional): the page a non-engineer reads.
5. **Close** (1 min): "Let's run this on ~200 of your real answers - two weeks,
   fixed price. You get a report your auditor can reproduce."

Practice the run 3-4 times until the commands feel automatic. That's all it takes.

---

## 11. If something goes wrong

- **"python is not recognized" / "not found":** try `python3` instead of `python`.
  If neither works, Python isn't installed or wasn't added to PATH - reinstall
  from python.org and tick "Add to PATH".
- **"No module named product":** you're in the wrong folder. Make sure your
  terminal is inside the `sfa-bench` folder (run `dir` on Windows / `ls` on
  Mac/Linux and check you see `product` and `sfa`).
- **The browser page says "API key required":** add the key - go to
  http://127.0.0.1:8000/ and type `demo-key`, or use
  http://127.0.0.1:8000/v1/report.html?key=demo-key
- **The report shows "TAMPER DETECTED" when you didn't expect it:** the demo
  leaves one answer tampered on purpose. To start clean, delete the folder
  `product/data` and re-run your commands.
- **Reset everything:** delete the `product/data` folder. It only holds demo/run
  data; nothing important is lost.
- **Port already in use:** something else is using 8000. Close it, or start the
  app on another port: `python -m product.groundledger.api` after setting the
  port (ask your engineer, or just reboot and retry).

---

## 12. Cheat sheet (all the commands)

```
python --version                                   # check Python 3.11+
python -m product.demo                             # run the full demo
python -m product.groundledger.verification        # prove it's reproducible + catches tampering

# Browser report:
python -m product.groundledger.ingest product/examples/batch.jsonl --tenant demo-tenant --data-root product/data
python -m product.groundledger.api                 # then open http://127.0.0.1:8000/  (key: demo-key)
#   press Ctrl+C to stop

# Run on real answers:
python -m product.groundledger.ingest their-answers.jsonl --tenant acme --data-root product/data
```

---

## 13. What NOT to say (stay honest - it builds trust)

- Don't say "tamper-proof" or "unhackable." Say **"tamper-evident"** - edits are
  detected.
- Don't say "certified" or "compliant." Say **"audit-ready evidence you use in
  your own compliance process."**
- Don't say "it catches every hallucination." Say **"it reliably catches
  fabricated citations and contradictions, deterministically, and records
  everything."**
- Don't promise it works on any answer format instantly. Strongest on answers that
  cite their sources; free-text is supported but more conservative.

Being straight about the limits is what makes a skeptical buyer trust the rest.
The full boundary is in `product/TRUST_MODEL.md` if they ask.

---

*You've got this. Run the demo a few times, get comfortable with the three beats,
and you'll be able to show it to anyone.*
