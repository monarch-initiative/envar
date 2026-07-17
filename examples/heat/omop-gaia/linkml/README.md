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
| `patch_target_schema.py`                  | Regenerates the **local patch** of the #27 target schema (see below) |
| `vendor/…local-patch.yaml`                | Generated, temporary patched target schema — do not hand-edit |

## Local patch of the target schema (temporary)

The #27 `ExternalExposure` marks ~8 FK/concept-id slots as `identifier: true`,
which makes them required — contrary to OMOP, where concept_id columns are
nullable (0 = unmapped) and `location_id` is a nullable FK. `patch_target_schema.py`
vendors a copy with those relaxed so output can validate. This is a stopgap
pending an upstream fix; the vendored file is regenerated, never hand-edited:

```bash
uv run --script patch_target_schema.py <path>/linkml_ohdsi_gis_extension_envar.yaml
```

## Run

```bash
cd examples/heat/omop-gaia/linkml
GIS=<path>/linkml_ohdsi_gis_extension_envar.yaml   # from #27's repo
LM=<linkml-map built from 8267d3a>

# 0. vendor the local patch of the target schema (see "Local patch" below)
uv run --script patch_target_schema.py "$GIS"
TARGET=vendor/linkml_ohdsi_gis_extension_envar.local-patch.yaml

# 1. denormalize the sidecar onto the value rows
uv run --script prepare_omop.py \
  ../../degauss/outputs/cohort_addresses_geocoded_daymet.csv \
  ../../degauss/outputs/envar/cohort_addresses_geocoded_daymet.provenance.json \
  --out inputs/daymet_values_prepared.csv

# 2. transform. NOTE: map-data needs a DIRECTORY with a <SourceType>.csv file —
#    a single CSV path silently yields 0 rows.
mkdir -p indir && cp inputs/daymet_values_prepared.csv indir/DaymetValueRow.csv
$LM map-data -T daymet_to_external_exposure.transform.yaml \
  -s daymet_values.source.yaml --target-schema "$TARGET" \
  -f csv -o out/external_exposure.csv indir/

# 3. validate
linkml-validate -s "$TARGET" -C ExternalExposure out/external_exposure.csv
```

## Status — increment 1 (real data, runnable)

Produces 24 real `ExternalExposure` rows (3 persons × 8 days) from the real
Daymet fixture, and **validates** against the (locally patched) target schema.
QC passes: row counts, `value_as_number` == source Tmax, provenance linkage on
every row, unique surrogate keys. Headline check — person 91204 on 2022-07-19 =
43.93 °C.

### Known gaps (follow-on)
- **person → Location join** for `location_id` — currently a null placeholder;
  the join (linkml-map `joins`) is increment 2.
- **Vocabulary mapping** for `exposure_concept_id`, `unit_concept_id`,
  `exposure_type_concept_id` — null pending mapping; the sidecar's
  `target_concept_id` is itself a declared gap (`concept_status: gap`).
- **Surrogate `external_exposure_id`** is a deterministic demo value; real
  assignment is a loader concern.
- **Sidecar shape:** the emitted sidecar is still the CONTRACT.md shape, not
  Nico's `EnvironmentalExposureRecord` — reconciliation pending.
- **Target schema (#27):** relaxed via a temporary local patch (see above);
  the `identifier: true` over-marking needs an upstream fix.
