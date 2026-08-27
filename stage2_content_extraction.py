#!/usr/bin/env python3
"""
STAGE 2: CONTENT EXTRACTION ONLY
Does NOT call any other stages.
Input: PDF + _segmentation.json
Output: _content.json
"""

import json
import sys
from pathlib import Path
from pypdf import PdfReader

def extract_text_from_pages(pdf_path, page_numbers):
    """Extract text from specified pages."""
    pdf = PdfReader(pdf_path)
    text = ""
    for page_num in page_numbers:
        page_index = page_num - 1
        if page_index < len(pdf.pages):
            text += f"\n--- Page {page_num} ---\n{pdf.pages[page_index].extract_text()}\n"
    return text.strip()

def extract_tables(text):
    """Find table-like structures."""
    tables = []
    lines = text.split('\n')
    table = []
    
    for line in lines:
        if not line.strip():
            if len(table) > 2:
                tables.append(table)
            table = []
        else:
            table.append(line.strip())
    
    return tables

if __name__ == '__main__':
    pdf_file = sys.argv[1] if len(sys.argv) > 1 else 'test_patient_1.pdf'
    seg_file = pdf_file.replace('.pdf', '_segmentation.json')
    
    if not Path(pdf_file).exists() or not Path(seg_file).exists():
        print(f"ERROR: Files not found")
        sys.exit(1)
    
    with open(seg_file) as f:
        segmentation = json.load(f)
    
    print(f"\nSTAGE 2: Content Extraction\nProcessing: {pdf_file}\n")
    
    result = {'pdf_file': pdf_file, 'documents': []}
    
    for i, doc in enumerate(segmentation['documents'], 1):
        print(f"Document {i}: {doc['type']} (pages {doc['pages']})...", end=" ")
        
        text = extract_text_from_pages(pdf_file, doc['pages'])
        tables = extract_tables(text)
        
        result['documents'].append({
            'type': doc['type'],
            'pages': doc['pages'],
            'raw_text': text,  # FULL text, not truncated!
            'text_length': len(text),
            'tables_found': len(tables)
        })
        print("OK")
    
    # Save
    output = pdf_file.replace('.pdf', '_content.json')
    with open(output, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\n✓ Saved: {output}\n")