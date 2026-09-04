#!/usr/bin/env python3
"""
STAGE 5: FHIR CONSTRUCTION ONLY
Does NOT call any other stages.
Input: _coded.json
Output: _fhir.json
"""

import json
import re
import sys
import uuid
from pathlib import Path
from datetime import datetime


def now_iso():
    """
    Current time with a UTC offset.

    FHIR dateTime and instant both require an offset whenever a time is
    present, so a bare datetime.now().isoformat() fails validation.
    """
    return datetime.now().astimezone().isoformat()


def clinical_time(document_date):
    """
    The instant a fact was recorded, from the document's own date.

    Stamping every fact with the pipeline's run time made the encounters
    impossible to order. A document with no recoverable date yields None, and
    the date is then left off the resource entirely rather than invented.
    """
    if not document_date:
        return None
    # Midnight local time: the records carry a date, not a time of day.
    return datetime.fromisoformat(document_date).astimezone().isoformat()


def build_patient(patient_id):
    """Build FHIR Patient resource."""
    return {
        "resourceType": "Patient",
        "id": patient_id,
        "active": True,
        "name": [{"use": "official", "given": ["Patient"], "family": "Record"}],
        "gender": "unknown"
    }

def build_encounter(patient_id, doc_type, document_date=None):
    """Build FHIR Encounter resource."""
    encounter = {
        "resourceType": "Encounter",
        "id": str(uuid.uuid4()),
        "status": "finished",
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"},
        "type": [{"text": doc_type}],
        "subject": {"reference": f"Patient/{patient_id}"},
    }
    when = clinical_time(document_date)
    if when:
        encounter["period"] = {"start": when}
    return encounter

# Fallback systems, used only when stage 4 did not record one.
DEFAULT_SYSTEMS = {'condition': 'http://hl7.org/fhir/sid/icd-10-cm',
                   'medication': 'http://www.nlm.nih.gov/research/umls/rxnorm',
                   'lab': 'http://loinc.org'}


def coding_system(entity, kind):
    """The code system stage 4 assigned, so SNOMED is never sent as ICD-10."""
    return entity.get('system') or DEFAULT_SYSTEMS[kind]


def build_condition(patient_id, encounter_id, condition, document_date=None):
    """Build FHIR Condition resource."""
    if not condition.get('code'):
        return None

    resource = {
        "resourceType": "Condition",
        "id": str(uuid.uuid4()),
        "subject": {"reference": f"Patient/{patient_id}"},
        "encounter": {"reference": f"Encounter/{encounter_id}"},
        "code": {"coding": [{"system": coding_system(condition, 'condition'), "code": condition['code']}], "text": condition['text']},
        "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
        "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "confirmed"}]}
    }
    if document_date:
        resource["recordedDate"] = document_date
    return resource

def build_medication(patient_id, medication, document_date=None):
    """Build FHIR MedicationStatement resource."""
    if not medication.get('code'):
        return None

    resource = {
        "resourceType": "MedicationStatement",
        "id": str(uuid.uuid4()),
        "status": "completed",
        "medicationCodeableConcept": {"coding": [{"system": coding_system(medication, 'medication'), "code": medication['code']}], "text": medication['text']},
        "subject": {"reference": f"Patient/{patient_id}"},
    }
    when = clinical_time(document_date)
    if when:
        resource["effectiveDateTime"] = when
    return resource


# ------------------------------------------------------------------
# Lab value parsing
# Stage 3 emits labs as free text ("BP: 148/88 mmHg"), so the numeric
# result has to be recovered here or the Observation carries no value.
# ------------------------------------------------------------------

