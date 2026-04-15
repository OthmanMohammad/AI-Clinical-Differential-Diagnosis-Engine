# Evaluation Cases

This directory contains curated clinical test cases used by
`python -m eval.run_eval` to measure the Graph RAG diagnosis pipeline.

## Schema

Each file is named `case_NN_short_slug.json` and follows this shape:

```json
{
  "id": "case_01",
  "name": "Classic T2DM with hyperglycemia",
  "split": "train",                      // "train" or "holdout"
  "patient": { /* PatientIntake payload */ },
  "expected_diagnoses": ["Type 2 Diabetes Mellitus"],
  "icd_codes": ["E11"],                  // informational only
  "mapping_confidence": "high",          // high | medium | low
  "clinically_validated": false,         // human-curated, NOT MD-reviewed
  "source": "Harrison's Principles of Internal Medicine (textbook presentation)",
  "notes": "..."
}
```

Matching against `expected_diagnoses` in `eval/metrics.py` is a
case-insensitive substring match in either direction, so
"Diabetes Mellitus Type 2" and "Type 2 Diabetes Mellitus" both match.

## Splits

- **train (15 cases)** — used for eyeballing retrieval behaviour and
  iterating on prompts/rules. Over-tuning against these is OK.
- **holdout (5 cases)** — must NOT be touched during tuning. Report
  MRR on these separately as the honest generalization signal.

## clinically_validated

Every case in this directory is flagged `clinically_validated: false`.
These are hand-written textbook presentations, not real clinical data,
and they have not been reviewed by a physician. They exist to catch
regressions in the retrieval pipeline, not to demonstrate clinical
accuracy.

Do not use these cases — or the system in general — for any real
patient care decision.
