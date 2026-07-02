"""GroundLedger client and transports."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from product.groundledger import assisted as assisted_mod, engine, export as export_mod, ingest as ingest_mod, replay, report as report_mod, rulepacks
from product.groundledger.store import TenantStore


class GroundLedgerError(Exception):
    """Raised on a transport or validation failure."""


class _EmbeddedTransport:
    """In-process transport: verify and seal directly to a local store."""

    def __init__(self, data_root: str, tenant: str, *, packs_dir: str | None = None,
                 signing_key: str | None = None):
        self.store = TenantStore(data_root, tenant)
        self.packs_dir = packs_dir
        self.signing_key = signing_key

    def submit(self, submission: dict[str, Any]) -> dict[str, Any]:
        pack_id = submission.get("rule_pack", "insurance_v1")
        rule_pack = rulepacks.load_rule_pack(pack_id, packs_dir=self.packs_dir)
        receipt = engine.verify_submission(submission, rule_pack)
        self.store.record(submission, receipt)
        return receipt

    def submit_text(self, submission: dict[str, Any]) -> dict[str, Any]:
        pack_id = submission.get("rule_pack", "insurance_v1")
        rule_pack = rulepacks.load_rule_pack(pack_id, packs_dir=self.packs_dir)
        receipt, stored = engine.verify_text_submission(submission, rule_pack)
        self.store.record(stored, receipt)
        return receipt

    def ingest(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        parsed = [(f"record {i}", rec, None) for i, rec in enumerate(records)]
        return ingest_mod.ingest(self.store, parsed, packs_dir=self.packs_dir)

    def receipts(self) -> list[dict[str, Any]]:
        return self.store.list_receipts()

    def audit_report(self) -> dict[str, Any]:
        return report_mod.build_report(self.store, packs_dir=self.packs_dir)

    def audit_export(self) -> dict[str, Any]:
        return export_mod.build_export_bundle(
            self.store, packs_dir=self.packs_dir, signing_key=self.signing_key
        )

    def replay(self) -> dict[str, Any]:
        resolver = (lambda pid: rulepacks.load_rule_pack(pid, packs_dir=self.packs_dir))
        return replay.attest(self.store, resolver)


class _HttpTransport:
    """Talks to a running GroundLedger API. Bypasses env proxies (in-VPC/localhost)."""

    def __init__(self, base_url: str, api_key: str, *, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            self.base_url + path, data=data, method=method,
            headers={"X-API-Key": self.api_key, "Content-Type": "application/json"},
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise GroundLedgerError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise GroundLedgerError(f"cannot reach {self.base_url}: {exc.reason}") from exc

    def submit(self, submission: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/verify", submission)["receipt"]

    def submit_text(self, submission: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/verify-text", submission)["receipt"]

    def ingest(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        return self._request("POST", "/v1/ingest", {"records": records})

    def receipts(self) -> list[dict[str, Any]]:
        return self._request("GET", "/v1/receipts")["receipts"]

    def audit_report(self) -> dict[str, Any]:
        return self._request("GET", "/v1/audit-report")

    def audit_export(self) -> dict[str, Any]:
        return self._request("GET", "/v1/audit-export")

    def replay(self) -> dict[str, Any]:
        return self._request("POST", "/v1/replay")


class GroundLedgerClient:
    """One interface over the embedded or HTTP transport."""

    def __init__(self, transport: Any, *, default_rule_pack: str = "insurance_v1"):
        self._t = transport
        self.default_rule_pack = default_rule_pack

    @classmethod
    def embedded(cls, data_root: str, tenant: str, *, rule_pack: str = "insurance_v1",
                 packs_dir: str | None = None, signing_key: str | None = None) -> "GroundLedgerClient":
        transport = _EmbeddedTransport(data_root, tenant, packs_dir=packs_dir, signing_key=signing_key)
        return cls(transport, default_rule_pack=rule_pack)

    @classmethod
    def http(cls, base_url: str, api_key: str, *, rule_pack: str = "insurance_v1",
             timeout: float = 10.0) -> "GroundLedgerClient":
        return cls(_HttpTransport(base_url, api_key, timeout=timeout), default_rule_pack=rule_pack)

    def verify(self, *, answer_id: str, candidate: dict[str, Any], evidence: dict[str, Any],
               task_input: dict[str, Any] | None = None, rule_pack: str | None = None) -> dict[str, Any]:
        """Verify one answer and append it to the sealed audit ledger."""
        submission = {
            "answer_id": answer_id,
            "rule_pack": rule_pack or self.default_rule_pack,
            "candidate": candidate,
            "evidence": evidence,
        }
        if task_input is not None:
            submission["task_input"] = task_input
        return self._t.submit(submission)

    def verify_text(self, *, answer_id: str, answer_text: str, evidence: dict[str, Any],
                    task_input: dict[str, Any] | None = None, rule_pack: str | None = None) -> dict[str, Any]:
        """Verify a free-text answer: extract a structured candidate, then judge it."""
        submission = {
            "answer_id": answer_id,
            "rule_pack": rule_pack or self.default_rule_pack,
            "answer_text": answer_text,
            "evidence": evidence,
        }
        if task_input is not None:
            submission["task_input"] = task_input
        return self._t.submit_text(submission)

    def ingest_records(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Bulk-verify a list of submission dicts; returns an ingest summary."""
        prepared = []
        for record in records:
            record = dict(record)
            record.setdefault("rule_pack", self.default_rule_pack)
            prepared.append(record)
        return self._t.ingest(prepared)

    def ingest_file(self, path: str, *, fmt: str = "auto") -> dict[str, Any]:
        """Parse a JSONL/CSV file locally and bulk-ingest it (any transport)."""
        parsed = ingest_mod.parse_source(path, fmt)
        submissions = [sub for _ref, sub, err in parsed if err is None and sub is not None]
        parse_errors = [
            {"ref": ref, "answer_id": None, "error": err}
            for ref, _sub, err in parsed if err is not None
        ]
        result = self.ingest_records(submissions)
        if parse_errors:
            result = {**result, "errors": parse_errors + list(result.get("errors", []))}
        return result

    def verify_text_assisted(self, *, answer_id: str, answer_text: str, evidence: dict[str, Any],
                             suggest, task_input: dict[str, Any] | None = None,
                             rule_pack: str | None = None, allow_in_ci: bool = False) -> dict[str, Any]:
        """Verify a free-text answer with an LLM-assisted proposer.

        The model (``suggest``) runs here, in your environment. Its nominations are
        sealed into the submission and re-checked deterministically by the verifier
        boundary - the server/engine never calls a model. Works over both transports.
        """
        submission = assisted_mod.build_text_submission(
            answer_id=answer_id, answer_text=answer_text, evidence=evidence,
            suggest=suggest, rule_pack=rule_pack or self.default_rule_pack,
            task_input=task_input, allow_in_ci=allow_in_ci,
        )
        return self._t.submit_text(submission)

    def submit(self, submission: dict[str, Any]) -> dict[str, Any]:
        """Verify a fully-formed submission dict."""
        submission.setdefault("rule_pack", self.default_rule_pack)
        return self._t.submit(submission)

    def receipts(self) -> list[dict[str, Any]]:
        return self._t.receipts()

    def audit_report(self) -> dict[str, Any]:
        return self._t.audit_report()

    def audit_export(self) -> dict[str, Any]:
        """Return the portable, self-verifying audit bundle."""
        return self._t.audit_export()

    def replay(self) -> dict[str, Any]:
        """Independently re-attest the ledger."""
        return self._t.replay()

    @staticmethod
    def is_grounded(receipt: dict[str, Any]) -> bool:
        return receipt.get("status") == "PASS"
