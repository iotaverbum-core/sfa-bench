"""GroundLedger Python SDK.

A thin, dependency-free client a design partner can drop into a RAG pipeline in
an afternoon. Two transports, one interface:

    from product.sdk import GroundLedgerClient

    # Embedded: no server, writes a sealed ledger to a local directory.
    gl = GroundLedgerClient.embedded(data_root="gl-data", tenant="acme",
                                     rule_pack="insurance_v1")

    # Or against an in-VPC GroundLedger API.
    gl = GroundLedgerClient.http(base_url="http://localhost:8000",
                                 api_key="prod-key", rule_pack="insurance_v1")

    receipt = gl.verify(answer_id="ans_1", candidate=answer, evidence=chunks)
    if not gl.is_grounded(receipt):
        log.warning("ungrounded answer: %s", receipt["explanation"])
"""
from .client import GroundLedgerClient, GroundLedgerError

__all__ = ["GroundLedgerClient", "GroundLedgerError"]
