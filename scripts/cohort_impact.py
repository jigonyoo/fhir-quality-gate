"""What the defects do to one quality measure.

The measure: adult patients with an active type 2 diabetes diagnosis (ICD-10 E11.9)
who have at least one glucose result on file. A naive implementation trusts the
bundle. This prints what it computes on each bundle, without raising anything.
"""
import json, sys
from collections import defaultdict

def cohort(path):
    b = json.load(open(path))
    res = [e.get("resource", {}) for e in b.get("entry", [])]
    patients, dx, glucose = set(), set(), set()
    for r in res:
        t = r.get("resourceType")
        if t == "Patient":
            patients.add(r.get("id"))
        elif t == "Condition":
            c = (r.get("code", {}).get("coding") or [{}])[0]
            if c.get("code") == "E11.9":                       # exact match, as written
                dx.add(r.get("subject", {}).get("reference", "").split("/")[-1])
        elif t == "Observation":
            c = (r.get("code", {}).get("coding") or [{}])[0]
            if c.get("code") == "2339-0" and c.get("system") == "http://loinc.org":
                glucose.add(r.get("subject", {}).get("reference", "").split("/")[-1])
    num = dx & glucose & patients
    den = dx & patients
    return len(patients), len(den), len(num), (len(num) / len(den) * 100 if den else 0)

print(f"{'bundle':<22}{'patients':>10}{'denominator':>13}{'numerator':>11}{'measure':>10}")
for p in sys.argv[1:]:
    n, d, num, pct = cohort(p)
    print(f"{p:<22}{n:>10,}{d:>13,}{num:>11,}{pct:>9.1f}%")
print("\nNeither run raised an error. Both look like a measure result.")
