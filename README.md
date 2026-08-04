# fhir-quality-gate

**A FHIR bundle can be structurally valid and still be wrong in ways that cost money.**

The drifted bundle in this repo is valid JSON, valid FHIR R4, and would pass a
structural validator. It also contains three type-2 diabetes diagnoses written
`E119` instead of `E11.9` — enough to drop **3 patients out of a 46-patient quality
measure denominator** without raising anything at all.

`fhir-gate` catches **12 of 12** planted defect types and raises **0** on the clean bundle.

---

## Measured result

```
planted defect types      : 12
detected                  : 12
missed                    : none
findings on clean bundle  : 0
total findings on drifted : 14

OK  12/12 defect types caught, 0 false alarms
```

Both bundles carry **identical base data** — same 300 patients, same observations,
same seed. Every difference below is a planted defect, not sampling noise.

### What a quality measure computes on each

Measure: adults with active type-2 diabetes (E11.9) who have a glucose result on file.

| bundle | patients | denominator | numerator | measure |
|---|---:|---:|---:|---:|
| clean | 300 | 46 | 26 | **56.5%** |
| drifted | 300 | **43** | **24** | **55.8%** |

**Neither run raised an error.** Both produce a number that looks like a measure
result. Three patients left the denominator because of a missing decimal point, and
two glucose results vanished — one referencing a patient not in the bundle, one
labelled with the SNOMED system URI instead of LOINC.

```bash
./scripts/run_evidence.sh          # everything, into evidence/
python3 -m fhirgate.cli bundles/drifted.json --today 2026-08-04
```

No dependencies beyond the standard library.

---

## The 12 checks

| # | Severity | What it catches | Why the receiving system cares |
|---|---|---|---|
| F2 | critical | duplicate resource id in one bundle | The patient is counted twice in every measure, or the second copy overwrites the first |
| F4 | critical | Patient with no identifier | Cannot be matched across systems — becomes a new patient on every import |
| F5 | critical | unit does not match the LOINC code | A height of 170 becomes 170 inches |
| F7 | critical | subject reference points outside the bundle | Orphaned — drops out of every per-patient roll-up |
| F8 | critical | value outside the plausible band | Systolic 4200 mm[Hg] moves a cohort mean and can fire a clinical alert |
| F9 | critical | LOINC code declared under the SNOMED system URI | Receivers filtering by system find nothing — invisible, not wrong |
| F12 | critical | ICD-10-CM without its decimal point | Payers reject the claim; the diagnosis never reaches the registry |
| F1 | high | gender outside the required value set (`M` not `male`) | Rejected, or silently coerced to `unknown` |
| F3 | high | birthDate in the future | Age-banded measures exclude the patient; paediatric logic may fire |
| F6 | high | code and display disagree | Humans read one thing, systems compute another |
| F10 | high | dateTime with no timezone offset | A 23:00 result lands on the wrong day in the receiver's timezone |
| F11 | high | status `FINAL` where the value set is lowercase | A finalised result is treated as missing |

Three of these are the ones that show up in real integration work.

**F9 makes data invisible rather than wrong.** A glucose result carrying LOINC
`2339-0` under `http://snomed.info/sct` is not rejected by anything — it simply never
matches a query filtering on `system = 'http://loinc.org'`. Nothing errors. The
result is just not there. This is the failure mode that takes weeks to find, because
every individual record looks fine when you open it.

**F5 is the one that reaches a patient.** The unit says inches, the magnitude is still
centimetres. Downstream BMI is computed from a height of 170 inches. No validator
objects, because `in` is a perfectly good UCUM unit.

**F12 is the cheapest to fix and the most expensive to miss.** `E119` is four
characters that a payer's adjudication engine rejects outright. Here it removed three
patients from a 46-patient denominator — a 6.5% shift in the cohort, from one missing
period.

---

## What this is not

This is **not** a FHIR structural validator. It assumes the bundle already parses and
already conforms to R4 — use the HL7 validator for that. These checks sit one layer
up, where the resource is valid and the meaning is still wrong.

Terminology is pinned in `fhirgate/checks.py` rather than fetched, so the repo runs
offline and the result is reproducible. In production those tables come from a
terminology server; the check logic does not change.

---

## Layout

```
bundles/
  clean.json               300 patients, no defects
  drifted.json             identical base data, 12 defect types planted
  planted_defects.json     the ground truth the test asserts against
fhirgate/
  checks.py                the 12 checks, each with evidence + impact + fix
  cli.py                   exits non-zero on any finding
scripts/
  make_bundles.py          deterministic generator, seed 20260804
  cohort_impact.py         what a quality measure computes on each bundle
  run_evidence.sh          reruns everything into evidence/
tests/test_checks.py       asserts 12/12 caught, 0 false alarms
```
