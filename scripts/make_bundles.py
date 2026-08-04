"""Build a clean FHIR R4 bundle and a drifted one carrying 12 planted defects.

Every defect here is one that passes JSON validation and, in most cases, passes a
structural FHIR validator too. They are the interoperability failures that only
show up when a second system tries to read the data - a payer rejecting a claim, a
registry dropping a patient, a quality measure quietly excluding half its cohort.
"""
import json, random, datetime as dt, os

random.seed(20260804)
os.makedirs("bundles", exist_ok=True)

N = 300
GENDERS = ["male", "female", "other", "unknown"]

# LOINC codes with their correct display strings
LOINC = {
    "8302-2": "Body height",
    "29463-7": "Body weight",
    "8480-6": "Systolic blood pressure",
    "8462-4": "Diastolic blood pressure",
    "2339-0": "Glucose [Mass/volume] in Blood",
}
UNITS = {"8302-2": "cm", "29463-7": "kg", "8480-6": "mm[Hg]", "8462-4": "mm[Hg]", "2339-0": "mg/dL"}
RANGE = {"8302-2": (140, 200), "29463-7": (45, 130), "8480-6": (95, 165),
         "8462-4": (55, 100), "2339-0": (70, 180)}

# ICD-10-CM conditions
ICD10 = {
    "E11.9": "Type 2 diabetes mellitus without complications",
    "I10": "Essential (primary) hypertension",
    "J45.909": "Unspecified asthma, uncomplicated",
    "M54.5": "Low back pain",
}

PLANTED = []
def note(did, resource, desc):
    PLANTED.append({"defect_id": did, "resource": resource, "description": desc})


def patient(i, sabotage=False):
    p = {
        "resourceType": "Patient",
        "id": f"pat-{i}",
        "identifier": [{"system": "http://hospital.example.org/mrn", "value": f"MRN{100000+i}"}],
        "active": True,
        "name": [{"family": f"Family{i}", "given": [f"Given{i}"]}],
        "gender": random.choice(GENDERS),
        "birthDate": (dt.date(1940, 1, 1) + dt.timedelta(days=random.randint(0, 30000))).isoformat(),
    }
    return p


def observation(i, pid, code, sabotage=False):
    lo, hi = RANGE[code]
    return {
        "resourceType": "Observation",
        "id": f"obs-{i}",
        "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                  "code": "vital-signs"}]}],
        "code": {"coding": [{"system": "http://loinc.org", "code": code, "display": LOINC[code]}]},
        "subject": {"reference": f"Patient/{pid}"},
        "effectiveDateTime": (dt.datetime(2026, 1, 1) + dt.timedelta(minutes=random.randint(0, 300000))
                              ).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "valueQuantity": {"value": round(random.uniform(lo, hi), 1),
                          "unit": UNITS[code], "system": "http://unitsofmeasure.org", "code": UNITS[code]},
    }


def condition(i, pid, code):
    return {
        "resourceType": "Condition",
        "id": f"cond-{i}",
        "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                                       "code": "active"}]},
        "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": code,
                             "display": ICD10[code]}]},
        "subject": {"reference": f"Patient/{pid}"},
        "recordedDate": (dt.date(2025, 1, 1) + dt.timedelta(days=random.randint(0, 500))).isoformat(),
    }


def build(sabotage: bool):
    # Reset the generator so both bundles share identical base data. Without this
    # the two files differ in ways that have nothing to do with the planted
    # defects, and any downstream comparison measures noise.
    random.seed(20260804)
    PLANTED.clear()
    entries = []
    for i in range(1, N + 1):
        entries.append({"resource": patient(i, sabotage)})
    oid = 1
    for i in range(1, N + 1):
        for code in random.sample(list(LOINC), k=random.randint(2, 4)):
            entries.append({"resource": observation(oid, f"pat-{i}", code, sabotage)})
            oid += 1
    cid = 1
    for i in range(1, N + 1):
        if random.random() < 0.6:
            entries.append({"resource": condition(cid, f"pat-{i}", random.choice(list(ICD10)))})
            cid += 1

    if sabotage:
        res = [e["resource"] for e in entries]
        pats = [r for r in res if r["resourceType"] == "Patient"]
        obs = [r for r in res if r["resourceType"] == "Observation"]
        conds = [r for r in res if r["resourceType"] == "Condition"]

        pats[3]["gender"] = "M"                                       # F1
        note("F1", "Patient", "gender 'M' instead of the required code 'male'")

        entries.append({"resource": dict(pats[10])})                  # F2
        note("F2", "Patient", "Patient/pat-11 appears twice with the same id")

        pats[20]["birthDate"] = "2039-04-11"                          # F3
        note("F3", "Patient", "birthDate in the future")

        del pats[30]["identifier"]                                    # F4
        note("F4", "Patient", "no MRN identifier - the record cannot be matched across systems")

        obs[5]["valueQuantity"]["unit"] = "in"                        # F5
        obs[5]["valueQuantity"]["code"] = "in"
        note("F5", "Observation", "body height reported in inches while the value is still a cm magnitude")

        obs[11]["code"]["coding"][0]["display"] = "Body mass index"   # F6
        note("F6", "Observation", "LOINC 29463-7 labelled 'Body mass index' - code and display disagree")

        # Planted on a glucose observation on purpose: these defects are only
        # interesting where they touch something a measure reads.
        glu = [o for o in obs if o["code"]["coding"][0]["code"] == "2339-0"]
        glu[3]["subject"]["reference"] = "Patient/pat-99999"           # F7
        note("F7", "Observation", "glucose result references a patient that is not in the bundle")

        obs[23]["valueQuantity"]["value"] = 4200.0                    # F8
        note("F8", "Observation", "systolic blood pressure of 4200 mm[Hg]")

        glu[9]["code"]["coding"][0]["system"] = "http://snomed.info/sct"   # F9
        note("F9", "Observation", "a glucose LOINC code declared under the SNOMED system URI")

        obs[35]["effectiveDateTime"] = "2026-03-04T11:20:00"          # F10
        note("F10", "Observation", "effectiveDateTime with no timezone offset")

        obs[41]["status"] = "FINAL"                                   # F11
        note("F11", "Observation", "status 'FINAL' - the value set is lowercase")

        dm = [c for c in conds if c["code"]["coding"][0]["code"] == "E11.9"]
        for c in dm[:3]:                                               # F12
            c["code"]["coding"][0]["code"] = "E119"
        note("F12", "Condition", "three type-2 diabetes codes written 'E119' with no decimal point")

    bundle = {"resourceType": "Bundle", "type": "collection", "entry": entries}
    return bundle, list(PLANTED)


clean, _ = build(False)
json.dump(clean, open("bundles/clean.json", "w"), indent=1)
drift, planted = build(True)
json.dump(drift, open("bundles/drifted.json", "w"), indent=1)
json.dump(planted, open("bundles/planted_defects.json", "w"), indent=1)
print(f"clean {len(clean['entry'])} entries, drifted {len(drift['entry'])} entries, "
      f"{len(planted)} defects planted")
