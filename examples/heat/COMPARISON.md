# What each heat-scenario pipeline carries forward today

Same cohort, same 8-day window, same coordinates. This table compares
**only what each pipeline natively emits today** — the CSVs the
DeGAUSS containers write, the THREDDS/R-attribute files the Amadeus
flow writes, and the gaiaCatalog + gaia-db + OMOP CDM tables the
OHDSI GIS stack writes. The EnVar `*.provenance.json/.yaml` sidecars
and the `envar/MANIFEST.json` file are **not** counted here — those are
the layer EnVar is proposing to add on top, and are tracked separately
at the bottom.

Legend: ✅ carried, on a stable column / named slot / standard file in
the pipeline's own output. ➖ present but only as a free-text or embedded
sub-field (recoverable, not first-class). ❌ not carried.

The "where" reference under each cell is the actual file or column you
can grep for in `examples/heat/`.

---

## A. Cohort identity and demographics

| Feature | DeGAUSS | Amadeus | OMOP / GAIA |
|---|---|---|---|
| Person identifier | ✅ `id` on every CSV row | ✅ `person_loc_id` / `person_id` on every row | ✅ `person.person_id`, `location.location_id`, `external_exposure.person_id` |
| Sex / gender | ❌ | ❌ | ✅ `person.gender_concept_id` (8532 F / 8507 M) + `gender_source_value` |
| Year of birth | ❌ | ❌ | ✅ `person.year_of_birth` |
| Race / ethnicity slots | ❌ | ❌ | ✅ present as empty slots (`race_concept_id`, `ethnicity_concept_id`, source values) — at least the schema is there |
| Observation period (per-person) | ❌ | ❌ | ❌ no `observation_period.csv` is produced by this pipeline natively; the value is used only as an internal filter |

## B. Address and geocoding quality

| Feature | DeGAUSS | Amadeus | OMOP / GAIA |
|---|---|---|---|
| Full street address | ✅ `address`, `matched_street`, `matched_zip`, `matched_city`, `matched_state` on every row of the geocoder + daymet CSVs | ❌ collapsed to lat/lon at the THREDDS request | ✅ `location.address_1` / `city` / `state` / `zip` + concat in `location_source_value`; same address columns on `gaia_db/location.csv` |
| Geocoder match score | ✅ `score` column | ❌ | ❌ no column for this on `location.csv` or `external_exposure.csv` |
| Geocoding precision (`range`/`street`/etc.) | ✅ `precision` column | ❌ | ❌ |
| Geocode-result flag (`success`/etc.) | ✅ `geocode_result` column | ❌ | ❌ |
| Country | ❌ | ❌ | ✅ `location.country_source_value` |

## C. Coordinates and CRS

| Feature | DeGAUSS | Amadeus | OMOP / GAIA |
|---|---|---|---|
| Latitude / longitude | ✅ `lat`, `lon` columns | ✅ `lat`, `lon` columns | ✅ `location.latitude` / `longitude` + PostGIS `geom` on `gaia_db/location.csv` |
| CRS / EPSG of the cohort coordinates | ❌ implicit WGS84 | ❌ implicit WGS84 | ✅ `gaia_db/location.geom` is in EPSG:4326 (column type and SRID enforce it); `gaia_db/data_source.srid` = 4326 |
| CRS of the source raster | ❌ | ✅ `thredds_dataset.xml` declares `coordinate_system = "WGS84,EPSG:4326"` on the grid | ✅ `gaia_catalog/meta_etl_*.json → epsg / local_epsg`; gaia-db `data_source.srid`; JSON-LD `additionalProperty` for SRS |

## D. Exposure values