# UCUM codes for the units that appear in these records.
UNIT_UCUM = {
    'mmhg': 'mm[Hg]', 'mm hg': 'mm[Hg]',
    'bpm': '/min', 'beats/min': '/min', 'breaths/min': '/min', '/min': '/min',
    '%': '%', 'percent': '%',
    'degrees': 'deg', 'degree': 'deg', 'deg': 'deg',
    'f': '[degF]', 'degf': '[degF]', 'c': 'Cel', 'degc': 'Cel',
    'lb': '[lb_av]', 'lbs': '[lb_av]', 'pounds': '[lb_av]', 'kg': 'kg',
    'in': '[in_i]', 'inches': '[in_i]', 'cm': 'cm', 'mm': 'mm',
    'mg/dl': 'mg/dL', 'g/dl': 'g/dL', 'mmol/l': 'mmol/L', 'meq/l': 'meq/L',
    'ms': 'ms', 'm/s': 'm/s', 'mv': 'mV', 'uv': 'uV',
}

# Measures whose unit is implied by the test rather than written out.
IMPLIED_UNIT = (
    (('bmi', 'body mass index'), 'kg/m2'),
    (('pain',), '{score}'),
    (('gcs', 'glasgow'), '{score}'),
    (('dash',), '{score}'),
    (('mmt', 'strength'), '{score}'),
)

# LOINC codes for the two halves of a blood pressure reading.
BP_COMPONENT_CODES = (('8480-6', 'Systolic blood pressure'),
                      ('8462-4', 'Diastolic blood pressure'))

# A qualitative result must not be reduced to whatever number sits beside it:
# "Straight leg raise: positive right at 40 degrees" is not "40 deg".
QUALITATIVE = re.compile(
    r'\b(positive|negative|normal|abnormal|intact|absent|present|none|no|'
    r'unremarkable|decreased|diminished|increased|reduced|mild|moderate|'
    r'severe|trace|full|within normal limits|wnl)\b', re.I)

UNIT_ALTERNATION = '|'.join(
    re.escape(u) for u in sorted(UNIT_UCUM, key=len, reverse=True))
NUMBER_UNIT = re.compile(
    r'(?P<num>-?\d+(?:\.\d+)?)\s*(?P<unit>' + UNIT_ALTERNATION + r')?',
    re.I)
BP_PAIR = re.compile(r'(?<!\d)(?P<sys>\d{2,3})\s*/\s*(?P<dia>\d{2,3})(?!\d)')
# Scored scales: pain 0-10, manual muscle testing 0-5, percentage scores.
# A "+"/"-" grade modifier ("4+/5") becomes a Quantity comparator rather than
# being silently rounded away.
SCORE = re.compile(
    r'(?<!\d)(?P<num>\d+(?:\.\d+)?)(?P<mod>[+-])?\s*/\s*(?P<den>5|10|100)(?!\d)')
FEET_INCHES = re.compile(r"(?<!\d)(?P<ft>\d)\s*'\s*(?P<inch>\d{1,2})\s*\"?")

# A measurement leads with its number ("4.2 ms", "148/88 mmHg"); a clinical
# finding does not ("fibrillations 1+"). Only the former is read as a value,
# so a graded finding is never reduced to a bare number.
LEADS_WITH_NUMBER = re.compile(r'^[<>~]?\s*\.?\d')

COMPARATOR = {'+': '>', '-': '<'}


def implied_unit(display):
    """Unit for a measure written without one, or None."""
    lowered = display.lower()
    for keywords, unit in IMPLIED_UNIT:
        if any(word in lowered for word in keywords):
            return unit
    return None


def quantity(value, unit, comparator=None):
    """A FHIR Quantity, UCUM-coded when the unit is known."""
    result = {"value": value}
    if comparator:
        result["comparator"] = comparator
    if unit:
        result.update({"unit": unit, "system": "http://unitsofmeasure.org", "code": unit})
    return result


