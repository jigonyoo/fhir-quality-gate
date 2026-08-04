#!/usr/bin/env bash
set -uo pipefail
mkdir -p evidence
python3 scripts/make_bundles.py
echo
echo "=== clean bundle ==="
python3 -m fhirgate.cli bundles/clean.json --today 2026-08-04 | tee evidence/clean.txt
echo
echo "=== drifted bundle ==="
python3 -m fhirgate.cli bundles/drifted.json --today 2026-08-04 | tee evidence/drifted.txt
echo
echo "=== what a quality measure computes on each ==="
python3 scripts/cohort_impact.py bundles/clean.json bundles/drifted.json | tee evidence/cohort.txt
echo
echo "=== coverage assertion ==="
python3 tests/test_checks.py | tee evidence/coverage.txt
