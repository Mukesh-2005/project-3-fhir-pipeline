#!/usr/bin/env python3
"""
STAGE 3: ENTITY EXTRACTION (CHUNKED)
Splits each document on sentence boundaries and sends every chunk, so no
document text is discarded before extraction.
Input: _content.json
Output: _entities.json
"""

import json
import sys
import re
from datetime import date
from pathlib import Path
from anthropic import Anthropic

client = Anthropic()

# Chunk budget in characters. Sized so a typical progress note is one or two
# calls, and overlap carries a fact that straddles a boundary into both chunks.
CHUNK_CHARS = 6000
CHUNK_OVERLAP = 400

ENTITY_KEYS = ('conditions', 'medications', 'allergies', 'labs')

# Sentence-ish boundary: terminal punctuation followed by whitespace, or any
# newline. Clinical text is line-oriented, so newlines are hard boundaries.
_BOUNDARY = re.compile(r'(?<=[.!?;:])\s+|\n+')


def empty_entities():
    """A fresh empty result, so callers never share a mutable default."""
    return {key: [] for key in ENTITY_KEYS}


def split_sentences(text):
    """Split text into sentence-like units."""
    return [part.strip() for part in _BOUNDARY.split(text) if part and part.strip()]


def chunk_text(text, size=CHUNK_CHARS, overlap=CHUNK_OVERLAP):
    """Pack sentences into chunks of at most `size` chars, with sentence-aligned overlap."""
    if not text.strip():
        return []
    if len(text) <= size:
        return [text]

    overlap = min(overlap, size // 4)
    chunks, current, current_len = [], [], 0

    for sentence in split_sentences(text):
        # A single unit longer than a whole chunk (dense table rows) is hard-split.
        if len(sentence) > size:
            if current:
                chunks.append(' '.join(current))
                current, current_len = [], 0
            chunks.extend(sentence[i:i + size] for i in range(0, len(sentence), size))
            continue

        if current_len + len(sentence) + 1 > size:
            chunks.append(' '.join(current))
            # Carry the trailing sentences forward as overlap.
            tail, tail_len = [], 0
            for previous in reversed(current):
                if tail_len + len(previous) + 1 > overlap:
                    break
                tail.insert(0, previous)
                tail_len += len(previous) + 1
            current, current_len = tail, tail_len

        current.append(sentence)
        current_len += len(sentence) + 1

    if current:
        chunks.append(' '.join(current))
    return chunks


# ------------------------------------------------------------------
# Document dates
# Every fact used to be stamped with the time the pipeline ran, which made the
# encounters impossible to order. The date is recovered here, where the raw
# document text is still available.
# ------------------------------------------------------------------

MONTHS = {m: i for i, m in enumerate(
    ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
     'jul', 'aug', 'sep', 'oct', 'nov', 'dec'], 1)}

# A labelled clinical date is far more trustworthy than the first date on the
# page. Word-bounded so "DOS" cannot match inside an unrelated word.
DATE_LABELS = re.compile(
    r'\b(?:date\s+of\s+(?:service|visit|admission|discharge|exam(?:ination)?|study)'
    r'|service\s+date|visit\s+date|encounter\s+date|dos|admitted|discharged'
    r'|visit\s*\d*\s*|date)\b\s*[:\-]?\s*', re.I)

# Dates that are metadata about the paperwork, not about the patient. These
# records carry a "PRODUCED 01/22/2025" litigation footer on every page, which
# would otherwise be read as the date of service for the whole chart.
EXCLUDED_CONTEXT = re.compile(
    r'\b(?:produced|generated|printed|created|revised|filed|received|'
    r'dob|date\s+of\s+birth|born|claim)\b[^\n]{0,16}$', re.I)

# The patient's own birth date, which must never become a date of service.
DOB_LABEL = re.compile(r'\b(?:dob|date\s+of\s+birth|born)\b\s*[:\-]?\s*$', re.I)
AGE_SUFFIX = re.compile(r'\s*\(?\s*age\b', re.I)

NUMERIC_DATE = re.compile(r'(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})(?!\d)')
ISO_DATE = re.compile(r'(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)')
TEXT_DATE = re.compile(
    r'(?<!\w)(' + '|'.join(MONTHS) + r')[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})(?!\d)', re.I)


def to_iso(year, month, day):
    """Validate and format a date, or None if it is not a real calendar date."""
    year = int(year)
    if year < 100:
        year += 2000 if year < 50 else 1900
    try:
        return date(year, int(month), int(day)).isoformat()
    except ValueError:
        return None