def parse_lab_value(raw):
    """
    Recover the result from a lab/vital string.

    Returns a dict with 'display' plus at most one of:
      'components'   - paired readings such as blood pressure
      'value'/'unit' - a single numeric result, UCUM-coded
      'value_string' - a qualitative result that must not be numeric

    A string carrying no result at all yields only 'display'.
    """
    if isinstance(raw, dict):
        display = str(raw.get('test_name') or raw.get('name') or raw)
        value, unit = raw.get('result'), raw.get('unit')
        if value is None:
            return {'display': display}
        try:
            return {'display': display, 'value': float(value),
                    'unit': UNIT_UCUM.get(str(unit).lower(), unit) if unit else None}
        except (TypeError, ValueError):
            return {'display': display, 'value_string': str(value)}

    text = re.sub(r'\s+', ' ', str(raw)).strip()

    # "BP: 148/88 mmHg" -> name before the first colon, result after it.
    if ':' in text:
        display, _, result = text.partition(':')
        display, result = display.strip(), result.strip()
    else:
        display, result = text, ''

    if not result:
        return {'display': display}

    parsed = {'display': display}

    # Height written as feet and inches.
    feet = FEET_INCHES.search(result)
    if feet:
        inches = int(feet.group('ft')) * 12 + int(feet.group('inch'))
        parsed.update(value=float(inches), unit='[in_i]')
        return parsed

    # Blood pressure: a systolic/diastolic pair, not a single number.
    pair = BP_PAIR.search(result)
    if pair and not SCORE.search(result):
        systolic, diastolic = int(pair.group('sys')), int(pair.group('dia'))
        if 'bp' in display.lower() or 'blood pressure' in display.lower() or (
                60 <= systolic <= 300 and 30 <= diastolic <= 200):
            parsed['components'] = [
                {'code': BP_COMPONENT_CODES[0][0], 'display': BP_COMPONENT_CODES[0][1],
                 'value': float(systolic), 'unit': 'mm[Hg]'},
                {'code': BP_COMPONENT_CODES[1][0], 'display': BP_COMPONENT_CODES[1][1],
                 'value': float(diastolic), 'unit': 'mm[Hg]'},
            ]
            return parsed

    # Qualitative findings, and graded findings that do not lead with their
    # number, stay text so no number is invented from a description.
    if QUALITATIVE.search(result) or not LEADS_WITH_NUMBER.match(result):
        parsed['value_string'] = result
        return parsed

    # Scored scales: "7/10" is the value 7, not the ratio 0.7.
    score = SCORE.search(result)
    if score:
        parsed.update(value=float(score.group('num')),
                      unit=implied_unit(display) or '{score}',
                      comparator=COMPARATOR.get(score.group('mod')))
        return parsed

    # A plain number with an optional written unit.
    match = NUMBER_UNIT.search(result)
    if match:
        written = (match.group('unit') or '').strip().lower()
        parsed.update(value=float(match.group('num')),
                      unit=UNIT_UCUM.get(written) if written else implied_unit(display))
        return parsed

    # Text with no number in it at all.
    parsed['value_string'] = result
    return parsed


def build_observation(patient_id, encounter_id, lab, document_date=None):
    """Build FHIR Observation resource."""
    if not lab.get('code'):
        return None

    parsed = parse_lab_value(lab['text'])

    observation = {
        "resourceType": "Observation",
        "id": str(uuid.uuid4()),
        "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "laboratory"}]}],
        "code": {"coding": [{"system": coding_system(lab, 'lab'), "code": lab['code']}], "text": parsed['display']},
        "subject": {"reference": f"Patient/{patient_id}"},
        "encounter": {"reference": f"Encounter/{encounter_id}"},
    }
    when = clinical_time(document_date)
    if when:
        observation["effectiveDateTime"] = when

    if parsed.get('components'):
        observation["component"] = [{
            "code": {"coding": [{"system": "http://loinc.org", "code": component['code'],
                                 "display": component['display']}]},
            "valueQuantity": quantity(component['value'], component['unit']),
        } for component in parsed['components']]
    elif parsed.get('value') is not None:
        observation["valueQuantity"] = quantity(
            parsed['value'], parsed.get('unit'), parsed.get('comparator'))
    elif parsed.get('value_string'):
        observation["valueString"] = parsed['value_string']

    return observation


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------

MAX_REPORTED_ERRORS = 20

# What a pass from this validator does and does not mean. fhir.resources builds
# pydantic models from the FHIR StructureDefinitions, so it checks shape but not
# terminology: an out-of-ValueSet code such as status="banana" still passes.
# Recorded in the output so a PASS is never read as more than it is.
VALIDATION_SCOPE = {
    "checked": ["resource structure", "required fields", "cardinality",
                "datatype and primitive formats (dateTime, instant, decimal)"],
    "not_checked": ["terminology bindings (ValueSet membership)",
                    "code system correctness (that a code belongs to its stated system)",
                    "profile conformance", "reference resolution"],
}


