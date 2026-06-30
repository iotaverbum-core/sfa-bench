# GroundLedger Trust Model

This document is for a customer who does not know or trust us. It states plainly
what GroundLedger proves, what it does not, and exactly what you can check
yourself. Trust here comes from reproducibility and evidence, not from our word.

Everything below is verifiable from a clean checkout with:

```bash
make verify        # or: python -m product.groundledger.verification
make test          # the product test suite
```

## What GroundLedger claims to prove

Under the rules in a given rule pack, and for the answers and evidence you supply:

1. **Groundedness verdicts are deterministic.** The same answer + evidence + rule
   pack always produces the same verdict. No model judges the output; a fixed rule
   set does. `make verify` re-derives committed example verdicts to byte-identical
   hashes.
2. **Every verdict is content-addressed and sealed.** Each receipt carries the
   hashes of the input, evidence, candidate, rules, and verdict, plus a
   `receipt_hash` over all of it. Editing any field breaks the hash.
3. **The ledger is tamper-evident.** Receipts are linked in a hash chain. Deleting,
   inserting, reordering, or editing an entry breaks the chain and is reported by
   replay.
4. **Verdicts are independently reproducible ("stranger trust").** `replay` and a
   self-verifying export bundle let a third party re-derive every verdict from the
   stored inputs, with no access to our systems, and get the identical result.
5. **For free-text answers, the extraction is sealed and replayable.** The prose is
   turned into a structured candidate deterministically; the extraction is hashed
   into the receipt and re-run during replay, so an edited answer is detected.

## What GroundLedger does NOT prove

- **It is not a compliance certification.** It produces evidence you can use in
  your own SOC 2 / ISO 42001 / EU AI Act process. It does not make you compliant
  and is not an audit opinion.
- **It is not tamper-proof.** "Tamper-evident" means a covered edit breaks an
  implemented integrity check. A motivated party who rewrites the stored receipts,
  the ledger chain, and (if used) re-signs with the signing key can produce an
  internally consistent forgery. The defense is detection and independent copies,
  not impossibility.
- **HMAC signing is keyed integrity, not non-repudiation.** Anyone holding the
  shared signing key can produce a valid signature. It is not public-key signing.
- **Free-text coverage is conservative.** The extractor reliably flags fabricated
  citations and contradictions on facts your evidence covers; it does not invent
  claims about subjects the evidence does not cover, so it under-reports rather
  than guesses. Absence of findings on free text is not proof of full grounding.
- **The verifier is narrow, not semantically complete.** It checks citation
  existence and claim/evidence agreement under explicit rules. It does not judge
  tone, completeness, or correctness beyond those rules.
- **It does not judge the model or the retrieval.** It judges the answer against
  the evidence you provide. Garbage evidence in, grounded-against-garbage out.

## Trusted vs. verified inputs and outputs

| Thing | Status |
|---|---|
| The answer text / candidate you submit | **Trusted input** - taken as given; never an answer key. |
| The evidence you submit | **Trusted input** - the verifier judges against it; it is the source of truth you assert. |
| The rule pack | **Trusted, inspectable** - plain JSON in `product/groundledger/rule_packs/`. |
| The verdict, family, severity | **Verified output** - deterministically derived; reproducible. |
| The receipt + ledger | **Verified, sealed** - content-addressed and hash-chained. |
| The audit report / export bundle | **Verified, self-checking** - re-derivable from embedded records. |
| The expected verdict / answer key | **Never seen by the verifier** - enforced by the research core's static and call-site guards (`sfa/invariants.py`). |

## How outputs are produced (the pipeline)

```
answer (+ citations or free text) + evidence + rule pack
      -> extraction (free text only; deterministic, sealed)
      -> deterministic verifier (sfa core; blind to answer key/history/metadata)
      -> sealed receipt -> hash-chained ledger
      -> audit report + signed self-verifying export bundle
      -> replay / verify (re-derives everything independently)
```

## What you can independently check

- Re-derive the committed examples and confirm the hashes match: `make verify`.
- Run the full product test suite: `make test`.
- Verify a signed export offline: `python -m product.groundledger.export verify bundle.json --key <key>`.
- Re-attest a tenant's whole ledger: `python -m product.groundledger.replay <data_root> <tenant>`.
- Read the rules: `product/groundledger/rule_packs/*.json`.
- Read the verifier itself: `sfa/verifier.py` (and the blindness guards it must pass).

## What could still go wrong (assumptions & boundaries)

- The signing key, if used, is a shared secret. If it leaks, signatures can be forged.
- The store is a filesystem the operator controls. Integrity is *evident* on
  replay, but an operator with write access can attempt forgery; the protection is
  that an outside copy + replay detects mismatch.
- The evidence you provide is assumed to be the real source. GroundLedger does not
  fetch or authenticate your documents.
- Determinism assumes the committed tool version and rule pack. A different version
  may produce different (still deterministic) hashes; the manifest pins the version.

## What you should not blindly trust

Don't trust a report we hand you on its own. Trust the report **plus** your own
run of `replay` / `export verify` on a machine we don't control, against your own
copy of the inputs. That is the entire point of the design.