def excluded(text, position):
    """
    True when the text just before a date marks it as paperwork metadata.

    The lookback stops at the start of the line: "PRODUCED 01/22/2025" must not
    suppress a genuine date on the following line.
    """
    line_start = text.rfind('\n', 0, position) + 1
    return bool(EXCLUDED_CONTEXT.search(text[max(line_start, position - 40):position]))


def dates_in(text, skip_excluded=True):
    """Parseable dates in `text` as (start, end, iso), earliest position first."""
    found = []
    for match in NUMERIC_DATE.finditer(text):
        # US clinical convention: month first.
        found.append((match.start(), match.end(),
                      to_iso(match.group(3), match.group(1), match.group(2))))
    for match in ISO_DATE.finditer(text):
        found.append((match.start(), match.end(), to_iso(*match.groups())))
    for match in TEXT_DATE.finditer(text):
        found.append((match.start(), match.end(),
                      to_iso(match.group(3), MONTHS[match.group(1)[:3].lower()], match.group(2))))
    return sorted((start, end, iso) for start, end, iso in found
                  if iso and not (skip_excluded and excluded(text, start)))


def birth_dates(text, raw):
    """
    Every date the document identifies as the patient's birth date.

    These charts repeat the DOB on each page banner, sometimes bare on its own
    line as "03/14/1987 (Age 36)" with no label. Learning the value once lets
    it be rejected wherever it appears.
    """
    found = set()
    for start, end, iso in raw:
        line_start = text.rfind('\n', 0, start) + 1
        before = text[max(line_start, start - 40):start]
        if DOB_LABEL.search(before) or AGE_SUFFIX.match(text[end:end + 16]):
            found.add(iso)
    return found


def find_document_date(text):
    """
    The document's service date, and every clinical date it contains.

    A date immediately following a label such as "Date of Service" wins;
    otherwise the earliest remaining date is used. Birth dates and paperwork
    metadata (the "PRODUCED" litigation footer) are never eligible. Returns
    (None, []) when the document carries no date, which is left unset rather
    than guessed.

    A document merging several visits has more than one real date; the extras
    are returned so the loss stays visible rather than silent.
    """
    raw = dates_in(text, skip_excluded=False)
    dob = birth_dates(text, raw)

    candidates = [(start, iso) for start, _, iso in raw
                  if iso not in dob and not excluded(text, start)]
    all_dates = sorted({iso for _, iso in candidates})

    for label in DATE_LABELS.finditer(text):
        if excluded(text, label.start() + len(label.group())):
            continue
        window = text[label.end():label.end() + 32]
        nearby = [(start, iso) for start, _, iso in dates_in(window, skip_excluded=False)
                  if iso not in dob]
        if nearby and nearby[0][0] <= 2:
            return nearby[0][1], all_dates

    return (candidates[0][1] if candidates else None), all_dates


def build_prompt(chunk, doc_type, part, total):
    """Prompt for one chunk. Says it is an excerpt so nothing is invented to fill gaps."""
    scope = f"excerpt {part} of {total} from a longer document" if total > 1 else "document"

    if doc_type == 'lab_report':
        return f"""Extract medical facts from this lab/diagnostic report ({scope}). Return ONLY valid JSON.

Text: {chunk}

{{
  "conditions": ["condition with findings"],
  "medications": [],
  "allergies": [],
  "labs": ["test_name: value unit", "procedure: key_finding"]
}}

Rules: JSON only. No markdown. Empty arrays OK. Be concise.
For labs, keep the numeric value and its unit in the string exactly as written
(e.g. "BP: 148/88 mmHg", "Lumbar flexion: 40 degrees"). Extract only what this
excerpt states."""

    return f"""Extract medical facts from this clinical document ({scope}). Return ONLY valid JSON.

Text: {chunk}

{{
  "conditions": ["condition1"],
  "medications": ["drug1"],
  "allergies": ["allergy1"],
  "labs": ["test: value unit"]
}}

Rules: JSON only. No markdown. Empty arrays OK.
For labs and vitals, keep the numeric value and its unit in the string exactly
as written (e.g. "BP: 148/88 mmHg", "HR: 96 bpm"). Extract only what this
excerpt states."""


