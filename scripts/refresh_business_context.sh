#!/bin/sh
# Refresh the growth agent's business data from Tara and hand it to the
# backend. Read-only on Tara (the export reads a private copy of its
# database); the export writes totals only.
#
# Runs daily from root's crontab at 04:30 IST, after Sumit's sheets update at
# 04:00. It ran from kapil's crontab until the repo became root-only, after
# which it failed silently from 17 Oct 2026; the Plan tab now warns when
# Tara's figures fall behind.
set -e
cd "$(dirname "$0")/.."
out=/tmp/autogmap_business_context.json
python3 scripts/export_business_context.py --out "$out"
docker cp "$out" autogmap-backend-1:/app/data/business_context.json
echo "$(date '+%F %T') business context refreshed"