def validate_bundle(bundle):
    """
    Validate the bundle against the FHIR R4B specification.

    Returns {'valid', 'validator', 'scope', 'error_count', 'errors'}. 'valid'
    is None when no validator is installed, so a missing dependency is never
    reported as a pass.
    """
    try:
        import fhir.resources
        from fhir.resources.R4B.bundle import Bundle
        from pydantic import ValidationError
    except ImportError:
        return {
            "valid": None,
            "validator": "none installed - bundle was NOT validated",
            "scope": VALIDATION_SCOPE,
            "error_count": 0,
            "errors": ["fhir.resources is not installed, so this bundle is unvalidated. "
                       "Install it with: pip install fhir.resources"],
        }

    validator = f"fhir.resources {fhir.resources.__version__} (FHIR R4B)"

    try:
        Bundle.model_validate(bundle)
    except ValidationError as exc:
        errors = [
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        ]
        return {
            "valid": False,
            "validator": validator,
            "scope": VALIDATION_SCOPE,
            "error_count": len(errors),
            "errors": errors[:MAX_REPORTED_ERRORS],
        }

    return {"valid": True, "validator": validator, "scope": VALIDATION_SCOPE,
            "error_count": 0, "errors": []}


if __name__ == '__main__':
    coded_file = sys.argv[1] if len(sys.argv) > 1 else 'whitfield_coded.json'

    if not Path(coded_file).exists():
        print(f"ERROR: {coded_file} not found")
        sys.exit(1)

    with open(coded_file, encoding='utf-8') as f:
        coded = json.load(f)

    print(f"\nSTAGE 5: FHIR Construction\nProcessing: {coded_file}\n")

    # Create bundle
    patient_id = str(uuid.uuid4())
    resources = [build_patient(patient_id)]

    for i, doc in enumerate(coded['documents'], 1):
        print(f"Document {i}: {doc['type']}...", end=" ")

        encounter_id = str(uuid.uuid4())
        document_date = doc.get('document_date')
        encounter = build_encounter(patient_id, doc['type'], document_date)
        encounter_id = encounter['id']
        resources.append(encounter)

        # Get entities from nested structure
        entities = doc.get('entities', {})

        for condition in entities.get('conditions', []):
            res = build_condition(patient_id, encounter_id, condition, document_date)
            if res:
                resources.append(res)

        for med in entities.get('medications', []):
            res = build_medication(patient_id, med, document_date)
            if res:
                resources.append(res)

        for lab in entities.get('labs', []):
            res = build_observation(patient_id, encounter_id, lab, document_date)
            if res:
                resources.append(res)

        print("OK")

    # Build bundle
    bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "timestamp": now_iso(),
        "entry": [{"fullUrl": f"http://example.com/{r['resourceType']}/{r['id']}", "resource": r, "request": {"method": "POST", "url": r['resourceType']}} for r in resources]
    }

    validation = validate_bundle(bundle)

    # Save
    # Carried through so stage 6 can scope a reload to this record rather
    # than inferring it from the output filename.
    source_file = coded.get('pdf_file', coded_file)
    result = {"source_file": Path(source_file).stem,
              "bundle": bundle, "validation": validation}
    output = coded_file.replace('_coded.json', '_fhir.json')
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)

    print(f"\nBundle created with {len(resources)} resources")
    print(f"Validator: {validation['validator']}")
    if validation['valid'] is True:
        print("Validation: PASS - valid FHIR R4B")
    elif validation['valid'] is None:
        print("Validation: NOT RUN")
        for message in validation['errors']:
            print(f"  {message}")
    else:
        print(f"Validation: FAIL - {validation['error_count']} error(s)")
        for message in validation['errors']:
            print(f"  {message}")
        if validation['error_count'] > len(validation['errors']):
            print(f"  ... and {validation['error_count'] - len(validation['errors'])} more")

    print(f"Saved: {output}\n")
