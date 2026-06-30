#!/usr/bin/env bash
# Export a printable sales HTML to PDF using headless Chrome/Chromium.
#   ./scripts/pilot-pdf.sh                                   # the one-pager (default)
#   ./scripts/pilot-pdf.sh product/sales/pilot/order-form.html
# Falls back with instructions if no Chrome/Chromium is found (open the HTML and
# use the browser's Print > Save as PDF).
set -euo pipefail
cd "$(dirname "$0")/.."

SRC="${1:-product/sales/pilot/one-pager.html}"
OUT="${SRC%.html}.pdf"

find_chrome() {
  for c in google-chrome-stable google-chrome chromium chromium-browser chrome; do
    if command -v "$c" >/dev/null 2>&1; then command -v "$c"; return 0; fi
  done
  for g in /opt/pw-browsers/chromium-*/chrome-linux/chrome \
           /opt/pw-browsers/chromium_headless_shell-*/chrome-linux*/headless_shell; do
    if [ -x "$g" ]; then echo "$g"; return 0; fi
  done
  return 1
}

if CHROME="$(find_chrome)"; then
  "$CHROME" --headless=new --no-sandbox --disable-gpu \
    --print-to-pdf="$OUT" "file://$PWD/$SRC" >/dev/null 2>&1 || \
  "$CHROME" --headless --no-sandbox --disable-gpu \
    --print-to-pdf="$OUT" "file://$PWD/$SRC" >/dev/null 2>&1
  if [ -f "$OUT" ]; then
    echo "Wrote $OUT"
  else
    echo "Chrome ran but no PDF was produced. Open $SRC and use Print > Save as PDF."
    exit 1
  fi
else
  echo "No Chrome/Chromium found."
  echo "Open $SRC in your browser and use Print > Save as PDF (A4/Letter, default margins)."
  exit 1
fi
