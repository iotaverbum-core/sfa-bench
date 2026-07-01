"""GroundLedger HTTP API - stdlib only, zero dependencies.

A deliberately tiny ``http.server`` backend so the whole thing can run inside a
customer VPC with no network egress and no package install. It is not a
high-scale server; it is the smallest honest "SaaS surface" over the engine.

The JSON API selects the tenant with the ``X-API-Key`` header. The two
human-facing HTML pages (``/`` and ``/v1/report.html``) also accept the key as a
``?key=`` query parameter so a non-engineer can open a link in a browser. Keys in
URLs can end up in logs; use the report view only inside a trusted network (see
``SECURITY.md``).

Endpoints:

  GET  /                                            -> HTML start page (open)
  GET  /v1/report.html   [key]                      -> HTML audit report (browser view)
  POST /v1/verify         body = submission         -> { receipt }
  POST /v1/verify-text    body = text submission    -> { receipt }
  POST /v1/ingest         body = { records: [...] }  -> ingest summary
  GET  /v1/receipts                                 -> { receipts: [...] }
  GET  /v1/audit-report                             -> audit report
  GET  /v1/audit-export                             -> self-contained signed bundle
  POST /v1/replay                                   -> attestation
  GET  /v1/rule-packs                               -> available packs
  GET  /healthz                                     -> { ok: true }
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import engine, export as export_mod, ingest as ingest_mod, report as report_mod, replay, rulepacks
from .store import TenantStore

DEFAULT_KEYS = {"demo-key": "demo-tenant"}

_PAGE_CSS = (
    "body{font:15px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#0f172a;"
    "max-width:640px;margin:60px auto;padding:0 20px;}"
    "h1{letter-spacing:-.02em;} .muted{color:#64748b;font-size:13px;}"
    "input,button{font:inherit;padding:9px 12px;border-radius:8px;border:1px solid #cbd5e1;}"
    "button{background:#1d4ed8;color:#fff;border-color:#1d4ed8;cursor:pointer;}"
    "code{background:#f1f5f9;padding:1px 5px;border-radius:4px;}"
)

INDEX_HTML = (
    "<!doctype html><html><head><meta charset='utf-8'><title>GroundLedger</title>"
    f"<style>{_PAGE_CSS}</style></head><body>"
    "<h1>GroundLedger</h1>"
    "<p>Groundedness audit for document-grounded AI, running in your environment. "
    "Enter your API key to view your audit report.</p>"
    "<form action='/v1/report.html' method='get'>"
    "<input name='key' placeholder='API key' size='28' autofocus> "
    "<button type='submit'>View audit report</button></form>"
    "<p class='muted' style='margin-top:22px;'>Machine endpoints: <code>/healthz</code>, "
    "<code>/v1/rule-packs</code>, and the JSON API. No model calls, no network egress.</p>"
    "</body></html>"
)

NEEDS_KEY_HTML = (
    "<!doctype html><html><head><meta charset='utf-8'><title>GroundLedger - key required</title>"
    f"<style>{_PAGE_CSS}</style></head><body>"
    "<h1>API key required</h1>"
    "<p>Add <code>?key=YOUR_KEY</code> to the URL, or start from "
    "<a href='/'>the start page</a>.</p></body></html>"
)


def _parse_pairs(raw: str) -> dict[str, str]:
    """Parse a 'k1:v1,k2:v2' env string into a dict."""
    out: dict[str, str] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        key, value = item.split(":", 1)
        out[key.strip()] = value.strip()
    return out


def make_handler(
    *,
    data_root: str,
    api_keys: dict[str, str],
    packs_dir: str | None = None,
    signing_keys: dict[str, str] | None = None,
):
    signing_keys = signing_keys or {}
    class Handler(BaseHTTPRequestHandler):
        server_version = "GroundLedger/0.1"

        def _tenant(self) -> str | None:
            key = self.headers.get("X-API-Key", "")
            if not key:  # allow ?key= for browser-opened HTML views
                key = parse_qs(urlparse(self.path).query).get("key", [""])[0]
            return api_keys.get(key)

        def _send(self, code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, code: int, html: str) -> None:
            body = html.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", 0) or 0)
            if not length:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def _resolver(self):
            return lambda pid: rulepacks.load_rule_pack(pid, packs_dir=packs_dir)

        def log_message(self, *args):  # silence default stderr logging
            return

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/healthz":
                self._send(200, {"ok": True})
                return
            if path == "/":
                self._send_html(200, INDEX_HTML)
                return
            if path == "/v1/rule-packs":
                self._send(200, {"rule_packs": rulepacks.list_rule_packs(packs_dir=packs_dir)})
                return
            tenant = self._tenant()
            if tenant is None:
                if path == "/v1/report.html":
                    self._send_html(401, NEEDS_KEY_HTML)
                else:
                    self._send(401, {"error": "invalid or missing X-API-Key"})
                return
            store = TenantStore(data_root, tenant)
            if path == "/v1/report.html":
                bundle = export_mod.build_export_bundle(
                    store, packs_dir=packs_dir, signing_key=signing_keys.get(tenant)
                )
                self._send_html(200, export_mod.render_html(bundle))
            elif path == "/v1/receipts":
                self._send(200, {"receipts": store.list_receipts()})
            elif path == "/v1/audit-report":
                self._send(200, report_mod.build_report(store, packs_dir=packs_dir))
            elif path == "/v1/audit-export":
                bundle = export_mod.build_export_bundle(
                    store, packs_dir=packs_dir, signing_key=signing_keys.get(tenant)
                )
                self._send(200, bundle)
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            tenant = self._tenant()
            if tenant is None:
                self._send(401, {"error": "invalid or missing X-API-Key"})
                return
            store = TenantStore(data_root, tenant)
            try:
                if self.path == "/v1/verify":
                    submission = self._body()
                    pack_id = submission.get("rule_pack", "insurance_v1")
                    rule_pack = rulepacks.load_rule_pack(pack_id, packs_dir=packs_dir)
                    receipt = engine.verify_submission(submission, rule_pack)
                    store.record(submission, receipt)
                    self._send(200, {"receipt": receipt})
                elif self.path == "/v1/verify-text":
                    submission = self._body()
                    pack_id = submission.get("rule_pack", "insurance_v1")
                    rule_pack = rulepacks.load_rule_pack(pack_id, packs_dir=packs_dir)
                    receipt, stored = engine.verify_text_submission(submission, rule_pack)
                    store.record(stored, receipt)
                    self._send(200, {"receipt": receipt})
                elif self.path == "/v1/ingest":
                    body = self._body()
                    records = body.get("records", [])
                    parsed = [(f"record {i}", rec, None) for i, rec in enumerate(records)]
                    result = ingest_mod.ingest(
                        store, parsed,
                        default_rule_pack=body.get("rule_pack", "insurance_v1"),
                        packs_dir=packs_dir,
                    )
                    self._send(200, result)
                elif self.path == "/v1/replay":
                    self._send(200, replay.attest(store, self._resolver()))
                else:
                    self._send(404, {"error": "not found"})
            except (engine.SubmissionError, rulepacks.RulePackError, ValueError) as exc:
                self._send(400, {"error": str(exc)})

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8000, *, data_root: str = "product/data",
          api_keys: dict[str, str] | None = None, packs_dir: str | None = None,
          signing_keys: dict[str, str] | None = None) -> ThreadingHTTPServer:
    handler = make_handler(
        data_root=data_root,
        api_keys=api_keys or DEFAULT_KEYS,
        packs_dir=packs_dir,
        signing_keys=signing_keys,
    )
    return ThreadingHTTPServer((host, port), handler)


def _serve_from_env() -> ThreadingHTTPServer:
    host = os.environ.get("GROUNDLEDGER_HOST", "127.0.0.1")
    port = int(os.environ.get("GROUNDLEDGER_PORT", "8000"))
    data_root = os.environ.get("GROUNDLEDGER_DATA", "product/data")
    api_keys = _parse_pairs(os.environ.get("GROUNDLEDGER_API_KEYS", "")) or DEFAULT_KEYS
    signing_keys = _parse_pairs(os.environ.get("GROUNDLEDGER_SIGNING_KEYS", ""))
    Path(data_root).mkdir(parents=True, exist_ok=True)
    httpd = serve(host, port, data_root=data_root, api_keys=api_keys, signing_keys=signing_keys)
    view = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    print(f"GroundLedger API on http://{host}:{port}  (data: {data_root})")
    print(f"  report view: http://{view}:{port}/  (enter an API key)")
    return httpd


if __name__ == "__main__":
    server = _serve_from_env()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
