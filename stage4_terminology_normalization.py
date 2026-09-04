#!/usr/bin/env python3
"""
STAGE 4: TERMINOLOGY NORMALIZATION ONLY
Does NOT call any other stages.
Input: _entities.json
Output: _coded.json

Matching is whole-word and longest-match-wins, so "insertional activity" no
longer matches the key "ct" and "cervical strain" beats the bare key "strain".
Every entry carries the code system it belongs to, so a SNOMED concept is never
published under the ICD-10 URL.

The mappings below are a best-effort demonstration dictionary, not a certified
code set; a clinical coder should review them before any real use.
"""

import json
import re
import sys
from pathlib import Path

ICD10 = 'http://hl7.org/fhir/sid/icd-10-cm'
SNOMED = 'http://snomed.info/sct'
LOINC = 'http://loinc.org'
RXNORM = 'http://www.nlm.nih.gov/research/umls/rxnorm'

# term -> (code, system)
CONDITION_CODES = {
    # Cervical / neck
    'neck pain': ('M54.2', ICD10),
    'posterior neck pain': ('M54.2', ICD10),
    'cervical pain': ('M54.2', ICD10),
    'cervicalgia': ('M54.2', ICD10),
    'cervical midline tenderness': ('M54.2', ICD10),
    # A strain is an injury, not the pain code M54.5 the old dictionary used.
    'cervical strain': ('S16.1XXA', ICD10),
    'acute cervical strain': ('S16.1XXA', ICD10),
    'neck strain': ('S16.1XXA', ICD10),
    'cervical sprain': ('S13.4XXA', ICD10),
    'whiplash': ('S13.4XXA', ICD10),

    # Thoracic / lumbar
    # M54.5 is a category header and is not itself billable; M54.50 is.
    'low back pain': ('M54.50', ICD10),
    'lower back pain': ('M54.50', ICD10),
    'lumbago': ('M54.50', ICD10),
    'post-operative low back pain': ('M54.50', ICD10),
    'back pain': ('M54.9', ICD10),
    'mid back pain': ('M54.6', ICD10),
    'thoracic pain': ('M54.6', ICD10),
    'lumbar strain': ('S39.012A', ICD10),
    'lumbosacral strain': ('S39.012A', ICD10),
    'acute lumbosacral strain': ('S39.012A', ICD10),
    'lumbar paraspinal tenderness': ('M54.50', ICD10),

    # Radiculopathy
    'radiculopathy': ('M54.10', ICD10),
    'cervical radiculopathy': ('M54.12', ICD10),
    'lumbar radiculopathy': ('M54.16', ICD10),
    'l5 radiculopathy': ('M54.16', ICD10),
    'lumbosacral radiculopathy': ('M54.17', ICD10),
    'radicular pain': ('M54.10', ICD10),
    'sciatica': ('M54.30', ICD10),

    # Disc and facet
    'degenerative disc disease': ('M51.36', ICD10),
    'disc degeneration': ('M51.36', ICD10),
    'disc desiccation': ('M51.36', ICD10),
    'disc disease': ('M51.9', ICD10),
    'disc bulge': ('M51.26', ICD10),
    'disc protrusion': ('M51.26', ICD10),
    'disc herniation': ('M51.26', ICD10),
    'disc displacement': ('M51.26', ICD10),
    'facet arthropathy': ('M47.816', ICD10),
    'facet arthritis': ('M47.816', ICD10),
    'facet hypertrophy': ('M47.816', ICD10),
    'spondylosis': ('M47.816', ICD10),
    'spinal stenosis': ('M48.00', ICD10),
    'lumbar stenosis': ('M48.06', ICD10),
    'lateral recess stenosis': ('M48.06', ICD10),
    'ligamentum flavum thickening': ('M48.06', ICD10),

    # Neurologic findings
    'paresthesia': ('R20.2', ICD10),
    'tingling': ('R20.2', ICD10),
    'numbness': ('R20.0', ICD10),
    'sensory deficit': ('R20.8', ICD10),
    'weakness': ('M62.81', ICD10),
    'muscle weakness': ('M62.81', ICD10),
    'ehl weakness': ('M62.81', ICD10),
    'neuropathy': ('G60.9', ICD10),
    'peripheral neuropathy': ('G60.9', ICD10),
    'polyneuropathy': ('G61.9', ICD10),
    'entrapment neuropathy': ('G56.90', ICD10),
    'plexopathy': ('G54.9', ICD10),

    # Gait
    'antalgic gait': ('R26.89', ICD10),
    'gait abnormality': ('R26.9', ICD10),
    'difficulty walking': ('R26.2', ICD10),

    # External cause. V00-V99 and T00-T88 are ICD-10 chapter RANGES, not codes,
    # and were rejected as codes by any real consumer; V89.2XXA is the code for
    # an unspecified motor-vehicle traffic accident.
    'motor vehicle collision': ('V89.2XXA', ICD10),
    'motor vehicle accident': ('V89.2XXA', ICD10),
    'rear-end collision': ('V89.2XXA', ICD10),

    # Post-procedural
    'post-operative': ('Z98.890', ICD10),
    'status post': ('Z98.890', ICD10),
    'rotator cuff repair': ('Z98.890', ICD10),
    'post-operative rehabilitation': ('Z98.890', ICD10),

    # General
    'diabetes': ('E11.9', ICD10),
    'hypertension': ('I10', ICD10),
    'osteoarthritis': ('M19.90', ICD10),
    'arthritis': ('M19.90', ICD10),
    'obesity': ('E66.9', ICD10),
    'sinusitis': ('J01.90', ICD10),
    # SNOMED concepts, now published under the SNOMED system rather than ICD-10.
    'viral sinusitis': ('444814009', SNOMED),
    'medication review': ('314529007', SNOMED),
}

