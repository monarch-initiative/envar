# linkml-map transforms (dm-bip engine) — proof of concept

This directory reproduces the hand-written `translate.py` steps of the heat
example as **declarative [linkml-map](https://github.com/linkml/linkml-map)
transformation specs**, driven by the [dm-bip](https://github.com/linkml/dm-bip)
engine (`compose_specs` → `linkml-map map-data`). It's a spike: it shows the
`degauss/` and `amadeus/` input transforms can be expressed as trans-specs +
schemas instead of imperative Python.

## Files

| File | Role |
|---|---|
| `patients.source.yaml`       | Source schema for `../data/patients_example1.json` |
| `amadeus_input.target.yaml`  | Target schema — Amadeus point-location table |
| `degauss_input.target.yaml`  | Target schema — DeGAUSS geocoder input table |
| `amadeus.transform.yaml`     | Trans-spec: patients → Amadeus rows |
| `degauss.transform.yaml`     | Trans-spec: patients → DeGAUSS rows |
| `prepare.py`                 | Generic prep: denormalize `study_window` onto each patient |

## Why `prepare.py`

linkml-map evaluates each derivation against a single source object, so a
per-`Patient` derivation can't reach the parent `PatientCohort.study_window`.
`prepare.py` copies `study_window.start/end` down onto every patient as
`window_start`/`window_end`, so the per-row `start_date`/`end_date` become plain
`populated_from`. This denormalization is the kind of step dm-bip's
`cleaners`/`prepare_input` layer owns.

## linkml-map version

The nested, non-deprecated `class_derivations` form used here requires an
**unreleased** linkml-map (`git+https://github.com/linkml/linkml-map@8267d3a`,
PR #235 head) — the released `0.5.2` only supports the deprecated
`object_derivations`. dm-bip already pins this build on a feature branch.

## Run

```bash
cd examples/heat/linkml
LM=<path to linkml-map built from 8267d3a>

# 1. denormalize the study window onto each patient
uv run --script prepare.py ../data/patients_example1.json --out inputs/patients_prepared.json

# 2. transform
$LM map-data -T amadeus.transform.yaml -s patients.source.yaml \
    --target-schema amadeus_input.target.yaml --source-type PatientCohort \
    -f json inputs/patients_prepared.json

$LM map-data -T degauss.transform.yaml -s patients.source.yaml \
    --target-schema degauss_input.target.yaml --source-type PatientCohort \
    -f json inputs/patients_prepared.json
```

Both outputs match the corresponding `../{amadeus,degauss}/translate.py` CSVs
field-for-field. `inputs/` and `out/` are generated and gitignored.
