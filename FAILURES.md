# Project 3 Audit: Issues Found & Fixed

## Summary
- **Found:** 10 bugs
- **Fixed:** 6 critical
- **Remaining:** 4 known (documented)

---

## 6 Critical Fixes

| Fix | Problem | Solution | Result |
|---|---|---|---|
| #1 | 43% data loss (truncation) | Sentence chunking | 220 facts, 0% loss |
| #2 | All values NULL | Parse lab values | 102/102 observations with values |
| #3 | Fake FHIR validation | Real R4B validator | Real errors caught (77) |
| #4 | Database accumulation | Idempotent loading | 1 patient, stable |
| #5 | Wrong codes (substring) | Whole-word matching | EMG: correct codes |
| #6 | All dates = run time | Extract real dates | 10 distinct dates |

---

## 4 Remaining Issues

1. **40 unmapped facts** (13 conditions, 6 meds, 21 labs)
   - Reported by name, not hidden
   - Could preserve as uncoded FHIR (valid)

2. **RxNorm codes unverified**
   - Marked as unverified in code
   - Need real RxNorm lookup

3. **Confidence hardcoded 0.85** (low priority)

4. **Patient resource stub** (low priority)

---

## Metrics

| Metric | Before | After |
|---|---|---|
| Data loss | 43% | 0% |
| Facts | 122 | 220 |
| Observations with values | 0/41 | 102/102 |
| FHIR validation | Fake | Real R4B |
| Terminology mapped | 92%* | 81%** |

*Inflated (included wrong matches)
**Honest (unmapped listed)

---

Full details: See code comments and git history.