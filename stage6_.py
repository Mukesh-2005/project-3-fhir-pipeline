#!/usr/bin/env python3
"""
STAGE 6: PERSISTENCE & QUERYABILITY ONLY
Does NOT call any other stages.
Input: _fhir.json
Output: Database file + query results

Loading is idempotent: every row records the source record it came from, and
reloading a source replaces its rows instead of adding a second copy. Without
that, each run minted fresh UUIDs and INSERT OR REPLACE never matched, so the
database accumulated one phantom patient per run.
"""

import json
import shutil
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

# Keep the checkmarks printable when stdout is redirected to a file or a
# pipe, which on Windows defaults to cp1252 and cannot encode them.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Rows are deleted parent-last so foreign keys stay satisfied.
TABLES_CHILD_FIRST = ('observations', 'conditions', 'medications',
                      'encounters', 'patients')


def reference_id(resource, field):
    """The bare id from a FHIR reference such as {"reference": "Patient/abc"}."""
    return (resource.get(field, {}) or {}).get('reference', '').split('/')[-1] or None


def first_coding_code(concept):
    """The first coding's code from a CodeableConcept, or None."""
    return ((concept or {}).get('coding') or [{}])[0].get('code')


def as_text(value):
    """A column-safe string, since extraction can hand back a dict."""
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


