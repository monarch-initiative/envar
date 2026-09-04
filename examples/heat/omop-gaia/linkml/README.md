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
| `prepare_locations.py`                    | Builds the OMOP `Location` table + `person_id → location_id` lookup (deduped by address) |
| `daymet_to_external_exposure.transform.yaml` | Trans-spec: `DaymetValueRow` → `ExternalExposure`, joined to `PersonLocation` for `location_id` |

## Unmapped concept ids

Vocabulary mapping is still open, so `exposure_concept_id`,
`exposure_type_concept_id`, `exposure_relationship_concept_id`, and
`unit_concept_id` are emitted as `0` — OMOP's standard "unmapped concept"
sentinel — rather than left null. The target schema requires all but
`unit_concept_id`, and `0` states the gap in OMOP's own vocabulary instead of
leaving a hole. This replaces the earlier local schema patch, which is gone: the
`identifier: true` over-marking it worked around was fixed upstream
(`linkml-ohdsi-gis-extension-envar` #2), so output now validates against the
published schema unmodified.

## Run

```bash
cd examples/heat/omop-gaia/linkml
TARGET=<path>/linkml_ohdsi_gis_extension_envar.yaml   # from #27's repo, unmodified
LM=linkml-map            # released 0.5.3 is sufficient

# 1. denormalize the sidecar onto the value rows, and build the Location table + lookup
uv run --script prepare_omop.py \
  ../../degauss/outputs/cohort_addresses_geocoded_daymet.csv \
  ../../degauss/outputs/envar/cohort_addresses_geocoded_daymet.provenance.json \
  --out inputs/daymet_values_prepared.csv
uv run --script prepare_locations.py ../../degauss/outputs/cohort_addresses_geocoded.csv

# 2. transform. NOTE: map-data needs a DIRECTORY with a <SourceType>.csv file —
#    a single CSV path silently yields 0 rows. Both the primary rows and the
#    PersonLocation join lookup go in the directory.
mkdir -p indir
cp inputs/daymet_values_prepared.csv indir/DaymetValueRow.csv
cp inputs/PersonLocation.csv indir/PersonLocation.csv
$LM map-data -T daymet_to_external_exposure.transform.yaml \
  -s daymet_values.source.yaml --target-schema "$TARGET" \
  -f csv -o out/external_exposure.csv indir/

# 3. validate
linkml-validate -s "$TARGET" -C ExternalExposure out/external_exposure.csv
```

## Status (real data, runnable)

Produces 24 real `ExternalExposure` rows (3 persons × 8 days) from the real
Daymet fixture, each carrying a `location_id` resolved via a person → Location
join, plus a real OMOP `Location` table (3 deduped addresses). **Validates
against the published target schema, unpatched.** QC passes: row counts,
`value_as_number` == source Tmax, provenance linkage on every row, unique
surrogate keys, `location_id` FK integrity + join correctness, start == end.
Headline check — person 91204 on 2022-07-19 = 43.93 °C.

### Known gaps (follow-on)
- **Vocabulary mapping** for the concept-id slots — emitted as `0` (unmapped)
  pending mapping; the sidecar's `target_concept_id` is itself a declared gap
  (`concept_status: gap`).
- **Surrogate `external_exposure_id`** is a deterministic demo value; real
  assignment is a loader concern.
- **Sidecar shape:** the emitted sidecar is still the CONTRACT.md shape, not
  Nico's `EnvironmentalExposureRecord` — reconciliation pending.
- **`Location` / `Person`:** `prepare_locations.py` hand-rolls the Location
  table; the target schema now defines `Location` and `Person` classes, so this
  should derive from the model rather than alongside it.
- **Runner:** driven by bare `linkml-map` here. dm-bip's `map-data` target is a
  generic wrapper around the same call, so wiring this through dm-bip is a
  follow-on rather than a rewrite.