def parse_response(response_text):
    """Parse the model's JSON, tolerating markdown fences and surrounding prose."""
    if response_text.startswith('```'):
        response_text = re.sub(r'^```(?:json)?\s*', '', response_text)
        response_text = re.sub(r'\s*```$', '', response_text)
    response_text = response_text.strip()

    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
    print(f" [Parse error - response: {response_text[:50]}]", end="")
    return None


def extract_chunk(chunk, doc_type, part, total):
    """Send one chunk and return its entities, or None if the call or parse failed."""
    max_tokens = 1500 if doc_type == 'lab_report' else 1000

    try:
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": build_prompt(chunk, doc_type, part, total)}],
        )
    except Exception as exc:
        print(f" [API error: {str(exc)[:30]}]", end="")
        return None

    # Find the first text block; extended thinking prepends ThinkingBlocks.
    response_text = ""
    for block in response.content:
        if hasattr(block, 'text'):
            response_text = block.text.strip()
            break

    if not response_text:
        print(" [No text in response]", end="")
        return None

    return parse_response(response_text)


def normalize(item):
    """Comparable form of an entity, for cross-chunk deduplication."""
    if isinstance(item, (dict, list)):
        return json.dumps(item, sort_keys=True).lower()
    return re.sub(r'\s+', ' ', str(item)).strip().lower()


def merge_entities(chunk_results):
    """Union entity lists across chunks, preserving order and dropping duplicates."""
    merged = empty_entities()
    for key in ENTITY_KEYS:
        seen = set()
        for result in chunk_results:
            for item in result.get(key) or []:
                fingerprint = normalize(item)
                if fingerprint and fingerprint not in seen:
                    seen.add(fingerprint)
                    merged[key].append(item)
    return merged


def extract_entities(text, doc_type):
    """Extract entities from a full document by chunking it and merging the results."""
    chunks = chunk_text(text)
    if not chunks:
        return empty_entities(), 0, 0

    results = []
    failed = 0
    for index, chunk in enumerate(chunks, 1):
        parsed = extract_chunk(chunk, doc_type, index, len(chunks))
        if parsed is None:
            failed += 1
        else:
            results.append(parsed)

    return merge_entities(results), len(chunks), failed


if __name__ == '__main__':
    content_file = sys.argv[1] if len(sys.argv) > 1 else 'whitfield_content.json'

    if not Path(content_file).exists():
        print(f"ERROR: {content_file} not found")
        sys.exit(1)

    with open(content_file, encoding='utf-8') as f:
        content = json.load(f)

    print("\nSTAGE 3: Entity Extraction (Chunked)")
    print(f"Processing: {content_file}\n")

    result = {'pdf_file': content['pdf_file'], 'documents': []}
    total_chars = 0
    total_failed = 0

    for i, doc in enumerate(content['documents'], 1):
        raw_text = doc['raw_text']
        total_chars += len(raw_text)
        print(f"Document {i}: {doc['type']}...", end=" ")

        entities, chunk_count, failed = extract_entities(raw_text, doc['type'])
        total_failed += failed

        fact_count = sum(len(entities.get(key, [])) for key in ('conditions', 'medications', 'labs'))

        document_date, all_dates = find_document_date(raw_text)

        result['documents'].append({
            'type': doc['type'],
            'pages': doc['pages'],
            'chunks': chunk_count,
            'chunks_failed': failed,
            'document_date': document_date,
            'dates_found': all_dates,
            'entities': entities,
        })

        marker = "OK " if fact_count > 0 else "(!)"
        detail = f"{document_date or 'no date'}, {chunk_count} chunk(s), {len(raw_text)} chars"
        if failed:
            detail += f", {failed} FAILED"
        print(f"{marker} ({fact_count} facts | {detail})")

    output = content_file.replace('_content.json', '_entities.json')
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)

    grand_total = sum(
        len(d['entities'].get(k, [])) for d in result['documents']
        for k in ('conditions', 'medications', 'labs')
    )
    undated = [d for d in result['documents'] if not d.get('document_date')]
    print(f"\n{total_chars} chars sent in full (0 discarded)")
    print(f"Dated {len(result['documents']) - len(undated)}/{len(result['documents'])} documents")
    if undated:
        print(f"  {len(undated)} undated; those facts are left without a date rather than guessed")
    print(f"Total facts: {grand_total}")
    if total_failed:
        print(f"WARNING: {total_failed} chunk(s) failed and contributed no facts")
    print(f"\nSaved: {output}\n")
