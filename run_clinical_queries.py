#!/usr/bin/env python3
"""
CLINICAL QUERIES OVER THE PERSISTED FHIR DATA

Reads the database written by stage 6. Nothing here is hardcoded: the
validation status is read back from the stage 5 output rather than asserted,
and every count comes from the database.
"""

import json
import sqlite3
import sys
from pathlib import Path

# Keep the checkmarks printable when stdout is redirected to a file or a
# pipe, which on Windows defaults to cp1252 and cannot encode them.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DB_PATH = 'fhir_data.db'
FHIR_PATH = 'whitfield_fhir.json'
OUTPUT_PATH = 'clinical_queries_results.json'

# Shown instead of the full URL, which is too wide for a terminal table.
SYSTEM_NAMES = {
    'http://hl7.org/fhir/sid/icd-10-cm': 'ICD-10-CM',
    'http://snomed.info/sct': 'SNOMED CT',
    'http://loinc.org': 'LOINC',
    'http://www.nlm.nih.gov/research/umls/rxnorm': 'RxNorm',
}


def system_name(url):
    """A short label for a code system URL."""
    if not url:
        return 'uncoded'
    return SYSTEM_NAMES.get(url, url.rsplit('/', 1)[-1])


def heading(number, title):
    print(f'\nQUERY {number}: {title}')
    print('=' * 70)


def show(rows, formatter, limit=15):
    """Print up to `limit` rows, saying how many were withheld."""
    for row in rows[:limit]:
        print(f'  {formatter(row)}')
    if len(rows) > limit:
        print(f'  ... and {len(rows) - limit} more')


def validation_status(path=FHIR_PATH):
    """
    The validation result recorded by stage 5.

    Read back rather than assumed: this script used to print "FHIR validation:
    PASS" unconditionally, which said nothing about the data.
    """
    if not Path(path).exists():
        return f'unknown ({path} not found)'

    with open(path, encoding='utf-8') as handle:
        validation = json.load(handle).get('validation', {})

    valid = validation.get('valid')
    validator = validation.get('validator', 'unknown validator')
    if valid is True:
        return f'PASS ({validator})'
    if valid is None:
        return f'NOT VALIDATED ({validator})'
    return f'FAIL - {validation.get("error_count", "?")} error(s) ({validator})'


