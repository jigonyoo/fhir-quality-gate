"""Twelve interoperability checks on a FHIR R4 bundle.

Structural validators answer "is this valid FHIR?". These answer the question that
actually costs money: "will the system on the other end read this the way we meant?"
A bundle can be structurally perfect and still lose half a quality-measure cohort
because one code was written without its decimal point.
"""
from __future__ import annotations
import re, datetime as dt
from collections import Counter, defaultdict

# --------------------------------------------------------------------------- #
# Terminology the checks lean on. In production these come from a terminology
# server; pinned here so the repo runs offline and the result is reproducible.

GENDER_VS = {"male", "female", "other", "unknown"}
OBS_STATUS_VS = {"registered", "preliminary", "final", "amended",
                 "corrected", "cancelled", "entered-in-error", "unknown"}

LOINC_DISPLAY = {
    "8302-2": "Body height",
    "29463-7": "Body weight",
    "8480-6": "Systolic blood pressure",
    "8462-4": "Diastolic blood pressure",
    "2339-0": "Glucose [Mass/volume] in Blood",
}
LOINC_UNIT = {"8302-2": "cm", "29463-7": "kg", "8480-6": "mm[Hg]",
              "8462-4": "mm[Hg]", "2339-0": "mg/dL"}
# Physiologically plausible bands. Outside these a value is a data-entry or unit error,
# not a sick patient.
LOINC_RANGE = {"8302-2": (40, 250), "29463-7": (1, 400), "8480-6": (50, 300),
               "8462-4": (20, 200), "2339-0": (10, 900)}

LOINC_SYSTEM = "http://loinc.org"
ICD10_SYSTEM = "http://hl7.org/fhir/sid/icd-10-cm"
ICD10_RE = re.compile(r"^[A-TV-Z][0-9][0-9AB](\.[0-9A-TV-Z]{1,4})?$")
TZ_RE = re.compile(r"(Z|[+-]\d{2}:\d{2})$")


def _f(fid, severity, resource, title, evidence, impact, fix):
    return {"check_id": fid, "severity": severity, "resource": resource, "title": title,
            "evidence": evidence, "impact": impact, "fix": fix}


def _res(bundle):
    return [e.get("resource", {}) for e in bundle.get("entry", [])]


def _coding(r, path="code"):
    try:
        return r[path]["coding"][0]
    except Exception:
        return {}


# --------------------------------------------------------------------------- #

def f1_gender_code(res, ctx):
    out = []
    for r in res:
        if r.get("resourceType") != "Patient":
            continue
        g = r.get("gender")
        if g is not None and g not in GENDER_VS:
            out.append(_f("F1", "high", f"Patient/{r.get('id')}",
                          "gender outside the required value set",
                          f"gender={g!r}, allowed {sorted(GENDER_VS)}",
                          "Receiving systems reject the resource or coerce it to 'unknown'.",
                          "Map the source value; 'M'/'F' are not FHIR codes."))
    return out


def f2_duplicate_id(res, ctx):
    seen = Counter((r.get("resourceType"), r.get("id")) for r in res if r.get("id"))
    dupes = [k for k, n in seen.items() if n > 1]
    return [_f("F2", "critical", f"{t}/{i}", "duplicate resource id in one bundle",
               f"{t}/{i} appears {seen[(t, i)]} times",
               "The second copy overwrites the first, or the patient is counted twice in every measure.",
               "De-duplicate before transmission; ids must be unique within a bundle.")
            for t, i in dupes]


def f3_future_birthdate(res, ctx):
    out = []
    for r in res:
        if r.get("resourceType") != "Patient" or not r.get("birthDate"):
            continue
        try:
            d = dt.date.fromisoformat(r["birthDate"])
        except ValueError:
            continue
        if d > ctx["today"]:
            out.append(_f("F3", "high", f"Patient/{r.get('id')}", "birthDate in the future",
                          f"birthDate={r['birthDate']}",
                          "Age-banded measures silently exclude the patient; paediatric logic may fire.",
                          "Reject at intake - a future birth date is never a valid record."))
    return out


def f4_missing_identifier(res, ctx):
    out = []
    for r in res:
        if r.get("resourceType") != "Patient":
            continue
        if not r.get("identifier"):
            out.append(_f("F4", "critical", f"Patient/{r.get('id')}",
                          "Patient with no identifier",
                          "identifier is absent",
                          "The record cannot be matched to the same person in any other system; it becomes a new patient on every import.",
                          "Require at least one identifier with a system URI before export."))
    return out


def f5_unit_mismatch(res, ctx):
    out = []
    for r in res:
        if r.get("resourceType") != "Observation":
            continue
        c = _coding(r)
        code, vq = c.get("code"), r.get("valueQuantity", {})
        expected = LOINC_UNIT.get(code)
        if expected and vq.get("unit") and vq["unit"] != expected:
            out.append(_f("F5", "critical", f"Observation/{r.get('id')}",
                          "unit does not match the unit expected for this LOINC code",
                          f"LOINC {code} ({LOINC_DISPLAY.get(code)}): unit={vq['unit']!r}, expected {expected!r}, value={vq.get('value')}",
                          "The magnitude is read on the wrong scale - a height of 170 becomes 170 inches.",
                          "Convert to the expected UCUM unit, or reject."))
    return out


