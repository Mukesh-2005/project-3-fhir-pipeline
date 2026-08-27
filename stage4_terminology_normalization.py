#!/usr/bin/env python3
"""
STAGE 4: TERMINOLOGY NORMALIZATION ONLY
Does NOT call any other stages.
Input: _entities.json
Output: _coded.json
"""

import json
import sys
from pathlib import Path

# Expanded medical code mappings - includes Whitfield terms
CONDITION_CODES = {
    # Neck/back pain conditions
    'posterior neck pain': 'M54.2',
    'neck pain': 'M54.2',
    'cervical pain': 'M54.2',
    'mid back pain': 'M54.3',
    'lower back pain': 'M54.5',
    'low back pain': 'M54.5',
    'back pain': 'M54.5',
    'lumbosacral pain': 'M54.5',
    'leg pain': 'M25.5',
    'right leg pain': 'M25.5',
    'pain radiating down right leg': 'M25.5',
    'pain with weight bearing on right leg': 'M25.5',
    'radiating pain': 'M25.5',
    'calf pain': 'M25.5',
    'foot pain': 'M25.5',
    'tingling': 'G89.29',
    'paresthesia': 'G89.29',
    'numbness': 'G89.29',
    'foot numbness': 'G89.29',
    'foot tingling': 'G89.29',
    'weakness': 'M62.81',
    'heel weakness': 'M62.81',
    'ehl weakness': 'M62.81',
    
    # Disc/spine conditions
    'degenerative disc disease': 'M47.9',
    'disc disease': 'M47.9',
    'disc space narrowing': 'M47.9',
    'disc desiccation': 'M47.9',
    'disc bulge': 'M51.2',
    'disc protrusion': 'M51.2',
    'disc herniation': 'M51.2',
    'facet arthropathy': 'M47.9',
    'facet arthritis': 'M47.9',
    'facet hypertrophy': 'M47.9',
    'stenosis': 'M48.0',
    'lateral recess stenosis': 'M48.0',
    'ligamentum flavum thickening': 'M48.0',
    
    # Strain/trauma
    'acute lumbosacral strain': 'M54.5',
    'strain': 'M54.5',
    'acute strain': 'M54.5',
    'motor vehicle collision': 'V00-V99',
    'motor vehicle accident': 'V00-V99',
    'collision': 'V00-V99',
    'rear-end collision': 'V00-V99',
    'trauma': 'T00-T88',
    
    # Radiculopathy/dermatome
    'radiculopathy': 'M54.1',
    'radicular': 'M54.1',
    'l5 radiculopathy': 'M54.1',
    'lumbosacral radiculopathy': 'M54.1',
    'l5 dermatome': 'M54.1',
    'sensory deficit': 'G89.29',
    'l5 sensory deficit': 'G89.29',
    
    # Post-op conditions
    'post-op': 'Z98.8',
    'post-operative': 'Z98.8',
    'rotator cuff repair': 'Z98.8',
    'post-operative low back pain': 'M54.5',
    'post-operative rehabilitation': 'Z98.8',
    'status post': 'Z98.8',
    'residual': 'Z98.8',
    
    # Gait abnormalities
    'antalgic gait': 'R26.1',
    'gait abnormality': 'R26.1',
    'weak heel walking': 'R26.1',
    'catching sensation': 'M25.6',
    
    # Standard conditions
    'denervation': 'M63.8',
    'active denervation': 'M63.8',
    'neuropathy': 'G60.9',
    'peripheral neuropathy': 'G60.9',
    'polyneuropathy': 'G61.9',
    'entrapment neuropathy': 'G56.9',
    'plexopathy': 'G54.9',
    'cervical': 'M54.2',
    'lumbar': 'M54.5',
    'viral sinusitis': '444814009',
    'medication review': '314529007',
    'sinusitis': '444814009',
    'diabetes': 'E11.9',
    'hypertension': 'I10',
    'arthritis': 'M19.90',
    'osteoarthritis': 'M19.90',
    'obesity': 'E66.9',
}

MEDICATION_CODES = {
    'ketorolac': '6109',
    'methocarbamol': '6916',
    'ondansetron': '31307',
    'docusate': '3442',
    'docusate sodium': '3442',
    'neuropathic medication': '5856',
    'anti-inflammatory': '6109',
    'anti-inflammatory medication': '6109',
    'metformin': '6809',
    'insulin': '5856',
    'lisinopril': '25481',
    'aspirin': '17778',
    'acetaminophen': '161',
    'ibuprofen': '5640',
    'naproxen': '6956',
    'tramadol': '10689',
    'gabapentin': '3623',
    'pregabalin': '225386',
    'morphine': '7052',
    'hydrocodone': '5489',
    'oral medication': '5856',
}

