#!/usr/bin/env python3
"""
STAGE 1: PAGE-WISE GROUPING & DOCUMENT SEGMENTATION (FIXED - CLEAN VERSION)
Reads a PDF, classifies each page, detects document boundaries.
"""

import json
import sys
from pathlib import Path
from pypdf import PdfReader
from anthropic import Anthropic

client = Anthropic()

def extract_text_from_page(pdf_path, page_num):
    """Extract text from a specific page."""
    pdf = PdfReader(pdf_path)
    page = pdf.pages[page_num]
    return page.extract_text()

def classify_page_with_llm(page_text):
    """Use Claude to classify page type."""
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=100,
        messages=[{
            "role": "user",
            "content": f"""Classify this medical document page into ONE category only.
            
Categories: discharge_summary, progress_note, lab_report, radiology_report, intake_form, insurance, cover_sheet, blank, duplicate, unknown

Page text:
{page_text[:500]}

Answer ONLY the category name, nothing else."""
        }]
    )
    return response.content[0].text.strip().lower()

def detect_layout_signals(page_text):
    """Look for boundary signals."""
    signals = {
        'has_page_marker': bool('page' in page_text.lower() and 'of' in page_text.lower()),
        'has_letterhead': bool('hospital' in page_text.lower() or 'clinic' in page_text.lower() or 'medical' in page_text.lower()),
        'has_section_header': bool('discharge' in page_text.lower() or 'summary' in page_text.lower() or 'diagnoses' in page_text.lower()),
        'is_mostly_empty': len(page_text.strip()) < 100,
    }
    return signals

def segment_pdf(pdf_path):
    """Main segmentation function."""
    pdf = PdfReader(pdf_path)
    total_pages = len(pdf.pages)
    
    results = {
        'pdf_file': pdf_path,
        'total_pages': total_pages,
        'pages': [],
        'documents': [],
    }
    
    print(f"\n{'='*60}")
    print(f"Processing: {pdf_path}")
    print(f"Total pages: {total_pages}")
    print(f"{'='*60}\n")
    
    # Classify each page
    for page_num in range(total_pages):
        print(f"Processing page {page_num + 1}/{total_pages}...", end=" ")
        
        page_text = extract_text_from_page(pdf_path, page_num)
        
        # Skip blank pages
        if len(page_text.strip()) < 50:
            page_type = 'blank'
            confidence = 1.0
        else:
            # LLM classification
            llm_type = classify_page_with_llm(page_text)
            
            # Layout signals
            layout = detect_layout_signals(page_text)
            
            # Simple voting (LLM gets more weight)
            page_type = llm_type
            confidence = 0.85 if not layout['is_mostly_empty'] else 0.7
        
        page_info = {
            'page_num': page_num + 1,
            'type': page_type,
            'confidence': confidence,
            'text_length': len(page_text),
        }
        
        results['pages'].append(page_info)
        print(f"{page_type} (conf: {confidence:.2f})")
    
    # Group pages into documents (simple grouping)
    if results['pages']:
        current_doc = {
            'type': results['pages'][0]['type'],
            'pages': [results['pages'][0]['page_num']],
        }
        
        for page in results['pages'][1:]:
            # New document if:
            # - Type changes
            # - Low confidence
            # - Blank page found
            if page['type'] != current_doc['type'] or page['confidence'] < 0.7 or page['type'] == 'blank':
                results['documents'].append(current_doc)
                current_doc = {
                    'type': page['type'],
                    'pages': [page['page_num']],
                }
            else:
                current_doc['pages'].append(page['page_num'])
        
        # Add last document
        if current_doc['pages']:
            results['documents'].append(current_doc)
    
    return results

def print_results(results):
    """Print segmentation results."""
    print(f"\n{'='*60}")
    print("SEGMENTATION RESULTS")
    print(f"{'='*60}")
    
    print("\nPAGE-BY-PAGE CLASSIFICATION:")
    for page in results['pages']:
        print(f"  Page {page['page_num']:2d}: {page['type']:20s} (confidence: {page['confidence']:.2f})")
    
    print("\nDOCUMENT GROUPING:")
    for i, doc in enumerate(results['documents'], 1):
        page_range = f"pages {doc['pages'][0]}-{doc['pages'][-1]}" if len(doc['pages']) > 1 else f"page {doc['pages'][0]}"
        print(f"  Document {i}: {doc['type']:20s} ({page_range})")
    
    print(f"\nTotal documents found: {len(results['documents'])}")
    print(f"{'='*60}\n")

# ============================================================
# MAIN - Run ONLY Stage 1
# ============================================================

if __name__ == '__main__':
    
    if len(sys.argv) < 2:
        pdf_file = 'whitfield.pdf'
    else:
        pdf_file = sys.argv[1]
    
    print("\n" + "="*60)
    print("STAGE 1: PAGE-WISE SEGMENTATION")
    print("="*60)
    
    # Check file exists
    if not Path(pdf_file).exists():
        print(f"❌ PDF file not found: {pdf_file}")
        sys.exit(1)
    
    # Run segmentation
    results = segment_pdf(pdf_file)
    print_results(results)
    
    # Save results
    output_file = pdf_file.replace('.pdf', '_segmentation.json')
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"✓ Results saved to: {output_file}")