#!/usr/bin/env python3
"""
STAGE 3: ENTITY EXTRACTION (ROBUST VERSION)
Handles large lab reports with better error handling
Input: _content.json
Output: _entities.json
"""

import json
import sys
import re
from pathlib import Path
from anthropic import Anthropic

client = Anthropic()

def extract_entities(text, doc_type):
    """Extract medical entities using Claude with robust parsing."""
    
    # For lab reports, limit the amount of text sent
    if doc_type == 'lab_report':
        text_to_send = text[:2500]  # Increase for complex lab reports
    else:
        text_to_send = text[:2000]
    
    # Customize prompt based on document type
    if doc_type == 'lab_report':
        prompt = f"""Extract medical facts from this lab/diagnostic report. Return ONLY valid JSON.

Text: {text_to_send}

{{
  "conditions": ["condition with findings"],
  "medications": [],
  "allergies": [],
  "labs": ["test_name: result (normal/abnormal)", "procedure: key_finding"]
}}

Rules: JSON only. No markdown. Empty arrays OK. Be concise."""
    else:
        prompt = f"""Extract medical facts from this clinical document. Return ONLY valid JSON.

Text: {text_to_send}

{{
  "conditions": ["condition1"],
  "medications": ["drug1"],
  "allergies": ["allergy1"],
  "labs": ["test: value"]
}}

Rules: JSON only. No markdown. Empty arrays OK."""
    
    try:
        # Increase max_tokens for complex lab reports
        max_tokens = 800 if doc_type == 'lab_report' else 500
        
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=max_tokens,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        
        # Extract text from response - handle ThinkingBlock
        response_text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                response_text = block.text.strip()
                break
        
        if not response_text:
            print(f" [No text in response]", end="")
            return {"conditions": [], "medications": [], "allergies": [], "labs": []}
        
        # Remove markdown fences if present
        if response_text.startswith('```'):
            # Remove ```json or ``` prefix
            response_text = re.sub(r'^```(?:json)?\s*', '', response_text)
            # Remove ``` suffix
            response_text = re.sub(r'\s*```$', '', response_text)
        
        response_text = response_text.strip()
        
        # Try to parse JSON
        try:
            data = json.loads(response_text)
            return data
        except json.JSONDecodeError as e:
            # If JSON parsing fails, try to extract valid JSON from text
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    return data
                except:
                    pass
            
            # Fallback: return empty
            print(f" [Parse error - response: {response_text[:50]}]", end="")
            return {"conditions": [], "medications": [], "allergies": [], "labs": []}
    
    except Exception as e:
        print(f" [API error: {str(e)[:30]}]", end="")
        return {"conditions": [], "medications": [], "allergies": [], "labs": []}

if __name__ == '__main__':
    content_file = sys.argv[1] if len(sys.argv) > 1 else 'test_patient_1_content.json'
    
    if not Path(content_file).exists():
        print(f"ERROR: {content_file} not found")
        sys.exit(1)
    
    with open(content_file) as f:
        content = json.load(f)
    
    print(f"\nSTAGE 3: Entity Extraction (Robust)")
    print(f"Processing: {content_file}\n")
    
    result = {'pdf_file': content['pdf_file'], 'documents': []}
    
    for i, doc in enumerate(content['documents'], 1):
        print(f"Document {i}: {doc['type']}...", end=" ")
        
        entities = extract_entities(doc['raw_text'], doc['type'])
        
        # Count facts
        fact_count = len(entities.get('conditions', [])) + len(entities.get('medications', [])) + len(entities.get('labs', []))
        
        result['documents'].append({
            'type': doc['type'],
            'pages': doc['pages'],
            'entities': entities
        })
        
        if fact_count > 0:
            print(f"✓ ({fact_count} facts)")
        else:
            print("⚠️  (0 facts)")
    
    # Save
    output = content_file.replace('_content.json', '_entities.json')
    with open(output, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\n✓ Saved: {output}\n")