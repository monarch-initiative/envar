# Daymet → OMOP ExternalExposure (linkml-map) — D6.1 back-half

The real EnVar ETL step (EnVar-Tracker #42): a declarative linkml-map trans-spec
that turns the per-(person × day) Daymet value table into OHDSI GIS
`ExternalExposure` rows, replacing the imperative logic in `../run.py`.

Unlike the throwaway front-half spike (patients JSON → tool input), this
consumes the **published** target schema
(`monarch-initiative/linkml-ohdsi-gis-extension-envar`, #27) and links every row
back to its EnVar sidecar — so it's the durable seed of D6.1, not scaffolding.

## Files

| File | Role |
|---|---|
| `daymet_values.source.yaml`               | Source schema for the Daymet value table (stands in for schema-automator inference) |
| `prepare_omop.py`                         | Denormalizes the EnVar sidecar's metadata onto each value row |
| `daymet_to_external_exposure.transform.yaml` | Trans-spec: `DaymetValueRow` → `ExternalExposure` |

## Run

```bash
cd examples/heat/omop-gaia/linkml
GIS=<path>/linkml_ohdsi_gis_extension_envar.yaml   # from #27's repo
LM=<linkml-map built from 8267d3a>

uv run --script prepare_omop.py \
  ../../degauss/outputs/cohort_addresses_geocoded_daymet.csv \
  ../../degauss/outputs/envar/cohort_addresses_geocoded_daymet.provenance.json \
  --out inputs/daymet_values_prepared.csv

# NOTE: map-data needs a DIRECTORY with a <SourceType>.csv file — a single CSV
# path silently yields 0 rows.
mkdir -p indir && cp inputs/daymet_values_prepared.csv indir/DaymetValueRow.csv
$LM map-data -T daymet_to_external_exposure.transform.yaml \
  -s daymet_values.source.yaml --target-schema "$GIS" \
  -f csv -o out/external_exposure.csv indir/
```

## Status — increment 1 (real data, runnable)

Produces 24 real `ExternalExposure` rows (3 persons × 8 days) from the real
Daymet fixture. QC passes: row counts, `value_as_number` == source Tmax,
provenance linkage on every row, unique surrogate keys. Headline check —
person 91204 on 2022-07-19 = 43.93 °C.

### Known gaps (follow-on)
- **person → Location join** for `location_id` (linkml-map `joins`, increment 2).
- **Vocabulary mapping** for `exposure_concept_id`, `unit_concept_id`,
  `exposure_type_concept_id`; the sidecar's `target_concept_id` is a declared
  gap (`concept_status: gap`).
- **Surrogate `external_exposure_id`** is a deterministic demo value; real
  assignment is a loader concern.
- **Sidecar shape:** the emitted sidecar is still the CONTRACT.md shape, not
  Nico's `EnvironmentalExposureRecord` — reconciliation pending.
- **Target schema (#27):** `ExternalExposure` marks ~11 concept_id slots as
  `identifier: true` (→ all required), which rejects the OMOP "0 = unmapped"
  convention. Needs revisiting upstream before output can fully validate.
