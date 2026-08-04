"""fhir-gate: read a FHIR bundle, report interoperability defects, exit non-zero."""
from __future__ import annotations
import argparse, json, sys, datetime as dt
from .checks import run_checks


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="fhir-gate")
    p.add_argument("bundles", nargs="+")
    p.add_argument("--today", default=None, help="ISO date used for date checks")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()

    total = 0
    for path in a.bundles:
        bundle = json.load(open(path))
        findings = run_checks(bundle, today)
        total += len(findings)
        n = len(bundle.get("entry", []))
        head = f"{path}  ({n:,} entries)"
        print(head); print("-" * len(head))
        if not findings:
            print("  no interoperability defects found\n"); continue
        if a.json:
            print(json.dumps(findings, indent=2)); continue
        for f in findings:
            print(f"  [{f['severity'].upper():8}] {f['check_id']}  {f['resource']} - {f['title']}")
            print(f"             {f['evidence']}")
            print(f"             impact: {f['impact']}")
            print(f"             fix:    {f['fix']}")
        print(f"\n  {len(findings)} defect(s)\n")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
