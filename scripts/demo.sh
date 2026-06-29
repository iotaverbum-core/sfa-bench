#!/usr/bin/env bash
# GroundLedger Phase 1 demo - the one command to run on a sales call.
#
#   ./scripts/demo.sh
#
# Verifies sample insurance answers, writes a customer-facing audit report
# (product/data/demo/report.html) and a signed, self-verifying bundle, and
# shows the tamper-detection moment. No network, no model calls, no dependencies.
set -euo pipefail

cd "$(dirname "$0")/.."

python3 -m product.demo

REPORT="product/data/demo/report.html"
echo
echo "Open the customer-facing report:"
echo "  $REPORT"

# Best-effort: open it locally if a desktop opener is available (ignored in CI).
if command -v open >/dev/null 2>&1; then
  open "$REPORT" >/dev/null 2>&1 || true
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$REPORT" >/dev/null 2>&1 || true
fi