class FHIRStore:
    def __init__(self, db_path='fhir_data.db'):
        """Open the database, rebuilding it if it predates the scoped schema."""
        self.db_path = Path(db_path)

        if self.needs_rebuild():
            backup = self.db_path.with_suffix('.legacy.bak')
            shutil.copy2(self.db_path, backup)
            print(f"! Existing database uses the old unscoped schema.")
            print(f"  Backed up to {backup.name}, then rebuilt.")
            self.rebuild = True
        else:
            self.rebuild = False

        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute('PRAGMA foreign_keys = ON')
        self.cursor = self.conn.cursor()
        self.setup_tables()

    def needs_rebuild(self):
        """True when an existing database lacks the source column or encounters."""
        if not self.db_path.exists():
            return False
        with closing(sqlite3.connect(self.db_path)) as conn:
            tables = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if not tables:
                return False
            if 'encounters' not in tables:
                return True
            columns = {row[1] for row in conn.execute("PRAGMA table_info(patients)")}
            return 'source' not in columns

    def setup_tables(self):
        """Create database tables."""
        if self.rebuild:
            for table in TABLES_CHILD_FIRST:
                self.cursor.execute(f'DROP TABLE IF EXISTS {table}')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS patients (
                id TEXT PRIMARY KEY,
                name TEXT,
                dob TEXT,
                gender TEXT,
                mrn TEXT,
                source TEXT
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS encounters (
                id TEXT PRIMARY KEY,
                patient_id TEXT,
                type TEXT,
                status TEXT,
                start TEXT,
                source TEXT,
                FOREIGN KEY (patient_id) REFERENCES patients(id)
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS conditions (
                id TEXT PRIMARY KEY,
                patient_id TEXT,
                encounter_id TEXT,
                code TEXT,
                display TEXT,
                source TEXT,
                FOREIGN KEY (patient_id) REFERENCES patients(id)
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS observations (
                id TEXT PRIMARY KEY,
                patient_id TEXT,
                encounter_id TEXT,
                code TEXT,
                display TEXT,
                value REAL,
                unit TEXT,
                value_text TEXT,
                date TEXT,
                source TEXT,
                FOREIGN KEY (patient_id) REFERENCES patients(id)
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS medications (
                id TEXT PRIMARY KEY,
                patient_id TEXT,
                drug_name TEXT,
                code TEXT,
                dose TEXT,
                status TEXT,
                source TEXT,
                FOREIGN KEY (patient_id) REFERENCES patients(id)
            )
        ''')

        for table in ('encounters', 'conditions', 'observations', 'medications'):
            self.cursor.execute(
                f'CREATE INDEX IF NOT EXISTS idx_{table}_source ON {table}(source)')
            self.cursor.execute(
                f'CREATE INDEX IF NOT EXISTS idx_{table}_patient ON {table}(patient_id)')

        self.conn.commit()

    def clear_source(self, source):
        """Drop every row previously loaded from this source."""
        removed = 0
        for table in TABLES_CHILD_FIRST:
            self.cursor.execute(f'DELETE FROM {table} WHERE source = ?', (source,))
            removed += self.cursor.rowcount
        return removed

    def store_bundle(self, bundle, source):
        """
        Store a FHIR bundle, replacing anything already loaded from `source`.

        The clear and the reload are one transaction, so a bundle that fails
        partway leaves the previous contents intact rather than half-deleted.
        """
        # Patients first so the foreign keys on the other tables resolve.
        entries = bundle.get('entry', [])
        ordered = sorted(entries,
                         key=lambda e: e.get('resource', {}).get('resourceType') != 'Patient')

        handlers = {
            'Patient': self.store_patient,
            'Encounter': self.store_encounter,
            'Condition': self.store_condition,
            'Observation': self.store_observation,
            'MedicationStatement': self.store_medication,
        }

        stored = 0
        with self.conn:  # commits on success, rolls back on any exception
            replaced = self.clear_source(source)
            for entry in ordered:
                resource = entry.get('resource', {})
                handler = handlers.get(resource.get('resourceType'))
                if handler:
                    handler(resource, source)
                    stored += 1

        return replaced, stored

    def store_patient(self, resource, source):
        """Store patient."""
        name = None
        if resource.get('name'):
            given = (resource['name'][0].get('given') or [''])[0]
            family = resource['name'][0].get('family', '')
            name = f"{given} {family}".strip()

        identifiers = resource.get('identifier') or [{}]

        self.cursor.execute('''
            INSERT OR REPLACE INTO patients (id, name, dob, gender, mrn, source)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (resource.get('id'), name, resource.get('birthDate'),
              resource.get('gender'), identifiers[0].get('value'), source))

    def store_encounter(self, resource, source):
        """Store encounter, so facts can be traced back to a visit."""
        types = resource.get('type') or [{}]
        self.cursor.execute('''
            INSERT OR REPLACE INTO encounters (id, patient_id, type, status, start, source)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (resource.get('id'), reference_id(resource, 'subject'),
              as_text(types[0].get('text')), resource.get('status'),
              (resource.get('period') or {}).get('start'), source))

    def store_condition(self, resource, source):
        """Store condition."""
        self.cursor.execute('''
            INSERT OR REPLACE INTO conditions
                (id, patient_id, encounter_id, code, display, source)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (resource.get('id'), reference_id(resource, 'subject'),
              reference_id(resource, 'encounter'),
              first_coding_code(resource.get('code')),
              as_text(resource.get('code', {}).get('text')), source))

    def store_observation(self, resource, source):
        """Store lab/vital, keeping numeric and non-numeric results apart."""
        value = None
        unit = None
        value_text = as_text(resource.get('valueString'))

        quantity = resource.get('valueQuantity')
        if quantity:
            raw = quantity.get('value')
            if raw is not None:  # 0 is a legitimate result
                try:
                    value = float(raw)
                except (ValueError, TypeError):
                    value_text = as_text(raw)
            unit = as_text(quantity.get('unit'))
            if quantity.get('comparator'):
                value_text = f"{quantity['comparator']}{raw}"

        # Paired readings (blood pressure) live in components, not a single value.
        components = resource.get('component')
        if components and value is None:
            parts = []
            for component in components:
                component_quantity = component.get('valueQuantity') or {}
                label = ((component.get('code', {}).get('coding') or [{}])[0]
                         .get('display', ''))
                parts.append(f"{label}: {component_quantity.get('value')} "
                             f"{component_quantity.get('unit', '')}".strip())
            value_text = "; ".join(parts)

        self.cursor.execute('''
            INSERT OR REPLACE INTO observations
                (id, patient_id, encounter_id, code, display, value, unit, value_text, date, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (resource.get('id'), reference_id(resource, 'subject'),
              reference_id(resource, 'encounter'),
              first_coding_code(resource.get('code')),
              as_text(resource.get('code', {}).get('text')),
              value, unit, value_text,
              resource.get('effectiveDateTime'), source))

    def store_medication(self, resource, source):
        """Store medication."""
        concept = resource.get('medicationCodeableConcept', {})
        dose = None
        if resource.get('dosage'):
            dose = as_text(resource['dosage'][0].get('text'))

        self.cursor.execute('''
            INSERT OR REPLACE INTO medications
                (id, patient_id, drug_name, code, dose, status, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (resource.get('id'), reference_id(resource, 'subject'),
              as_text(concept.get('text')), first_coding_code(concept),
              dose, resource.get('status', 'unknown'), source))

    # Demo Queries
    def query_conditions(self):
        """Query 1: All conditions."""
        self.cursor.execute('SELECT code, display FROM conditions ORDER BY display')
        return [{'code': row[0], 'condition': row[1]} for row in self.cursor.fetchall()]

    def query_medications(self):
        """Query 2: All medications."""
        self.cursor.execute('SELECT drug_name, dose, status FROM medications ORDER BY drug_name')
        return [{'drug': row[0], 'dose': row[1], 'status': row[2]} for row in self.cursor.fetchall()]

    def query_labs(self):
        """Query 3: All lab results."""
        self.cursor.execute(
            'SELECT display, value, unit, value_text FROM observations ORDER BY display')
        results = []
        for display, value, unit, value_text in self.cursor.fetchall():
            results.append({
                'test': display,
                'value': value if value is not None else (value_text or 'N/A'),
                'unit': unit,
            })
        return results

    def query_all_patients(self):
        """Query 4: All patients."""
        self.cursor.execute('SELECT id, name, source FROM patients')
        return [{'id': row[0], 'name': row[1], 'source': row[2]}
                for row in self.cursor.fetchall()]

    def query_encounters(self):
        """Query 5: Encounters with the number of facts recorded against each."""
        self.cursor.execute('''
            SELECT e.id, e.type,
                   (SELECT COUNT(*) FROM conditions c WHERE c.encounter_id = e.id),
                   (SELECT COUNT(*) FROM observations o WHERE o.encounter_id = e.id)
            FROM encounters e ORDER BY e.type
        ''')
        return [{'encounter': row[0], 'type': row[1],
                 'conditions': row[2], 'observations': row[3]}
                for row in self.cursor.fetchall()]

    def query_summary(self):
        """Query 6: Complete summary."""
        return {
            'conditions': self.query_conditions(),
            'medications': self.query_medications(),
            'labs': self.query_labs(),
        }

    def row_counts(self):
        """Row count per table, for reporting what the load actually left behind."""
        counts = {}
        for table in TABLES_CHILD_FIRST:
            self.cursor.execute(f'SELECT COUNT(*) FROM {table}')
            counts[table] = self.cursor.fetchone()[0]
        return counts

    def close(self):
        """Close database."""
        self.conn.close()


def bundle_source(fhir_data, fhir_file):
    """Which record this bundle came from; a reload of it replaces its rows."""
    return fhir_data.get('source_file') or Path(fhir_file).name.replace('_fhir.json', '')


if __name__ == '__main__':
    fhir_file = sys.argv[1] if len(sys.argv) > 1 else 'whitfield_fhir.json'

    if not Path(fhir_file).exists():
        print(f"ERROR: {fhir_file} not found")
        sys.exit(1)

    with open(fhir_file, encoding='utf-8') as f:
        fhir_data = json.load(f)

    print(f"\nSTAGE 6: Persistence & Queryability\nProcessing: {fhir_file}\n")

    source = bundle_source(fhir_data, fhir_file)
    store = FHIRStore()
    replaced, stored = store.store_bundle(fhir_data['bundle'], source)

    if replaced:
        print(f"✓ Replaced {replaced} existing row(s) for source '{source}'")
    print(f"✓ Stored {stored} resources from source '{source}'")

    counts = store.row_counts()
    print("  " + ", ".join(f"{table}: {count}" for table, count in counts.items()))

    queries = {
        'source': source,
        'conditions': store.query_conditions(),
        'medications': store.query_medications(),
        'labs': store.query_labs(),
        'patients': store.query_all_patients(),
        'encounters': store.query_encounters(),
        'summary': store.query_summary(),
    }

    store.close()

    output = fhir_file.replace('_fhir.json', '_queries.json')
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(queries, f, indent=2)

    print(f"✓ Ran 6 demo queries")
    print(f"✓ Saved: {output}\n")
