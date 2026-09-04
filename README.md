<div align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=6,11,20&height=180&section=header&text=MUKESH%20K&fontSize=52&fontColor=fff&animation=twinkling&fontAlignY=32&desc=Data%20Scientist%20%7C%20ML%20Engineer&descAlignY=58&descSize=18" width="100%"/>
</div>

---
 
 # Project 3: Medical Record FHIR Pipeline

**Converts multi-document PDFs to FHIR R4B resources with real validation.**

## What It Does
PDF (22 pages, 15 documents)
↓
220 facts extracted
↓
196 FHIR resources
↓
SQLite database
↓
6 working queries


## Quick Start

```bash
python stage1_segmentation.py
python stage2_content_extraction.py
python stage3_entity_extraction.py
python stage4_terminology_normalization.py
python stage5_fhir_construction.py
python stage6_.py
python stage7_.py
python Evaluate_whitfield.py
```

**Result:** 196 FHIR R4B resources, real validation PASS ✓

## Key Metrics

- **220 facts** extracted (was 122, +80%)
- **0% data loss** (was 43%)
- **102/102 observations** with real values (was 0/41)
- **Real FHIR validation** (not fake)
- **10 distinct clinical dates** (chronological, not all run time)
- **Idempotent database** (runs 1, 2, 3 produce identical results)

## Architecture

**7 Stages:**
1. Page classification (15 documents)
2. Content extraction (full text)
3. Entity extraction (sentence chunking)
4. Terminology mapping (81% coverage)
5. FHIR construction (196 resources)
6. Database persistence (SQLite, transactional)
7. Provenance tracking (all facts traced)

## Known Issues

- 40 unmapped facts (13 conditions, 6 meds, 21 labs) — reported by name
- RxNorm codes unverified — marked in code
- Confidence & patient fields low priority

**See FAILURES.md for full audit.**

## Medical Intelligence

✓ Blood pressure → 2 LOINC components (systolic/diastolic)
✓ MMT grades → value + comparator (4+/5 → value:4, >)
✓ EMG findings → text (no invented numbers)
✓ Clinical dates → chronological (ED → surgery → discharge)

## Validation

```bash
# Run queries
python run_clinical_queries.py

# Check validation
# FHIR R4B: PASS ✓ (real validator, not fake)
```

## Tech Stack

- **Python 3.11**
- **Claude API** (entity extraction)
- **fhir.resources 8.3.0** (R4B validation)
- **SQLite** (persistence)
- **PyPDF** (text extraction)

## Files

- `stage1-7_.py` — Pipeline stages
- `Evaluate_whitfield.py` — Validation
- `run_clinical_queries.py` — Database queries
- `FAILURES.md` — Bug audit
- `whitfield.pdf` — Test document
