# Project 3 Audit: Issues Found & Fixed

## Summary
- **Found:** 11 bugs
- **Fixed:** 6 critical
- **Remaining:** 5 known (documented)

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

## 5 Remaining Issues

1. **Extraction is not reproducible** (accepted limitation)
   - Stages 1 and 3 call the LLM; re-running the same PDF gives slightly
     different results (fact counts have ranged 187-220 across runs)
   - **`temperature=0` is not available.** Sampling parameters
     (`temperature`/`top_p`/`top_k`) were removed on `claude-sonnet-5`; the API
     returns 400 and `anthropic` 1.0.0 does not expose the parameter.
     Still accepted on older models (Sonnet 4.6, Haiku 4.5)
   - Options if this matters later: cache responses keyed on
     (model + prompt) for byte-identical replay, or move to a model that
     still accepts `temperature`
   - Consequence: every metric in this file is one run's numbers, not a fixed value

2. **40 unmapped facts** (13 conditions, 6 meds, 21 labs)
   - Reported by name, not hidden
   - Could preserve as uncoded FHIR (valid)

3. **RxNorm codes unverified**
   - Marked as unverified in code
   - Need real RxNorm lookup

4. **Confidence hardcoded 0.85** (low priority)

5. **Patient resource stub** (low priority)

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