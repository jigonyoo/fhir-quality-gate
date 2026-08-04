"""Twelve defects planted, twelve check families. Both directions asserted."""
import json, sys, os, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fhirgate import run_checks

TODAY = dt.date(2026, 8, 4)
clean = run_checks(json.load(open("bundles/clean.json")), TODAY)
drift = run_checks(json.load(open("bundles/drifted.json")), TODAY)
planted = json.load(open("bundles/planted_defects.json"))

want = {p["defect_id"] for p in planted}
got = {f["check_id"] for f in drift}
missed = sorted(want - got, key=lambda x: int(x[1:]))

print(f"planted defect types      : {len(want)}")
print(f"detected                  : {len(want & got)}")
print(f"missed                    : {missed or 'none'}")
print(f"findings on clean bundle  : {len(clean)}")
print(f"total findings on drifted : {len(drift)}")
assert not clean, "a check fired on the clean bundle"
assert not missed, f"missed {missed}"
print(f"\nOK  {len(want)}/{len(want)} defect types caught, 0 false alarms")
