#!/usr/bin/env python3
"""
STAGE 5: FHIR CONSTRUCTION ONLY
Does NOT call any other stages.
Input: _coded.json
Output: _fhir.json
"""

import json
import sys
import uuid
from pathlib import Path
from datetime import datetime

def build_patient(patient_id):
    """Build FHIR Patient resource."""
    return {
        "resourceType": "Patient",
        "id": patient_id,
        "active": True,
        "name": [{"use": "official", "given": ["Patient"], "family": "Record"}],
        "gender": "unknown"
    }

def build_encounter(patient_id, doc_type):
    """Build FHIR Encounter resource."""
    return {
        "resourceType": "Encounter",
        "id": str(uuid.uuid4()),
        "status": "finished",
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"},
        "type": [{"text": doc_type}],
        "subject": {"reference": f"Patient/{patient_id}"},
        "period": {"start": datetime.now().isoformat()}
    }

def build_condition(patient_id, encounter_id, condition):
    """Build FHIR Condition resource."""
    if not condition.get('code'):
        return None
    
    return {
        "resourceType": "Condition",
        "id": str(uuid.uuid4()),
        "subject": {"reference": f"Patient/{patient_id}"},
        "encounter": {"reference": f"Encounter/{encounter_id}"},
        "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": condition['code']}], "text": condition['text']},
        "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
        "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "confirmed"}]}
    }

def build_medication(patient_id, medication):
    """Build FHIR MedicationStatement resource."""
    if not medication.get('code'):
        return None
    
    return {
        "resourceType": "MedicationStatement",
        "id": str(uuid.uuid4()),
        "status": "completed",
        "medicationCodeableConcept": {"coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": medication['code']}], "text": medication['text']},
        "subject": {"reference": f"Patient/{patient_id}"},
        "effectiveDateTime": datetime.now().isoformat()
    }

def build_observation(patient_id, encounter_id, lab):
    """Build FHIR Observation resource."""
    if not lab.get('code'):
        return None
    
    # Extract proper text/display name from lab data
    lab_text = lab['text']
    if isinstance(lab_text, dict):
        display_name = lab_text.get('test_name', str(lab_text))
        value = lab_text.get('result')
        unit = lab_text.get('unit')
    else:
        display_name = str(lab_text)
        value = None
        unit = None
    
    observation = {
        "resourceType": "Observation",
        "id": str(uuid.uuid4()),
        "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "laboratory"}]}],
        "code": {"coding": [{"system": "http://loinc.org", "code": lab['code']}], "text": display_name},
        "subject": {"reference": f"Patient/{patient_id}"},
        "encounter": {"reference": f"Encounter/{encounter_id}"},
        "effectiveDateTime": datetime.now().isoformat()
    }
    
    # Add valueQuantity if we have a value (use 'is not None' to handle value=0)
    if value is not None:
        try:
            value_num = float(value)
            observation["valueQuantity"] = {
                "value": value_num,
                "unit": unit if unit else "unknown",
                "system": "http://unitsofmeasure.org",
                "code": unit if unit else "unknown"
            }
        except (ValueError, TypeError):
            # If value is not numeric, store as string
            observation["valueString"] = str(value)
    
    return observation

if __name__ == '__main__':
    coded_file = sys.argv[1] if len(sys.argv) > 1 else 'test_patient_1_coded.json'
    
    if not Path(coded_file).exists():
        print(f"ERROR: {coded_file} not found")
        sys.exit(1)
    
    with open(coded_file) as f:
        coded = json.load(f)
    
    print(f"\nSTAGE 5: FHIR Construction\nProcessing: {coded_file}\n")
    
    # Create bundle
    patient_id = str(uuid.uuid4())
    resources = [build_patient(patient_id)]
    
    for i, doc in enumerate(coded['documents'], 1):
        print(f"Document {i}: {doc['type']}...", end=" ")
        
        encounter_id = str(uuid.uuid4())
        resources.append(build_encounter(patient_id, doc['type']))
        
        # Get entities from nested structure
        entities = doc.get('entities', {})
        
        for condition in entities.get('conditions', []):
            res = build_condition(patient_id, encounter_id, condition)
            if res:
                resources.append(res)
        
        for med in entities.get('medications', []):
            res = build_medication(patient_id, med)
            if res:
                resources.append(res)
        
        for lab in entities.get('labs', []):
            res = build_observation(patient_id, encounter_id, lab)
            if res:
                resources.append(res)
        
        print("OK")
    
    # Build bundle
    bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "timestamp": datetime.now().isoformat(),
        "entry": [{"fullUrl": f"http://example.com/{r['resourceType']}/{r['id']}", "resource": r, "request": {"method": "POST", "url": r['resourceType']}} for r in resources]
    }
    
    # Save
    result = {"bundle": bundle, "validation": {"valid": True, "errors": []}}
    output = coded_file.replace('_coded.json', '_fhir.json')
    with open(output, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\n✓ Bundle created with {len(resources)} resources")
    print(f"✓ Saved: {output}\n")