| Feature | DeGAUSS | Amadeus | OMOP / GAIA |
|---|---|---|---|
| One row per (person × day) | ✅ 24 rows in `cohort_addresses_geocoded_daymet_1.0.0.csv` | ✅ 24 rows in `gridmet_tmmx.csv` | ❌ The native gaia output `external_exposure_gaia_native.csv` collapses every row to the variable's window-wide `attr_start_date / attr_end_date`. Per-day external_exposure does **not** come out of `working.spatial_join_exposure` today |
| Value in native source units | ❌ Daymet container does the K→°C conversion itself, so the native CSV is already °C | ✅ `value_kelvin` column on `gridmet_tmmx.csv` | ❌ only the OMOP-side unit lands in `value_as_number`; the upstream native unit is not on the row |
| Value in human-friendly °C | ✅ `tmax` column | ✅ `value_celsius` column (Amadeus's covariate calc converts) | ✅ `external_exposure.value_as_number` (Cel) |
| Window-wide vs per-day dates | per-day | per-day | window-wide only (this is the documented gaia limitation in `outputs/NATIVE_METADATA.md`) |
| Exposure concept / variable identity | ❌ implicit in the column name `tmax` | ❌ implicit in the column name `tmmx` | ✅ `external_exposure.exposure_concept_id` (placeholder concept) + `exposure_type_concept_id` (32885) — the slot exists even if no real OMOP concept is yet minted for daily-max-air-temperature |

## E. Units

| Feature | DeGAUSS | Amadeus | OMOP / GAIA |
|---|---|---|---|
| Native unit declared by a machine-readable slot | ❌ The CSV column is named `tmax` with no unit annotation; °C is by container convention | ✅ `thredds_dataset.xml` declares `units = "K"` on the grid; `gridmet_tmmx.cf_metadata.json` mirrors it. THREDDS also declares `scale_factor = 0.1`, `add_offset = 220.0` so the packed int16 unpacks to true Kelvin | ✅ `gaia_db/variable_source.unit_code` (UCUM `CEL`) + `unit_text` (`deg C`); JSON-LD `variableMeasured.unitCode / unitText`; `external_exposure.unit_concept_id` (8653) |
| K→°C conversion math recorded | n/a | ❌ Both columns ship side by side but the math `K − 273.15` is not written down by Amadeus | ❌ not in any gaia-native column. Gaia stores °C as if it were always °C; the unit_concept_id alone says nothing about provenance of the conversion |
| OMOP unit concept | n/a | n/a | ✅ `unit_concept_id = 8653` |

## F. Variable identity (CF / standard vocabulary)

| Feature | DeGAUSS | Amadeus | OMOP / GAIA |
|---|---|---|---|
| Variable short name | ✅ column header `tmax` | ✅ column header `value_kelvin`/`value_celsius`; THREDDS xml has `long_name = "tmmx"`, `standard_name = "tmmx"` (note: gridMET uses the dataset's own short code as `standard_name`, not the CF term) | ✅ `gaia_db/variable_source.variable_name` |
| Variable description / long name | ❌ | ✅ `thredds_dataset.xml → description = "Daily Maximum Temperature (2m)"`; grid is named `daily_maximum_temperature` | ✅ `gaia_db/variable_source.variable_description`; JSON-LD `variableMeasured.description` |
| CF standard name (e.g. `air_temperature`) | ❌ | ➖ THREDDS xml has `standard_name="tmmx"` which is **not** a real CF term — gridMET overloads the slot. So a CF lookup against the file would fail | ✅ `gaia_db/variable_source.property_id` and JSON-LD `variableMeasured.propertyID` point at `http://vocab.nerc.ac.uk/standard_name/air_temperature/` (the NERC vocab mirror of CF) — this is **only** present because gaiaCatalog has a `propertyID` slot, and someone hand-authored the right value into the JSON-LD |
| CF cell methods (e.g. `time: maximum`) | ❌ | ❌ implicit in the variable name only (`daily_maximum_temperature`) | ❌ no slot in gaiaCatalog or gaia-db |
| Variable valid range (min/max physical bounds) | ❌ | ❌ | ✅ `gaia_db/variable_source.min_value/max_value` (−50 / 60); also in JSON-LD `variableMeasured` |
| Variable validity dates | ❌ | ✅ `thredds_dataset.xml → TimeSpan` (full dataset span 1979–2026) | ✅ `gaia_db/variable_source.start_date/end_date` (narrowed to the study window per the JSON-LD entry) |
| Fill value / missing-value sentinel | ❌ | ✅ `thredds_dataset.xml → _FillValue / missing_value = 32767` | ➖ `gaia_catalog/meta_etl_*.json → nodata = ["float4", "-9999"]` for daymet; nothing for gridmet because the value was already unpacked upstream |

## G. Spatial metadata (resolution, extraction method, coverage)

| Feature | DeGAUSS | Amadeus | OMOP / GAIA |
|---|---|---|---|
| Native grid resolution | ❌ not in any output file; you have to know "Daymet = 1 km" out of band | ➖ derivable from `thredds_dataset.xml → axis lat/lon increment` (0.041666… deg ≈ 4 km), but not written as a resolution number | ❌ gaiaCatalog has no first-class slot for this; only present in our JSON-LD via the `envar:native_spatial_resolution_m` PropertyValue (EnVar extension, not native) |
| Extraction method (point-in-cell, nearest-cell, IDW, etc.) | ❌ | ❌ | ❌ no slot |
| Source-dataset spatial coverage | ❌ | ✅ `thredds_dataset.xml → projectionBox` + `LatLonBox` give the CONUS bbox | ✅ `gaia_catalog/meta_dcat_*.json → spatialCoverage`; `gaia_db/data_source.spatial_coverage`; `meta_etl_*.json → extent` (POLYGON WKT) |
| Geometry type of the dataset | ❌ | ❌ | ✅ `gaia_db/data_source.geom_type` (`point`); `meta_etl_*.json → structure / geometry` (`raster`) |

## H. Temporal metadata (resolution, aggregation, day boundary)

| Feature | DeGAUSS | Amadeus | OMOP / GAIA |
|---|---|---|---|
| Temporal resolution as a discrete field | ❌ implicit (one row per day) | ❌ implicit (one row per day); `thredds_dataset.xml → day` axis declares `increment = 1.0` over `"days since 1900-01-01"`, so derivable | ❌ no first-class `temporal_resolution` slot in gaiaCatalog or gaia-db |
| Temporal aggregation method (`daily_maximum` etc.) | ❌ | ➖ encoded only in the variable's long_name (`daily_maximum_temperature`) | ❌ no slot |
| Day-boundary convention (`local_midnight` / `UTC_midnight` / 06–06) | ❌ | ❌ NetCDF time axis is `"days since 1900-01-01"` with no `calendar` clarification on day-edge — pure ambiguity | ❌ no slot anywhere |
| Dataset time-span | ❌ | ✅ `thredds_dataset.xml → TimeSpan` (1979 → present) | ✅ `gaia_catalog/meta_dcat_*.json → dct:temporal`; `gaia_db/variable_source.start_date/end_date` |
| Time-origin / calendar of the source data | ❌ | ✅ `thredds_dataset.xml → day` axis (`days since 1900-01-01`, `calendar = gregorian`) | ❌ no slot in gaia |

## I. Source-dataset identity, licensing, lineage

| Feature | DeGAUSS | Amadeus | OMOP / GAIA |
|---|---|---|---|
| Dataset name | ❌ | ❌ (not in any of `thredds_dataset.xml` / `cf_metadata.json` — has to be inferred from the THREDDS URL path) | ✅ `gaia_db/data_source.dataset_name` and `meta_dcat_*.json → dct:title` |
| Dataset version | ➖ tool version is in the filename (`daymet_1.0.0`) but that's the **container** version, not the upstream dataset version | ❌ | ✅ `gaia_db/data_source.dataset_version` (`V4 R1`, `current`) |
| DOI | ❌ | ❌ | ✅ `meta_dcat_*.json → dct:identifier` (daymet has a DOI; gridmet has only `url` in DCAT — not all entries carry one) |
| License | ❌ | ❌ | ✅ `gaia_db/data_source.license` + `meta_dcat_*.json → dct:license` (note: gaia stores it as a string like `public-domain-us-gov` or `CC0-1.0` — no SPDX normalisation) |
| Publisher / creator / provider | ❌ | ❌ | ✅ `gaia_db/data_source.creator/provider`; `meta_dcat_*.json → dct:publisher` |
| Date published / modified | ❌ | ❌ | ✅ `gaia_db/data_source.date_published/date_modified` |
| Keywords | ❌ | ❌ | ✅ `gaia_db/data_source.keywords`; `meta_dcat_*.json → dcat:keyword` |
| Source landing-page URL | ❌ | ➖ THREDDS NCSS URL is in `thredds_dataset.xml @location` but it's the data endpoint, not the human landing page | ✅ `gaia_db/data_source.url`; `meta_etl_*.json → source`; JSON-LD `url` |

## J. Exposure model / linkage methodology

| Feature | DeGAUSS | Amadeus | OMOP / GAIA |
|---|---|---|---|
| Exposure-model type as a structured slot (e.g. `spatial_interpolation` vs `statistical_blend`) | ❌ | ❌ | ❌ no first-class gaiaCatalog slot — only present in our JSON-LD via `envar:exposure_model_type` PropertyValue (EnVar extension) |
| Free-text method description | ❌ | ❌ | ✅ `gaia_db/data_source.measurement_technique` + `meta_dcat_*.json → measurementTechnique` (free-text only, e.g. "spatial interpolation from GHCN-Daily station observations") |
| Model inputs (e.g. "GHCN-Daily", "PRISM monthly normals", "NLDAS-2") | ❌ | ❌ | ❌ no slot anywhere |
| Linkage strategy (how patient point ↔ raster cell) | ❌ | ❌ | ➖ only as the SQL-join semantics of `working.spatial_join_exposure` (`st_within` with a hard-coded buffer) — not exposed as a documented column |
| Geocoding-precision propagation | ❌ (precision is on the row, but no statement about what was done with it downstream) | ❌ | ❌ |

## K. Tool / run provenance

| Feature | DeGAUSS | Amadeus | OMOP / GAIA |
|---|---|---|---|
| Tool name | ➖ embedded in filename (`...geocoder_3.3.0...csv`, `...daymet_1.0.0.csv`) | ❌ | ❌ |
| Tool version | ✅ container image tag in the filename and in `ghcr.io/degauss-org/...` reference | ❌ Amadeus's R object would carry the package version in `attributes()`, but no native file records this for us | ❌ no gaia table records the gaia-db image version |
| Run timestamp | ❌ (only OS file mtime) | ➖ HTTP `Date` header in `thredds_response_headers.json` is the only timestamp | ✅ `gaia_db/data_source.created_at/updated_at`; `gaia_db/location.created_at` (each row's load time) |
| Input / output row counts | ❌ | ❌ | ❌ no native gaia output records this; you'd `wc -l` |
| Input-file checksum / sha256 | ❌ | ❌ | ❌ |
| Container / image digest | ❌ | ❌ | ❌ |
| SQL functions actually invoked | n/a | n/a | ➖ `gaia_db/spatial_join_log.txt` captures the psql NOTICE lines from the join, but it's a log not a structured record |

---

## Native sidecar / metadata files produced today

| Pipeline | Native metadata files |
|---|---|
| DeGAUSS | none. Only the two CSVs, with the container version baked into the filename |
| Amadeus | `gridmet_tmmx.cf_metadata.json` (CF Conventions metadata pulled from THREDDS `dataset.xml`), `thredds_response_headers.json`, the raw `thredds_dataset.xml` |
| OMOP / GAIA | gaiaCatalog 3-file pattern per dataset: `meta_etl_*.json` (ETL recipe), `meta_dcat_*.json` (DCAT discovery), `meta_json-ld_*.json` (Schema.org `Dataset`). After ingestion, the same content is queryable in `gaia_db/data_source.csv` and `gaia_db/variable_source.csv` |

## What no pipeline carries today (the gap)

These features appear in the EnVar sidecar template but are **not** produced by any pipeline's native output:

- A structured day-boundary convention slot (`local_midnight` etc.)
- A structured temporal-aggregation slot (`daily_maximum`)
- A structured exposure-model type (`spatial_interpolation` vs `statistical_blend`)
- A structured list of exposure-model inputs (`GHCN-Daily`, `PRISM monthly normals`, …)
- A structured extraction-method slot (`single_pixel` vs `nearest_grid_cell` vs IDW)
- A structured linkage-strategy slot (`point-in-cell`, `nearest_grid_cell`, …)
- A propagation flag for geocoding precision
- An SPDX-normalised license string (gaia stores a freeform license name)
- A first-class native-spatial-resolution-in-metres slot
- A first-class unit-conversion record (`from_ucum`, `to_ucum`, `formula`)
- A first-class container-image / SQL-patch / file-checksum block
- Per-day `external_exposure` rows on the OMOP side (gaia today collapses to the variable's window)

## One-paragraph summary

- **DeGAUSS** carries the richest *cohort-side* signal — full street
  address, geocoder score, geocoder precision, geocode-result flag,
  per-day rows — and bakes the **container** version into the
  filename. That's the limit of what it tells you. No unit annotation,
  no DOI, no license, no day-boundary, no CF standard name, no
  methodological metadata.
- **Amadeus** carries the per-day data plus a useful CF-Conventions
  blob (`cf_metadata.json` from THREDDS): native units (K),
  scale_factor / add_offset, fill value, CRS, time-origin, dataset
  bbox, time span. It carries **no** dataset-identity metadata (no
  name, no DOI, no license, no publisher), and the THREDDS file's
  `standard_name` slot is overloaded with the gridMET shortcode rather
  than a real CF term.
- **OMOP / GAIA** is the only one that natively carries dataset-level
  discovery metadata (DCAT title / description / publisher /
  identifier / temporal coverage / keywords), the variable's
  controlled-vocabulary identifier (NERC propertyID), license,
  version, date-published, full street address columns, and OMOP
  demographic columns. Its weak spots are: (1) it natively collapses
  per-day exposure dates to the variable's window-wide validity range,
  and (2) it has no slot for the EnVar-style methodological fields
  (day boundary, aggregation method, exposure-model type, model
  inputs, extraction method, linkage strategy, unit-conversion record,
  geocoding-precision propagation) — those gaps are why the EnVar
  layer exists at all.
