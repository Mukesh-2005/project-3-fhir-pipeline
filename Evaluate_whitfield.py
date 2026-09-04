#!/usr/bin/env python3
"""
EVALUATION FOR WHITFIELD (NO GROUND TRUTH)
Just validates FHIR output and counts resources.
"""

import json
import sys
from pathlib import Path

# Keep the checkmarks printable when stdout is redirected to a file or a
# pipe, which on Windows defaults to cp1252 and cannot encode them.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

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
    validator = validation.get('validator', 'unknown')
    if validation.get('valid') is True:
        print(f"Status: ✓ PASS - Valid FHIR R4B  (checked by {validator})")
    elif validation.get('valid') is None:
        # No validator installed: unvalidated is not the same as valid.
        print("Status: ? NOT VALIDATED - no validator available")
        for error in validation.get('errors', [])[:3]:
            print(f"  - {error}")
    else:
        count = validation.get('error_count', len(validation.get('errors', [])))
        print(f"Status: ⚠️  INVALID - {count} error(s)  (checked by {validator})")
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
        text = m.get('resource', {}).get('medicationCodeableConcept', {}).get('text', 'Unknown')
        print(f"    - {text}")
    
    print("\n" + "="*70)
    print("✓ Evaluation complete!")
    print("="*70)
    
    return True

if __name__ == '__main__':
    fhir_file = sys.argv[1] if len(sys.argv) > 1 else 'whitfield_fhir.json'
    
    if not evaluate_fhir_only(fhir_file):
        sys.exit(1)