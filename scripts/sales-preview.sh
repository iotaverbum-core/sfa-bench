#!/usr/bin/env bash
# Open the pilot landing page and one-pager locally for a quick read.
#   ./scripts/sales-preview.sh
set -euo pipefail
cd "$(dirname "$0")/.."

LANDING="product/sales/landing/pilot.html"
ONEPAGER="product/sales/pilot/one-pager.html"

echo "Sales assets:"
echo "  Landing page : $LANDING"
echo "  One-pager    : $ONEPAGER"
echo "  All assets   : product/sales/  (see product/sales/SALES_LAUNCH_README.md)"

open_one() {
  if command -v open >/dev/null 2>&1; then open "$1" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$1" >/dev/null 2>&1 || true
  else echo "  (open $1 in your browser)"; fi
}
open_one "$LANDING"
open_one "$ONEPAGER"