def f6_display_mismatch(res, ctx):
    out = []
    for r in res:
        if r.get("resourceType") != "Observation":
            continue
        c = _coding(r)
        code, disp = c.get("code"), c.get("display")
        want = LOINC_DISPLAY.get(code)
        if want and disp and disp != want:
            out.append(_f("F6", "high", f"Observation/{r.get('id')}",
                          "code and display disagree",
                          f"LOINC {code} carries display {disp!r}; the code means {want!r}",
                          "Humans reading the chart see one thing, systems reading the code compute another.",
                          "Take display from the terminology server, never from the source feed."))
    return out


def f7_dangling_reference(res, ctx):
    ids = {f"{r.get('resourceType')}/{r.get('id')}" for r in res}
    out = []
    for r in res:
        ref = (r.get("subject") or {}).get("reference")
        if ref and ref.startswith("Patient/") and ref not in ids:
            out.append(_f("F7", "critical", f"{r.get('resourceType')}/{r.get('id')}",
                          "subject reference points outside the bundle",
                          f"subject.reference={ref} is not present",
                          "The observation is orphaned - it belongs to no patient and drops out of every per-patient roll-up.",
                          "Include the referenced resource, or use an absolute reference the receiver can resolve."))
    return out


def f8_implausible_value(res, ctx):
    out = []
    for r in res:
        if r.get("resourceType") != "Observation":
            continue
        c = _coding(r)
        code = c.get("code")
        v = (r.get("valueQuantity") or {}).get("value")
        band = LOINC_RANGE.get(code)
        if band and isinstance(v, (int, float)) and not (band[0] <= v <= band[1]):
            out.append(_f("F8", "critical", f"Observation/{r.get('id')}",
                          "value outside the physiologically plausible band",
                          f"{LOINC_DISPLAY.get(code)} = {v} {(r.get('valueQuantity') or {}).get('unit')} (plausible {band[0]}-{band[1]})",
                          "One value like this moves a cohort mean and can trigger a clinical alert on a patient who is fine.",
                          "Range-check at intake and route outliers to review rather than loading them."))
    return out


def f9_wrong_code_system(res, ctx):
    out = []
    for r in res:
        if r.get("resourceType") != "Observation":
            continue
        c = _coding(r)
        code, sysu = c.get("code"), c.get("system")
        if code in LOINC_DISPLAY and sysu and sysu != LOINC_SYSTEM:
            out.append(_f("F9", "critical", f"Observation/{r.get('id')}",
                          "code declared under the wrong code system",
                          f"code {code} is LOINC but system={sysu}",
                          "Any receiver that filters by system finds nothing - the observation is invisible, not wrong.",
                          "Set system to http://loinc.org for LOINC codes."))
    return out


def f10_naive_timestamp(res, ctx):
    out = []
    for r in res:
        t = r.get("effectiveDateTime")
        if t and "T" in t and not TZ_RE.search(t):
            out.append(_f("F10", "high", f"{r.get('resourceType')}/{r.get('id')}",
                          "dateTime with no timezone offset",
                          f"effectiveDateTime={t}",
                          "The receiver assumes its own timezone; a result taken at 23:00 lands on the wrong day.",
                          "FHIR requires an offset when a dateTime carries a time. Emit +00:00 or the local offset."))
    return out


def f11_status_case(res, ctx):
    out = []
    for r in res:
        if r.get("resourceType") != "Observation":
            continue
        s = r.get("status")
        if s and s not in OBS_STATUS_VS:
            hint = " (the value set is lowercase)" if s.lower() in OBS_STATUS_VS else ""
            out.append(_f("F11", "high", f"Observation/{r.get('id')}",
                          "status outside the required value set",
                          f"status={s!r}{hint}",
                          "Filters on status='final' skip the row, so a finalised result is treated as missing.",
                          "Codes are case-sensitive; normalise before export."))
    return out


def f12_icd10_format(res, ctx):
    out = []
    for r in res:
        if r.get("resourceType") != "Condition":
            continue
        c = _coding(r)
        if c.get("system") != ICD10_SYSTEM:
            continue
        code = c.get("code", "")
        if not ICD10_RE.match(code):
            fix_hint = ""
            if re.match(r"^[A-Z]\d{3,}$", code):
                fix_hint = f" - looks like {code[:3]}.{code[3:]}"
            out.append(_f("F12", "critical", f"Condition/{r.get('id')}",
                          "ICD-10-CM code is not in valid format",
                          f"code={code!r}{fix_hint}",
                          "Payers reject the claim outright; the diagnosis never reaches the registry.",
                          "Restore the decimal point; ICD-10-CM is category + '.' + subcategory."))
    return out


CHECKS = [f1_gender_code, f2_duplicate_id, f3_future_birthdate, f4_missing_identifier,
          f5_unit_mismatch, f6_display_mismatch, f7_dangling_reference,
          f8_implausible_value, f9_wrong_code_system, f10_naive_timestamp,
          f11_status_case, f12_icd10_format]

SEV = {"critical": 3, "high": 2, "medium": 1}


def run_checks(bundle, today=None):
    ctx = {"today": today or dt.date.today()}
    res = _res(bundle)
    out = []
    for fn in CHECKS:
        try:
            out.extend(fn(res, ctx))
        except Exception as exc:
            out.append(_f(fn.__name__, "medium", "-", "check errored", repr(exc), "-", "-"))
    out.sort(key=lambda f: (-SEV.get(f["severity"], 0), f["check_id"]))
    return out
