#!/usr/bin/env python3
"""
STAGE 7: PROVENANCE & CONFIDENCE ONLY
Does NOT call any other stages.
Input: _fhir.json
Output: _provenance.json
"""

import json
import sys
from pathlib import Path
from datetime import datetime

if __name__ == '__main__':
    fhir_file = sys.argv[1] if len(sys.argv) > 1 else 'test_patient_1_fhir.json'
    
    if not Path(fhir_file).exists():
        print(f"ERROR: {fhir_file} not found")
        sys.exit(1)
    
    with open(fhir_file) as f:
        fhir_data = json.load(f)
    
    print(f"\nSTAGE 7: Provenance & Confidence\nProcessing: {fhir_file}\n")
    
    # Extract provenance info from FHIR resources
    provenance_log = []
    bundle = fhir_data['bundle']
    
    for entry in bundle.get('entry', []):
        resource = entry.get('resource', {})
        rtype = resource.get('resourceType')
        
        # Log each resource with confidence
        log_entry = {
            'resource_type': rtype,
            'resource_id': resource.get('id'),
            'source_document': fhir_file,
            'extraction_confidence': 0.85,  # Default
            'timestamp': datetime.now().isoformat(),
            'status': 'accepted'
        }
        
        # Add display/description
        if rtype == 'Condition':
            log_entry['description'] = resource.get('code', {}).get('text', 'Unknown condition')
        elif rtype == 'Observation':
            log_entry['description'] = resource.get('code', {}).get('text', 'Unknown observation')
        elif rtype == 'MedicationStatement':
            log_entry['description'] = resource.get('medicationCodeableConcept', {}).get('text', 'Unknown medication')
        
        provenance_log.append(log_entry)
    
    print(f"✓ Tracked {len(provenance_log)} facts with provenance")
    
    # Save provenance
    result = {
        'fhir_file': fhir_file,
        'total_facts': len(provenance_log),
        'facts_needing_review': 0,
        'provenance_log': provenance_log,
        'review_queue': []
    }
    
    output = fhir_file.replace('_fhir.json', '_provenance.json')
    with open(output, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"✓ Saved: {output}\n")