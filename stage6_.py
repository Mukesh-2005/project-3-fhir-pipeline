#!/usr/bin/env python3
"""
STAGE 6: PERSISTENCE & QUERYABILITY ONLY
Does NOT call any other stages.
Input: _fhir.json
Output: Database file + query results
"""

import json
import sys
import sqlite3
from pathlib import Path
from datetime import datetime

class FHIRStore:
    def __init__(self, db_path='fhir_data.db'):
        """Initialize database."""
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self.setup_tables()
    
    def setup_tables(self):
        """Create database tables."""
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS patients (
                id TEXT PRIMARY KEY,
                name TEXT,
                dob TEXT,
                gender TEXT,
                mrn TEXT
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS conditions (
                id TEXT PRIMARY KEY,
                patient_id TEXT,
                code TEXT,
                display TEXT,
                FOREIGN KEY (patient_id) REFERENCES patients(id)
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS observations (
                id TEXT PRIMARY KEY,
                patient_id TEXT,
                code TEXT,
                display TEXT,
                value REAL,
                unit TEXT,
                date TEXT,
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
                FOREIGN KEY (patient_id) REFERENCES patients(id)
            )
        ''')
        
        self.conn.commit()
    
    def store_bundle(self, bundle):
        """Store FHIR bundle in database."""
        for entry in bundle.get('entry', []):
            resource = entry.get('resource', {})
            rtype = resource.get('resourceType')
            
            if rtype == 'Patient':
                self.store_patient(resource)
            elif rtype == 'Condition':
                self.store_condition(resource)
            elif rtype == 'Observation':
                self.store_observation(resource)
            elif rtype == 'MedicationStatement':
                self.store_medication(resource)
        
        self.conn.commit()
    
    def store_patient(self, resource):
        """Store patient."""
        patient_id = resource.get('id')
        name = None
        if resource.get('name'):
            given = resource['name'][0].get('given', [''])[0]
            family = resource['name'][0].get('family', '')
            name = f"{given} {family}".strip()
        
        self.cursor.execute('''
            INSERT OR REPLACE INTO patients (id, name, dob, gender, mrn)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            patient_id,
            name,
            resource.get('birthDate'),
            resource.get('gender'),
            resource.get('identifier', [{}])[0].get('value') if resource.get('identifier') else None
        ))
    
    def store_condition(self, resource):
        """Store condition."""
        patient_id = resource.get('subject', {}).get('reference', '').split('/')[-1]
        code = resource.get('code', {}).get('coding', [{}])[0].get('code')
        display = resource.get('code', {}).get('text')
        
        self.cursor.execute('''
            INSERT OR REPLACE INTO conditions (id, patient_id, code, display)
            VALUES (?, ?, ?, ?)
        ''', (resource.get('id'), patient_id, code, display))
    
    def store_observation(self, resource):
        """Store lab/vital."""
        patient_id = resource.get('subject', {}).get('reference', '').split('/')[-1]
        
        # Get code safely
        code = resource.get('code', {}).get('coding', [{}])[0].get('code')
        
        # Get display safely (convert dict to string if needed)
        display = resource.get('code', {}).get('text')
        if isinstance(display, dict):
            display = str(display)
        
        # Get value safely - USE 'is not None' to handle value=0
        value = None
        unit = None
        if resource.get('valueQuantity'):
            val_qty = resource['valueQuantity']
            value_raw = val_qty.get('value')
            
            # Handle dict or simple value - check 'is not None' not truthiness
            if isinstance(value_raw, dict):
                value = str(value_raw)
            elif value_raw is not None:  # THIS IS THE FIX
                try:
                    value = float(value_raw)
                except (ValueError, TypeError):
                    value = str(value_raw)
            
            unit = val_qty.get('unit')
            if isinstance(unit, dict):
                unit = str(unit)
        
        # Ensure all params are correct types
        resource_id = str(resource.get('id')) if resource.get('id') else None
        patient_id = str(patient_id) if patient_id else None
        code = str(code) if code else None
        display = str(display) if display else None
        
        self.cursor.execute('''
            INSERT OR REPLACE INTO observations (id, patient_id, code, display, value, unit, date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            resource_id, patient_id, code, display, value, unit,
            resource.get('effectiveDateTime')
        ))
    
    def store_medication(self, resource):
        """Store medication."""
        patient_id = resource.get('subject', {}).get('reference', '').split('/')[-1]
        code = resource.get('medicationCodeableConcept', {}).get('coding', [{}])[0].get('code')
        display = resource.get('medicationCodeableConcept', {}).get('text')
        
        dose = None
        if resource.get('dosage'):
            dose = resource['dosage'][0].get('text')
        
        self.cursor.execute('''
            INSERT OR REPLACE INTO medications (id, patient_id, drug_name, code, dose, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            resource.get('id'), patient_id, display, code, dose,
            resource.get('status', 'unknown')
        ))
    
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
        self.cursor.execute('SELECT display, value, unit FROM observations ORDER BY display')
        results = []
        for row in self.cursor.fetchall():
            # Handle None values properly (include 0 values)
            value = row[1] if row[1] is not None else 'N/A'
            results.append({'test': row[0], 'value': value, 'unit': row[2]})
        return results
    
    def query_all_patients(self):
        """Query 4: All patients."""
        self.cursor.execute('SELECT id, name FROM patients')
        return [{'id': row[0], 'name': row[1]} for row in self.cursor.fetchall()]
    
    def query_summary(self):
        """Query 5: Complete summary."""
        return {
            'conditions': self.query_conditions(),
            'medications': self.query_medications(),
            'labs': self.query_labs()  # Uses the fixed query_labs
        }
    
    def close(self):
        """Close database."""
        self.conn.close()

if __name__ == '__main__':
    fhir_file = sys.argv[1] if len(sys.argv) > 1 else 'test_patient_1_fhir.json'
    
    if not Path(fhir_file).exists():
        print(f"ERROR: {fhir_file} not found")
        sys.exit(1)
    
    with open(fhir_file) as f:
        fhir_data = json.load(f)
    
    print(f"\nSTAGE 6: Persistence & Queryability\nProcessing: {fhir_file}\n")
    
    # Store bundle
    store = FHIRStore()
    store.store_bundle(fhir_data['bundle'])
    print("✓ Stored in database")
    
    # Run queries
    queries = {
        'conditions': store.query_conditions(),
        'medications': store.query_medications(),
        'labs': store.query_labs(),
        'patients': store.query_all_patients(),
        'summary': store.query_summary()
    }
    
    store.close()
    
    # Save results
    output = fhir_file.replace('_fhir.json', '_queries.json')
    with open(output, 'w') as f:
        json.dump(queries, f, indent=2)
    
    print(f"✓ Ran 5 demo queries")
    print(f"✓ Saved: {output}\n")