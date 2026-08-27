#!/usr/bin/env python3
"""
EVALUATION FOR WHITFIELD (NO GROUND TRUTH)
Just validates FHIR output and counts resources.
"""

import json
import sys
from pathlib import Path

def evaluate_fhir_only(fhir_file):
    """Evaluate FHIR output without ground truth."""
    
    print("\n" + "="*70)
    print("WHITFIELD EVALUATION (FHIR Validation Only)")
    print("="*70)
    
    if not Path(fhir_file).exists():
        print(f"❌ File not found: {fhir_file}")
        return False
    
    with open(fhir_file) as f:
        data = json.load(f)
    
    # Check structure
    print("\n[FHIR VALIDATION]")
    if 'bundle' not in data:
        print("❌ No FHIR bundle found")
        return False
    
    bundle = data['bundle']
    if bundle.get('resourceType') != 'Bundle':
        print("❌ Not a valid FHIR Bundle")
        return False
    
    validation = data.get('validation', {})
    if validation.get('valid'):
        print("Status: ✓ PASS - Valid FHIR R4")
    else:
        print("Status: ⚠️  Invalid FHIR")
        if validation.get('errors'):
            for error in validation.get('errors', [])[:3]:
                print(f"  - {error}")
    
    # Count resources
    print("\n[RESOURCE COUNTS]")
    resource_counts = {}
    entries = bundle.get('entry', [])
    
    for entry in entries:
        rtype = entry.get('resource', {}).get('resourceType')
        resource_counts[rtype] = resource_counts.get(rtype, 0) + 1
    
    for rtype in sorted(resource_counts.keys()):
        print(f"  {rtype}: {resource_counts[rtype]}")
    
    total = len(entries)
    print(f"\nTotal resources: {total}")
    
    # Show extracted facts
    print("\n[EXTRACTED FACTS]")
    conditions = [e for e in entries if e.get('resource', {}).get('resourceType') == 'Condition']
    observations = [e for e in entries if e.get('resource', {}).get('resourceType') == 'Observation']
    meds = [e for e in entries if e.get('resource', {}).get('resourceType') == 'MedicationStatement']
    
    print(f"  Conditions: {len(conditions)}")
    for c in conditions[:5]:
        text = c.get('resource', {}).get('code', {}).get('text', 'Unknown')
        print(f"    - {text}")
    
    print(f"  Observations/Labs: {len(observations)}")
    for o in observations[:5]:
        text = o.get('resource', {}).get('code', {}).get('text', 'Unknown')
        print(f"    - {text}")
    
    print(f"  Medications: {len(meds)}")
    for m in meds[:3]:
        text = m.get('resource', {}).get('medicationCodeableConcept', {}).get('coding', [{}])[0].get('display', 'Unknown')
        print(f"    - {text}")
    
    print("\n" + "="*70)
    print("✓ Evaluation complete!")
    print("="*70)
    
    return True

if __name__ == '__main__':
    fhir_file = sys.argv[1] if len(sys.argv) > 1 else 'whitfield_fhir.json'
    
    if not evaluate_fhir_only(fhir_file):
        sys.exit(1)