# RxNorm ingredient codes carried over from the original dictionary. These have
# NOT been re-verified against RxNorm and several look doubtful; treat them as
# placeholders pending a proper RxNorm lookup.
MEDICATION_CODES = {
    'ketorolac': ('6109', RXNORM),
    'methocarbamol': ('6916', RXNORM),
    'ondansetron': ('31307', RXNORM),
    'docusate': ('3442', RXNORM),
    'docusate sodium': ('3442', RXNORM),
    'metformin': ('6809', RXNORM),
    'insulin': ('5856', RXNORM),
    'lisinopril': ('25481', RXNORM),
    'aspirin': ('17778', RXNORM),
    'acetaminophen': ('161', RXNORM),
    'ibuprofen': ('5640', RXNORM),
    'naproxen': ('6956', RXNORM),
    'tramadol': ('10689', RXNORM),
    'gabapentin': ('3623', RXNORM),
    'pregabalin': ('225386', RXNORM),
    'morphine': ('7052', RXNORM),
    'hydrocodone': ('5489', RXNORM),
    'codeine': ('2670', RXNORM),
    'cyclobenzaprine': ('21241', RXNORM),
    'prednisone': ('8640', RXNORM),
    'diazepam': ('3322', RXNORM),
}

LAB_CODES = {
    # Vital signs
    'bp': ('85354-9', LOINC),
    'blood pressure': ('85354-9', LOINC),
    'hr': ('8867-4', LOINC),
    'heart rate': ('8867-4', LOINC),
    'pulse': ('8867-4', LOINC),
    'rr': ('9279-1', LOINC),
    'respiratory rate': ('9279-1', LOINC),
    'spo2': ('59408-5', LOINC),
    'oxygen saturation': ('59408-5', LOINC),
    'gcs': ('9269-2', LOINC),
    'glasgow coma': ('9269-2', LOINC),
    't': ('8310-5', LOINC),
    'temp': ('8310-5', LOINC),
    'temperature': ('8310-5', LOINC),
    'ht': ('8302-2', LOINC),
    'height': ('8302-2', LOINC),
    'body height': ('8302-2', LOINC),
    'wt': ('29463-7', LOINC),
    'weight': ('29463-7', LOINC),
    'body weight': ('29463-7', LOINC),
    'bmi': ('39156-5', LOINC),
    'body mass index': ('39156-5', LOINC),
    'pain': ('72514-3', LOINC),
    'pain severity': ('72514-3', LOINC),

    # Imaging. "ct" only matches the standalone word now, not "activity".
    'x-ray': ('43468-8', LOINC),
    'radiographs': ('43468-8', LOINC),
    'ed radiographs': ('43468-8', LOINC),
    'lumbar radiographs': ('43468-8', LOINC),
    'ct': ('24627-2', LOINC),
    'ct scan': ('24627-2', LOINC),
    'mri': ('24676-9', LOINC),
    'imaging': ('18748-4', LOINC),

    # Physical exam
    'range of motion': ('89264-0', LOINC),
    'rom': ('89264-0', LOINC),
    'lumbar flexion': ('89264-0', LOINC),
    'lumbar extension': ('89264-0', LOINC),
    'shoulder flexion': ('89264-0', LOINC),
    'shoulder abduction': ('89264-0', LOINC),
    'external rotation': ('89264-0', LOINC),
    'mmt': ('50373-0', LOINC),
    'manual muscle test': ('50373-0', LOINC),
    'strength': ('50373-0', LOINC),
    'supraspinatus': ('50373-0', LOINC),
    'dash score': ('42838-2', LOINC),
    'functional assessment': ('42838-2', LOINC),

    # EMG / NCS
    'emg': ('51737-7', LOINC),
    'emg/ncs': ('51737-7', LOINC),
    'electromyography': ('51737-7', LOINC),
    'needle electromyography': ('51737-7', LOINC),
    'nerve conduction': ('51737-7', LOINC),
    'peroneal motor': ('51737-7', LOINC),
    'tibial motor': ('51737-7', LOINC),
    'sural sensory': ('51737-7', LOINC),
    'h-reflex': ('51737-7', LOINC),
    'distal latency': ('51737-7', LOINC),
    'conduction velocity': ('51737-7', LOINC),

    # Standard labs
    'glucose': ('2345-7', LOINC),
    'hemoglobin': ('718-7', LOINC),
    'hematocrit': ('4544-3', LOINC),
    'potassium': ('2823-3', LOINC),
    'sodium': ('2951-2', LOINC),
    'creatinine': ('2160-0', LOINC),
}

