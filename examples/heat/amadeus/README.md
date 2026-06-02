# amadeus — isolated GridMET (METDATA) Tmmx heat pipeline

The second leg of the heat scenario. Takes the canonical patient
cohort (`data/patients_example1.json`) and extracts daily maximum
2-m air temperature (`tmmx`) at each patient's coordinate from the
University of Idaho's gridMET (a.k.a. METDATA) dataset. The output
is one row per (person × day) in °C and K, paired with an EnVar
provenance sidecar.

Isolation is deliberate. `amadeus/run.py` reads nothing from
`degauss/outputs/` or `omop-gaia/outputs/` — its sole input is
`patients_example1.json` (plus its own bundled fixtures for offline
mode). The three heat-scenario pipelines can therefore be compared
as independent runs (same input, three implementations, three
provenance trails).

## What "real Amadeus" means here

[`NIEHS/amadeus`](https://niehs.github.io/amadeus/) is the R package
that powers NIEHS CHORDS's gridded-environmental-data extraction:
`amadeus::download_data("gridmet", variables = "tmmx")` fetches the
GridMET NetCDFs, then `amadeus::calculate_covariates("gridmet", ...)`
extracts per-point values via `terra::extract`. The same data also
lives behind a [THREDDS NCSS endpoint at Northwest Knowledge
Network](http://thredds.northwestknowledge.net:8080/thredds/reacch_climate_MET_aggregated_catalog.html).

This folder supports **both paths**, in priority order:

1. **Real R amadeus.** If you build the bundled `envar-amadeus:4.4`
   image (`docker build --platform linux/amd64 -t envar-amadeus:4.4 .`),
   `run.py` invokes it via `Rscript amadeus_extract.R`. That script
   calls the real `amadeus::download_data()` to fetch GridMET NetCDFs,
   then uses the real `terra::rast` + `terra::extract` for per-point
   extraction.
2. **Python THREDDS-equivalent path.** If the R image isn't present,
   `run.py` falls back to calling the same Northwest Knowledge Network
   THREDDS NCSS endpoint the R chain ultimately reaches. Same GridMET
   V4 data, same patient coordinates, same per-day values — different
   client implementation.

The execution mode actually used is **recorded in the sidecar** as
`tool_run.execution_mode` (`real_amadeus_download_real_terra_extract`
or `python_thredds_equivalent`), so downstream consumers can tell
the two apart.

## Layout

```text
amadeus/
├── README.md                  this file
├── translate.py               patients_example1.json → patient_locations.csv
├── run.py                     extract GridMET tmmx, emit EnVar sidecar
├── Dockerfile                 build envar-amadeus:4.4 (rocker/geospatial:4.4 + amadeus)
├── amadeus_extract.R          REAL amadeus + terra extraction script
├── inputs/
│   └── patient_locations.csv  produced by translate.py
├── fixtures/                  bundled THREDDS responses for offline runs
│   ├── gridmet_tmmx_<person_id>_<start>_<end>.csv    raw NCSS CSV per patient
│   ├── thredds_dataset.xml                            CF metadata blob
│   ├── thredds_dataset_headers.json                   dataset.xml HTTP response headers
│   └── thredds_ncss_response_headers.json             per-NCSS-call response headers
└── outputs/                   everything the run produces (see below)
```

## What's in `outputs/` after a run

```text
outputs/
├── gridmet_tmmx.csv                 per-(person × day): person_id, date, lat, lon, value_kelvin, value_celsius
├── gridmet_tmmx.attributes.json     R `attr()`-style metadata block (call, package_version, datetime, row.names …)
├── gridmet_tmmx.cf_metadata.json    CF Conventions metadata from THREDDS dataset.xml, normalised to JSON
├── thredds_response_headers.json    HTTP response headers from one NCSS call
├── NATIVE_METADATA.md               narrative: what's native vs what EnVar adds
└── envar/
    ├── README.md
    └── gridmet_tmmx.provenance.yaml   EnVar sidecar (full provenance)

# When the real R container is used, run.py additionally drops:
outputs/_amadeus_raw.csv
outputs/_amadeus_attributes.json
outputs/_amadeus_session.json
outputs/_amadeus_run_meta.json
```

## Pipeline — step by step

`run.py` is organised in four stages.

### Stage 1 — Translate the canonical cohort

`translate.py` (invoked first by the justfile recipe) reads
`patients_example1.json` and writes `inputs/patient_locations.csv`
with columns `person_loc_id, lat, lon, start_date, end_date`. That's
the `sf`-style point table `amadeus::calculate_covariates()` consumes.
`person_loc_id` == `person_id` here because the canonical cohort has
one address per patient.

### Stage 2 — Try the real R amadeus container

If `envar-amadeus:4.4` is present on the local Docker daemon and
`ENVAR_OFFLINE` / `ENVAR_FORCE_PYTHON` are not set, `run.py`
shells out:

```bash
docker run --rm --platform linux/amd64 -v <here>:/work -w /work \
    envar-amadeus:4.4 Rscript amadeus_extract.R \
    inputs/patient_locations.csv outputs/
```

`amadeus_extract.R` (in this folder) runs the **real**
`amadeus::download_data("gridmet", variables="tmmx")` to fetch the
GridMET NetCDF for each year in the study window, then uses
`terra::rast` + `terra::time` + `terra::extract` to pull per-point
per-day values. Output is written verbatim to
`outputs/_amadeus_raw.csv` and friends. `run.py` reads that CSV back,
projects it to the EnVar contract column order, and stamps the
sidecar with
`execution_mode = real_amadeus_download_real_terra_extract` plus the
image digest.

If the image isn't built or the container exits non-zero, the run
proceeds to stage 3.

### Stage 3 — Python THREDDS-equivalent fallback

For each patient location, GETs:

```text
http://thredds.northwestknowledge.net:8080/thredds/ncss/
    agg_met_tmmx_1979_CurrentYear_CONUS.nc
    ?var=daily_maximum_temperature
    &latitude=<lat>&longitude=<lon>
    &time_start=<start>T00:00:00Z&time_end=<end>T00:00:00Z
    &accept=csv
```

Parses the response (a 4-column CSV: `time, lat, lon,
daily_maximum_temperature[unit="K"]`) and **unpacks the value** —
this is the critical bit:

The THREDDS NCSS CSV is **packed int16** with `scale_factor = 0.1`
and `add_offset = 220.0`. The header advertises `[unit="K"]` even
though the raw value isn't Kelvin. The true Kelvin value is
`raw * 0.1 + 220.0`. Verified for tmmx on 2022-07-19 at
(33.4485, -112.0738): raw = 958 → 315.8 K = 42.65 °C. The
OPeNDAP endpoint at `/thredds/dodsC/...` would auto-unpack via
xarray/netCDF4, but those deps are heavier than the two-line unpack.

Responses and one set of response headers are cached to
`fixtures/` so `ENVAR_OFFLINE=1` runs work without network.

### Stage 4 — Native artefacts + EnVar provenance sidecar

- `gridmet_tmmx.csv` — per-(person × day): `person_id, date, lat,
  lon, value_kelvin, value_celsius`. Both units exposed so the
  downstream OMOP loader doesn't need to know the conversion.
- `gridmet_tmmx.attributes.json` — what `attributes(amadeus_result)`
  would carry in R if serialised (call, package_version, r_version,
  datetime_run_utc, row.names, …).
- `gridmet_tmmx.cf_metadata.json` — the GridMET NetCDF's CF
  Conventions header attributes (`standard_name`, `units`,
  `scale_factor`, `add_offset`, `grid_mapping`, …) fetched from the
  THREDDS `dataset.xml` endpoint and normalised to JSON.
- `thredds_response_headers.json` — HTTP response headers captured
  from one NCSS call (cookies / auth stripped).
- `envar/gridmet_tmmx.provenance.yaml` — the EnVar provenance
  sidecar. Includes:
  - `provenance_id`: ULID-shaped, ends in `-gridmet`. Deterministic
    given (input sha256, tool name, version, run timestamp).
  - `variable.units.{native_units_ucum, output_units_ucum, unit_conversion}`
    declaring the K → °C conversion in machine-actionable form.
  - `spatial.{native_spatial_resolution_m: 4000, crs, extraction_method:
    nearest_cell, target_geography_type}`.
  - `temporal.{temporal_resolution: daily, temporal_aggregation_method:
    maximum, day_boundary_convention: local_midnight, calendar:
    gregorian, extraction_window_*}`.
  - `source_dataset.{name: gridMET (METDATA), short_code: gridmet,
    doi: 10.1002/joc.3413, license_spdx: CC0-1.0, native_format:
    NetCDF-4_CF, access_url}`.
  - `exposure_model.{type: statistical_blend, inputs: [PRISM monthly
    normals, NLDAS-2 sub-daily reanalysis]}` — declaring this is a
    blended/reanalysis product, not a spatial interpolation like
    Daymet.
  - `tool_run.{execution_mode, container_image_*, run_timestamp_utc,
    input_file_sha256, input_row_count, output_file_sha256,
    output_row_count, r_package_call, data_endpoint, packing}`.

## Headline numbers from this pipeline

For person 91204 on 2022-07-19 at (33.4485, -112.0738):

| Quantity | Value |
| --- | --- |
| Raw THREDDS NCSS int16 | 958 |
| Unpacked Kelvin (`raw * 0.1 + 220.0`) | 315.80 K |
| Converted °C (`K − 273.15`) | 42.65 °C |

`scripts/verify.py` pairs this with DeGAUSS / Daymet's 43.91 °C on
the same patient-day to demonstrate the +1.26 °C cross-source spread.

## How Amadeus differs from DeGAUSS / Daymet, methodologically

The EnVar sidecar exists to make these differences machine-readable;
the comparison is what the heat scenario is about.

| Slot | Amadeus / GridMET | DeGAUSS / Daymet |
| --- | --- | --- |
| `spatial.native_spatial_resolution_m` | 4000 | 1000 |
| `spatial.extraction_method` | `nearest_cell` | `inverse_distance_weighted_4_nearest_cells` |
| `exposure_model.type` | `statistical_blend` | `spatial_interpolation` |
| `exposure_model.inputs` | PRISM monthly normals + NLDAS-2 reanalysis | GHCN-Daily station observations |
| `source_dataset.short_code` | `gridmet` | `daymet_v4` |
| `variable.units.native_units_ucum` | `K` | `Cel` |
| `temporal.day_boundary_convention` | `local_midnight` | `local_midnight` |

## Isolation in one diagram

```text
patients_example1.json
        │
        ├──────────────────────────────────────────┐──────────────────────────────┐
        ▼                                          ▼                              ▼
   amadeus/  ─►  gridmet_tmmx.csv             degauss/  ─►  cohort_*_daymet.csv   omop-gaia/  ─►  external_exposure.csv
                  (own provenance: -gridmet)               (own provenance: -daymet)               (own provenance: -omop-gaia-daymet)
```

The three folders share `data/patients_example1.json` as the only
common ancestor.

## How to run

From `examples/heat/`:

```bash
just amadeus      # this folder: translate.py then run.py
```

From this folder directly:

```bash
uv run --script translate.py ../data/patients_example1.json
uv run --script run.py                              # online (R container if built, else THREDDS)
ENVAR_OFFLINE=1 uv run --script run.py              # use bundled fixtures
ENVAR_FORCE_PYTHON=1 uv run --script run.py         # skip the R container even if built
```

| Env var | Default | Effect |
| --- | --- | --- |
| `ENVAR_OFFLINE` | unset | Force-load THREDDS responses from `fixtures/`. The script will not hit the network. |
| `ENVAR_FORCE_PYTHON` | unset | Skip the real R amadeus container even if `envar-amadeus:4.4` is built; go straight to the Python THREDDS path. |

To build the real R amadeus container once:

```bash
docker build --platform linux/amd64 -t envar-amadeus:4.4 .
```

(About a 5–10 minute one-time build of `rocker/geospatial:4.4` +
amadeus + dependencies.)

## Prerequisites

- `uv` (PEP 723 inline-script runner). Host-side deps: `httpx`,
  `pyyaml`.
- For the R path: Docker (with `linux/amd64` emulation on Apple
  Silicon) and the `envar-amadeus:4.4` image built from this folder's
  `Dockerfile`.
- For the Python THREDDS path: network access to
  `thredds.northwestknowledge.net:8080`. Set `ENVAR_OFFLINE=1` to use
  the bundled fixtures and skip the network.