LAB_CODES = {
    # Vital signs
    'bp': '55284-4',
    'blood pressure': '55284-4',
    'hr': '8867-4',
    'heart rate': '8867-4',
    'rr': '9279-1',
    'respiratory rate': '9279-1',
    'spo2': '59408-5',
    'oxygen saturation': '59408-5',
    'gcs': '9269-2',
    'glasgow coma': '9269-2',
    'temp': '8310-5',
    'temperature': '8310-5',
    
    # Imaging
    'radiographs': '18748-4',
    'x-ray': '18748-4',
    'ed radiographs': '18748-4',
    'lumbar radiographs': '18748-4',
    'ct': '18748-4',
    'ct scan': '18748-4',
    'mri': '18748-4',
    'imaging': '18748-4',
    
    # Physical exam findings
    'lumbar flexion': '89264-0',
    'lumbar extension': '89264-0',
    'range of motion': '89264-0',
    'rom': '89264-0',
    'shoulder flexion': '89264-0',
    'external rotation': '89264-0',
    'mmt': '50373-0',
    'manual muscle test': '50373-0',
    'supraspinatus': '50373-0',
    'ehl strength': '50373-0',
    'strength': '50373-0',
    'dash score': '42838-2',
    'functional assessment': '42838-2',
    
    # EMG/NCS
    'emg': '51737-7',
    'electromyography': '51737-7',
    'emg/ncs': '51737-7',
    'nerve conduction': '51737-7',
    'peroneal motor': '51737-7',
    'tibial motor': '51737-7',
    'sural sensory': '51737-7',
    'h-reflex': '51737-7',
    'needle electromyography': '51737-7',
    'fibrillations': '51737-7',
    'positive sharp waves': '51737-7',
    'recruitment': '51737-7',
    'distal latency': '51737-7',
    'amplitude': '51737-7',
    'conduction velocity': '51737-7',
    
    # Standard labs
    'glucose': '2345-7',
    'hemoglobin': '718-7',
    'hematocrit': '4544-3',
    'potassium': '2823-3',
    'sodium': '2951-2',
    'creatinine': '2160-0',
    'body height': '8302-2',
    'height': '8302-2',
    'body weight': '29463-7',
    'weight': '29463-7',
    'body mass index': '39156-5',
    'bmi': '39156-5',
    'pain': '72514-3',
    'pain severity': '72514-3',
}

def map_term(term, mapping):
    """Smart string matching for codes."""
    # Handle dicts or strings
    if isinstance(term, dict):
        term_str = term.get('test_name') or term.get('drug_name') or term.get('substance') or str(term)
    else:
        term_str = str(term)
    
    term_lower = term_str.lower()
    
    # Exact match first
    if term_lower in mapping:
        return mapping[term_lower]
    
    # Substring match: check if ANY dictionary key is IN the term
    for key, code in mapping.items():
        if key in term_lower:
            return code
    
    # Try reverse: check if term is IN any dictionary key (for partial matches)
    for key, code in mapping.items():
        if term_lower in key:
            return code
    
    return None

if __name__ == '__main__':
    entities_file = sys.argv[1] if len(sys.argv) > 1 else 'test_patient_1_entities.json'
    
    if not Path(entities_file).exists():
        print(f"ERROR: {entities_file} not found")
        sys.exit(1)
    
    with open(entities_file) as f:
        entities = json.load(f)
    
    print(f"\nSTAGE 4: Terminology Normalization\nProcessing: {entities_file}\n")
    
    result = {'pdf_file': entities['pdf_file'], 'documents': []}
    
    for i, doc in enumerate(entities['documents'], 1):
        print(f"Document {i}: {doc['type']}...", end=" ")
        
        coded = {
            'type': doc['type'],
            'pages': doc['pages'],
            'entities': {
                'conditions': [],
                'medications': [],
                'labs': []
            }
        }
        
        # Code conditions
        for cond in doc['entities'].get('conditions', []):
            code = map_term(cond, CONDITION_CODES)
            coded['entities']['conditions'].append({'text': cond, 'code': code})
        
        # Code medications
        for med in doc['entities'].get('medications', []):
            code = map_term(med, MEDICATION_CODES)
            coded['entities']['medications'].append({'text': med, 'code': code})
        
        # Code labs
        for lab in doc['entities'].get('labs', []):
            code = map_term(lab, LAB_CODES)
            coded['entities']['labs'].append({'text': lab, 'code': code})
        
        result['documents'].append(coded)
        print("OK")
    
    # Save
    output = entities_file.replace('_entities.json', '_coded.json')
    with open(output, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\n✓ Saved: {output}\n")