# Word-boundary patterns, compiled once. \b will not fire inside a longer word,
# so the key "ct" matches "CT scan" but not "insertional activity".
_PATTERNS = {}


def pattern_for(key):
    """Cached whole-word pattern for a dictionary key."""
    if key not in _PATTERNS:
        _PATTERNS[key] = re.compile(r'(?<!\w)' + re.escape(key).replace(r'\ ', r'\s+') + r'(?!\w)',
                                    re.I)
    return _PATTERNS[key]


def term_text(term):
    """The searchable string for an entity, which may arrive as a dict."""
    if isinstance(term, dict):
        return str(term.get('test_name') or term.get('drug_name')
                   or term.get('substance') or term.get('name') or term)
    return str(term)


def map_term(term, mapping):
    """
    Map a free-text term to (code, system), or (None, None) when nothing matches.

    The longest matching key wins, so a specific term beats a generic one
    ("cervical strain" over "strain"). Ties break alphabetically so the result
    never depends on dictionary insertion order.
    """
    text = re.sub(r'\s+', ' ', term_text(term)).strip()
    if not text:
        return None, None

    matches = [key for key in mapping if pattern_for(key).search(text)]
    if not matches:
        return None, None

    best = min(matches, key=lambda key: (-len(key), key))
    return mapping[best]


def code_entities(items, mapping, unmapped):
    """Code a list of entities, recording anything that did not match."""
    coded = []
    for item in items:
        code, system = map_term(item, mapping)
        if code is None:
            unmapped.append(term_text(item))
        coded.append({'text': item, 'code': code, 'system': system})
    return coded


if __name__ == '__main__':
    entities_file = sys.argv[1] if len(sys.argv) > 1 else 'whitfield_entities.json'

    if not Path(entities_file).exists():
        print(f"ERROR: {entities_file} not found")
        sys.exit(1)

    with open(entities_file, encoding='utf-8') as f:
        entities = json.load(f)

    print(f"\nSTAGE 4: Terminology Normalization\nProcessing: {entities_file}\n")

    result = {'pdf_file': entities['pdf_file'], 'documents': []}
    unmapped_all = {'conditions': [], 'medications': [], 'labs': []}
    total = 0

    for i, doc in enumerate(entities['documents'], 1):
        print(f"Document {i}: {doc['type']}...", end=" ")

        source = doc.get('entities', {})
        coded = {
            'type': doc['type'],
            'pages': doc['pages'],
            'entities': {
                'conditions': code_entities(source.get('conditions', []),
                                            CONDITION_CODES, unmapped_all['conditions']),
                'medications': code_entities(source.get('medications', []),
                                             MEDICATION_CODES, unmapped_all['medications']),
                'labs': code_entities(source.get('labs', []),
                                      LAB_CODES, unmapped_all['labs']),
            },
        }

        # Carry the document date through for stage 5.
        if doc.get('document_date'):
            coded['document_date'] = doc['document_date']

        counts = {k: len(v) for k, v in coded['entities'].items()}
        total += sum(counts.values())
        result['documents'].append(coded)
        print(f"OK ({counts['conditions']}c/{counts['medications']}m/{counts['labs']}l)")

    result['unmapped'] = unmapped_all

    output = entities_file.replace('_entities.json', '_coded.json')
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)

    unmapped_count = sum(len(v) for v in unmapped_all.values())
    mapped = total - unmapped_count
    print(f"\nMapped {mapped}/{total} facts ({100 * mapped // total if total else 0}%)")
    for kind, terms in unmapped_all.items():
        if terms:
            # These are dropped by stage 5, which builds no resource without a code.
            print(f"  {len(terms)} {kind} unmapped, e.g. {terms[0][:60]!r}")
    print(f"\nSaved: {output}\n")