def main():
    if not Path(DB_PATH).exists():
        print(f'ERROR: {DB_PATH} not found. Run stage6_.py first.')
        return 1

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # A schema older than stage 6's current layout lacks the columns below.
    columns = {row[1] for row in cursor.execute('PRAGMA table_info(conditions)')}
    if 'system' not in columns:
        print('ERROR: database predates the current schema. Re-run stage6_.py.')
        conn.close()
        return 1

    results = {'validation': validation_status()}

    # Query 1: conditions, with the system each code actually belongs to.
    heading(1, 'Conditions with Codes and Code Systems')
    cursor.execute('''
        SELECT DISTINCT code, system, display FROM conditions ORDER BY display
    ''')
    conditions = cursor.fetchall()
    results['query_1_conditions'] = [
        {'code': c, 'system': s, 'display': d} for c, s, d in conditions]
    print(f'Found {len(conditions)} unique conditions:')
    show(conditions, lambda r: f'[{r[0] or "-":<10}] {system_name(r[1]):<10} {r[2]}')

    # Query 2: medications.
    heading(2, 'Medications with Doses and Status')
    cursor.execute('''
        SELECT DISTINCT drug_name, code, system, dose, status
        FROM medications ORDER BY drug_name
    ''')
    meds = cursor.fetchall()
    results['query_2_medications'] = [
        {'drug': d, 'code': c, 'system': s, 'dose': dose, 'status': st}
        for d, c, s, dose, st in meds]
    print(f'Found {len(meds)} unique medications:')
    show(meds, lambda r: f'{r[0]} [{r[1] or "-"}] {r[3] or "no dose"} - {r[4]}')

    # Query 3: observations. Paired readings (blood pressure) and qualitative
    # findings live in value_text, so filtering on `value` alone hid them.
    heading(3, 'Observations with Results')
    cursor.execute('''
        SELECT display, value, unit, value_text, date
        FROM observations
        WHERE value IS NOT NULL OR value_text IS NOT NULL
        ORDER BY date, display
    ''')
    labs = cursor.fetchall()
    results['query_3_observations'] = [
        {'test': t, 'value': v, 'unit': u, 'value_text': vt, 'date': d}
        for t, v, u, vt, d in labs]

    cursor.execute('SELECT COUNT(*) FROM observations')
    total_obs = cursor.fetchone()[0]
    print(f'Found {len(labs)} of {total_obs} observations carrying a result:')
    show(labs, lambda r: f'{(r[4] or "")[:10]:<11}{r[0]}: '
                         f'{r[1] if r[1] is not None else r[3]} {r[2] or ""}'.rstrip())

    # Query 4: code frequency.
    heading(4, 'Conditions by Code Frequency')
    cursor.execute('''
        SELECT code, system, COUNT(*) AS freq FROM conditions
        GROUP BY code, system ORDER BY freq DESC, code
    ''')
    frequency = cursor.fetchall()
    results['query_4_code_frequency'] = [
        {'code': c, 'system': s, 'count': n} for c, s, n in frequency]
    print(f'{len(frequency)} distinct codes:')
    show(frequency, lambda r: f'[{r[0] or "-":<10}] {system_name(r[1]):<10} {r[2]} occurrence(s)',
         limit=10)

    # Query 5: the clinical timeline. This only became answerable once facts
    # carried the document's own date instead of the pipeline's run time.
    heading(5, 'Clinical Timeline by Encounter')
    cursor.execute('''
        SELECT e.start, e.type,
               (SELECT COUNT(*) FROM conditions c WHERE c.encounter_id = e.id),
               (SELECT COUNT(*) FROM observations o WHERE o.encounter_id = e.id)
        FROM encounters e
        ORDER BY COALESCE(e.start, '9999'), e.type
    ''')
    timeline = cursor.fetchall()
    results['query_5_timeline'] = [
        {'date': (start or '')[:10] or None, 'type': kind,
         'conditions': nc, 'observations': no}
        for start, kind, nc, no in timeline]
    dated = sum(1 for row in timeline if row[0])
    print(f'{len(timeline)} encounters ({dated} dated):')
    show(timeline,
         lambda r: f'{(r[0] or "undated")[:10]:<11}{r[1]:<20}'
                   f'{r[2]:>3} conditions, {r[3]:>3} observations',
         limit=20)

    # Query 6: summary.
    heading(6, 'Pipeline Summary Statistics')
    counts = {}
    for table in ('patients', 'encounters', 'conditions', 'medications', 'observations'):
        cursor.execute(f'SELECT COUNT(*) FROM {table}')
        counts[table] = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM conditions WHERE code IS NULL')
    counts['conditions_uncoded'] = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT source) FROM patients")
    counts['sources'] = cursor.fetchone()[0]
    cursor.execute('SELECT MIN(start), MAX(start) FROM encounters WHERE start IS NOT NULL')
    earliest, latest = cursor.fetchone()

    facts = counts['conditions'] + counts['medications'] + counts['observations']
    results['query_6_summary'] = dict(counts, total_facts=facts,
                                      earliest=earliest, latest=latest)

    print(f'Source records:          {counts["sources"]}')
    print(f'Patient records:         {counts["patients"]}')
    print(f'Encounters:              {counts["encounters"]}')
    print(f'Conditions coded:        {counts["conditions"]}')
    print(f'Medications:             {counts["medications"]}')
    print(f'Observations:            {counts["observations"]}')
    print(f'Total structured facts:  {facts}')
    if earliest and latest:
        print(f'Clinical date range:     {earliest[:10]} to {latest[:10]}')
    print(f'FHIR validation:         {results["validation"]}')

    conn.close()

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as handle:
        json.dump(results, handle, indent=2)

    print('\n' + '=' * 70)
    print('✓ All 6 clinical queries demonstrated')
    print(f'✓ Results saved to {OUTPUT_PATH}')
    print('=' * 70)
    return 0


if __name__ == '__main__':
    sys.exit(main())
