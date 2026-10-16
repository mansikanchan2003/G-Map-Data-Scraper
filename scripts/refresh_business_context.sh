#!/bin/sh
# Refresh the growth agent's business data from Tara and hand it to the
# backend. Read-only on Tara; the export writes totals only. Runs from cron
# on the host (kapil cannot write data/, so the file goes in by docker cp).
set -e
cd "$(dirname "$0")/.."
out=/tmp/autogmap_business_context.json
python3 scripts/export_business_context.py --out "$out"
docker cp "$out" autogmap-backend-1:/app/data/business_context.json
echo "$(date '+%F %T') business context refreshed"
