# Shared output contract for examples/heat/

All three sub-systems must conform to this contract so the OMOP step can
read what Amadeus and DeGAUSS produced, and so all three can be diffed in
the verify step.

## Shared input

`data/patients_example1.json` — 3 patients, 8-day window 2022-07-15 → 2022-07-22.
Each patient has `person_id`, `address.{street,city,state,zip}`, and
`geocoded.{lat,lon,precision,score}` already populated.

## DeGAUSS — outputs

The DeGAUSS containers (`ghcr.io/degauss-org/geocoder:3.3.0`,
`ghcr.io/degauss-org/daymet:1.0.0`) are run end-to-end; their joined CSV
outputs are preserved **verbatim** under their native versioned filenames.
EnVar-aliased copies (column `id`→`person_id`, stable sort) sit alongside
them for downstream consumers. Both files' sha256 are recorded in the
sidecar.

### `degauss/outputs/cohort_addresses_geocoder_3.3.0_score_threshold_0.5.csv` (native)
Byte-identical to the geocoder container's joined CSV.
| id | address | start_date | end_date | matched_street | matched_zip | matched_city | matched_state | lat | lon | score | precision | geocode_result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

### `degauss/outputs/cohort_addresses_geocoded.csv` (EnVar-aliased)
Same content, column `id` renamed to `person_id`, sorted by `person_id`.

### `degauss/outputs/cohort_addresses_geocoded_daymet_1.0.0.csv` (native)
Byte-identical to the daymet container's joined CSV. One row per
(person × day) over the study window. `tmax` is in `°C`.
| id | address | matched_street | matched_zip | matched_city | matched_state | score | precision | geocode_result | date | tmax |
|---|---|---|---|---|---|---|---|---|---|---|

### `degauss/outputs/cohort_addresses_geocoded_daymet.csv` (EnVar-aliased)
Slim downstream view: `person_id, date, lat, lon, precision, score, tmax`.

### `degauss/outputs/cohort_addresses_geocoded_daymet.provenance.json`
LinkML-style EnVar sidecar. Must contain at minimum:
- `provenance_id` (ULID-shaped string ending in `-daymet`)
- `variable`: `cf_standard_name`, `cf_cell_methods`, `units_ucum`, `name`
- `spatial`: `native_spatial_resolution_m`, `crs`, `extraction_method`
- `temporal`: `temporal_resolution`, `temporal_aggregation_method`, `day_boundary_convention`
- `source_dataset`: `name`, `short_code`, `doi`, `version`, `license_spdx`
- `exposure_model`: `type` (= `"spatial_interpolation"`), `inputs`
- `linkage`: `strategy`, `geocoding_precision_propagated`
- `tool_run`: `tool_name`, `tool_version`, `run_timestamp_utc`, `input_row_count`, `output_row_count`

## Amadeus — outputs

### `amadeus/outputs/gridmet_tmmx.csv`
| person_id | date | lat | lon | value_kelvin | value_celsius |
|---|---|---|---|---|---|

(GridMET's native unit is Kelvin; expose **both** so the OMOP loader
doesn't have to know.)

### `amadeus/outputs/gridmet_tmmx.provenance.yaml`
Same EnVar sidecar shape as DeGAUSS, but with:
- `provenance_id` ending in `-gridmet`
- `source_dataset.short_code: gridmet`
- `source_dataset.name: gridMET`
- `exposure_model.type: statistical_blend`
- `exposure_model.inputs: ["PRISM monthly normals", "NLDAS-2 sub-daily reanalysis"]`
- `spatial.native_spatial_resolution_m: 4000`

## OMOP/GAIA — outputs

### `omop-gaia/outputs/person.csv`
OMOP CDM v5.4 `person` columns: `person_id`, `gender_concept_id`,
`year_of_birth`, `month_of_birth`, `day_of_birth`, `birth_datetime`,
`race_concept_id`, `ethnicity_concept_id`, `location_id`,
`provider_id`, `care_site_id`, `person_source_value`,
`gender_source_value`, `gender_source_concept_id`,
`race_source_value`, `race_source_concept_id`,
`ethnicity_source_value`, `ethnicity_source_concept_id`.

Fields not derivable from the input get `0` (OMOP convention for unknown
concept) or empty.

### `omop-gaia/outputs/location.csv`
OMOP CDM v5.4 `location` columns: `location_id`, `address_1`, `address_2`,
`city`, `state`, `zip`, `county`, `location_source_value`, `country_concept_id`,
`country_source_value`, `latitude`, `longitude`.

### `omop-gaia/outputs/external_exposure.csv`
OHDSI GIS WG `external_exposure` columns: `person_id`, `location_id`,
`exposure_concept_id`, `exposure_start_date`, `exposure_end_date`,
`value_as_number`, `unit_concept_id`, `exposure_type_concept_id`,
`exposure_source_value`, `exposure_source_concept_id`.

**Two rows per (person × day) × source** — one for Daymet, one for GridMET.
The `exposure_source_value` column carries the upstream sidecar's
`provenance_id` (e.g. `01HFA7K8R3M6XP-daymet`).

### `omop-gaia/outputs/sidecars/`
Both upstream EnVar sidecars copied here, addressable by `provenance_id`.

### `omop-gaia/outputs/MANIFEST.json`
Index: `provenance_id` → relative sidecar path, plus counts per source.

## Units — non-negotiable

- DeGAUSS / Daymet output column `tmax`: **°C** (UCUM `Cel`).
- Amadeus / GridMET native column `value_kelvin`: **K** (UCUM `K`).
- Amadeus / GridMET converted column `value_celsius`: **°C** (UCUM `Cel`).
- OMOP `external_exposure.value_as_number`: **°C** for both source rows.
  Conversion happens in the OMOP loader, *and is recorded* in the
  external-exposure sidecar block.

## Day-boundary convention — declared per source

- Daymet: `local_midnight`.
- GridMET: `local_midnight` (the THREDDS-aggregated daily file is
  midnight-to-midnight local).

Both sidecars **must** declare this slot explicitly (the whole point of EnVar).

## Process hygiene

- Each script in each subfolder is a single Python file with PEP 723
  inline dependencies. No `pip install`. No project-wide pyproject changes.
- Each `run.py` accepts `ENVAR_OFFLINE=1` to use a bundled fixture
  (so the example survives the network being down).
- All outputs are deterministic given the inputs and the data source state.
- `provenance_id` includes a timestamp suffix; the rest of the ID is
  derived from a hash of inputs + tool name + version so re-runs are
  comparable.
