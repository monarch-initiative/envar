# degauss — isolated Daymet Tmax heat pipeline

The first leg of the heat scenario. Takes the canonical patient
cohort (`data/patients_example1.json`) and runs it end-to-end
through the **real** NIEHS DeGAUSS containers: the Census-based
geocoder, then the AppEEARS-based Daymet extractor. Output is one
row per (person × day) of daily maximum 2-m air temperature in °C,
paired with an EnVar provenance sidecar that records both container
runs.

Isolation is deliberate. `degauss/run.py` reads nothing from
`amadeus/outputs/` or `omop-gaia/outputs/` — its sole input is
`patients_example1.json`. The three heat-scenario pipelines can
therefore be compared as independent runs (same input, three
implementations, three provenance trails).

## What "real DeGAUSS" means here

[DeGAUSS](https://degauss.org/) is the NIEHS / Cincinnati Children's
collection of single-purpose Docker containers for geomarker work.
This folder runs **two of them**, in sequence:

| Container | Purpose | Reference data |
| --- | --- | --- |
| [`ghcr.io/degauss-org/geocoder:3.3.0`](https://degauss.org/geocoder/) | Address → lat/lon. Wraps the U.S. Census geocoder and emits a CSV with `lat`, `lon`, `precision`, `score`, `geocode_result`, and the matched address fields. **No credentials required.** | U.S. Census TIGER/Line + ZCTA |
| [`ghcr.io/degauss-org/daymet:1.0.0`](https://degauss.org/daymet/) | (lat/lon, date range) → daily Daymet variables. Downloads Daymet V4 R1 NetCDF tiles from NASA's [AppEEARS](https://appeears.earthdatacloud.nasa.gov/) and extracts per-point per-day values via terra. | Daymet V4 R1 (NASA ORNL DAAC) |

There is no Python fallback in this pipeline — if Docker is missing
or AppEEARS credentials are unavailable, the run aborts with a clear
error. That's intentional: the comparison with amadeus / omop-gaia
hinges on what the real DeGAUSS toolchain actually produces.

The daymet container's output is cached at `_cache/daymet/<key>/`
keyed by `(input CSV sha256, image tag, --vars)`. Subsequent runs
with the same input reuse the cached CSV and skip the (slow)
AppEEARS round-trip. `ENVAR_NO_CACHE=1` forces a re-fetch.

## Layout

```text
degauss/
├── README.md                  this file
├── translate.py               patients_example1.json → cohort_addresses.csv
├── run.py                     run geocoder + daymet containers, emit EnVar sidecar
├── inputs/
│   └── cohort_addresses.csv   produced by translate.py
├── fixtures/                  bundled API responses for `outputs/census_geocoder_responses.json`
│   ├── census_<digest>.txt        cached Census raw responses (per address hash)
│   └── daymet_<digest>.txt        cached Daymet single-pixel responses (per coord hash) — present for archival; the real pipeline uses the AppEEARS container, not single-pixel
├── _docker_workdir/           bind-mount workspace for the two containers (cleared each run)
├── _cache/daymet/<key>/       content-addressed cache of daymet container outputs
└── outputs/                   everything the run produces (see below)
```

## What's in `outputs/` after a run

```text
outputs/
├── cohort_addresses_geocoder_3.3.0_score_threshold_0.5.csv
│       Byte-identical copy of the geocoder container's joined CSV (DeGAUSS-native, uses `id`).
├── cohort_addresses_geocoded_daymet_1.0.0.csv
│       Byte-identical copy of the daymet container's joined CSV (DeGAUSS-native, uses `id`).
├── cohort_addresses_geocoded.csv
│       EnVar-aliased copy of the geocoder CSV: id → person_id, stable-sorted, joined back to the input.
├── cohort_addresses_geocoded_daymet.csv
│       EnVar-aliased copy of the daymet CSV: per-(person × day), columns `person_id, date, lat, lon, precision, score, tmax` (°C).
├── census_geocoder_responses.json
│       Per-address raw responses from the live Census geocoder, keyed by sha256 of the input address.
├── NATIVE_METADATA.md         narrative: what's native vs what EnVar adds
└── envar/
    ├── README.md
    └── cohort_addresses_geocoded_daymet.provenance.json   EnVar sidecar (full provenance, both container runs)
```

Both `*_native_*` CSVs are kept verbatim so anyone diffing against
upstream DeGAUSS docs gets the same bytes. The EnVar-aliased CSVs
are what downstream consumers (`amadeus/`, `omop-gaia/`,
`scripts/verify.py`) and the EnVar sidecar's `output_file_sha256`
point to.

## Pipeline — step by step

`run.py` is organised in three stages.

### Stage 1 — Translate the canonical cohort

`translate.py` (invoked first by the justfile recipe) reads
`patients_example1.json` and writes
`inputs/cohort_addresses.csv` with columns
`person_id, address, start_date, end_date`. The `address` field is
DeGAUSS's expected `"<street> <zip>"` form (no city/state/apartment),
preferring the JSON's `geocoder_input` if present.

### Stage 2 — Geocode (real DeGAUSS geocoder container)

```bash
docker run --rm --platform linux/amd64 -v <work>:/tmp \
    ghcr.io/degauss-org/geocoder:3.3.0 cohort_addresses.csv
```

The container expects a CSV with an `id` column (not `person_id`),
so `run.py` rewrites the input on the fly. The container's native
output filename is
`cohort_addresses_geocoder_3.3.0_score_threshold_0.5.csv`; that file
is copied to `outputs/` byte-identically and **also** re-emitted as
`cohort_addresses_geocoded.csv` with `id` renamed back to
`person_id` and rows stable-sorted by `person_id`.

The geocoder also writes per-address Census API responses into
`outputs/census_geocoder_responses.json`, keyed by sha256 of the
input address (matching what's bundled under `fixtures/census_*`).

### Stage 3 — Daymet extraction (real DeGAUSS daymet container)

```bash
docker run --rm --platform linux/amd64 \
    -e daymet_username=... -e daymet_password=... \
    -v <work>:/tmp \
    ghcr.io/degauss-org/daymet:1.0.0 cohort_addresses_geocoded.csv --vars=tmax
```

The container hits NASA's AppEEARS API, downloads the relevant
Daymet V4 R1 NetCDF tiles, opens them with terra, and extracts a
per-(person × day) `tmax` series for each row of the geocoded CSV.
Native output is
`cohort_addresses_geocoded_daymet_1.0.0.csv`; copied verbatim to
`outputs/` and re-emitted as `cohort_addresses_geocoded_daymet.csv`
with the EnVar column set.

The native daymet CSV is also stored in `_cache/daymet/<key>/`. The
key is `sha256(input CSV bytes) | image tag | --vars`. Subsequent
runs whose input hashes to the same key reuse the cached output and
skip the (10–60-minute) AppEEARS round-trip. `ENVAR_NO_CACHE=1` to
force a re-fetch.

### Stage 4 — EnVar provenance sidecar

`outputs/envar/cohort_addresses_geocoded_daymet.provenance.json`
records the full provenance:

- `provenance_id`: ULID, ends in `-daymet`. Deterministic given
  (input sha256, tool name, version, run timestamp).
- `variable.{name: tmax, cf_standard_name: air_temperature,
  cf_cell_methods: "time: maximum", units_ucum: Cel}`.
- `spatial.{native_spatial_resolution_m: 1000, crs: EPSG:4326,
  extraction_method: inverse_distance_weighted_4_nearest_cells,
  target_geography_type: point_residence}`.
- `temporal.{temporal_resolution: daily, temporal_aggregation_method:
  maximum, day_boundary_convention: local_midnight, calendar:
  gregorian, extraction_window_*}`.
- `source_dataset.{name: "Daymet V4 Daily Surface Weather Data",
  short_code: daymet_v4, doi: 10.3334/ORNLDAAC/2129, version: V4 R1,
  producer_institution: "NASA ORNL DAAC",
  license_spdx: public-domain-us-gov, native_format: NetCDF-4_CF,
  access_url}`.
- `exposure_model.{type: spatial_interpolation, inputs:
  ["GHCN-Daily station observations"]}` — declaring this is a
  station-network interpolation, not a reanalysis blend.
- `tool_run.{tool_name: daymet, tool_version: 1.0.0, execution_mode:
  real_container, container_image_repository,
  container_image_tag, container_image_digest, run_timestamp_utc,
  input_file_sha256, input_row_count, output_file_sha256,
  output_row_count}`.
- `provenance_chain[0]` — the **geocoder** run, recorded as a
  separately-identified upstream step with its own `provenance_id`
  (`-geocoder`), container image digest, input/output sha256s, and
  source-dataset block (U.S. Census TIGER/Line + ZCTA).

The provenance chain is what makes DeGAUSS's output composable: the
downstream `omop-gaia/` pipeline can pull either ID out of the
manifest and resolve it to the right step.

## Headline numbers from this pipeline

For person 91204 on 2022-07-19 at the matched Census coordinate:

| Quantity | Value |
| --- | --- |
| Daymet tmax (°C) | **43.91 °C** |

`scripts/verify.py` pairs this with Amadeus / GridMET's 42.65 °C on
the same patient-day to demonstrate the +1.26 °C cross-source spread.

## How DeGAUSS / Daymet differs from Amadeus / GridMET, methodologically

The EnVar sidecar exists to make these differences machine-readable;
the comparison is what the heat scenario is about.

| Slot | DeGAUSS / Daymet | Amadeus / GridMET |
| --- | --- | --- |
| `spatial.native_spatial_resolution_m` | 1000 | 4000 |
| `spatial.extraction_method` | `inverse_distance_weighted_4_nearest_cells` | `nearest_cell` |
| `exposure_model.type` | `spatial_interpolation` | `statistical_blend` |
| `exposure_model.inputs` | GHCN-Daily station observations | PRISM monthly normals + NLDAS-2 reanalysis |
| `source_dataset.short_code` | `daymet_v4` | `gridmet` |
| `variable.units.native_units_ucum` | `Cel` | `K` |
| `temporal.day_boundary_convention` | `local_midnight` | `local_midnight` |

## Isolation in one diagram

```text
patients_example1.json
        │
        ├──────────────────────────────────────────┐──────────────────────────────┐
        ▼                                          ▼                              ▼
   degauss/  ─►  cohort_*_daymet.csv          amadeus/  ─►  gridmet_tmmx.csv      omop-gaia/  ─►  external_exposure.csv
                  (own provenance: -daymet)               (own provenance: -gridmet)               (own provenance: -omop-gaia-daymet)
```

The three folders share `data/patients_example1.json` as the only
common ancestor.

## How to run

From `examples/heat/`:

```bash
just degauss      # this folder: translate.py then run.py
```

From this folder directly:

```bash
uv run --script translate.py ../data/patients_example1.json
DAYMET_USERNAME=... DAYMET_PASSWORD=... uv run --script run.py
```

A repo-root `.env` file with `DAYMET_USERNAME` / `DAYMET_PASSWORD`
is auto-loaded by the justfile (`set dotenv-load := true`).

| Env var | Default | Effect |
| --- | --- | --- |
| `DAYMET_USERNAME` | required | NASA EarthData (URS) username. Free signup at <https://urs.earthdata.nasa.gov/users/new>. |
| `DAYMET_PASSWORD` | required | URS password. The account must additionally be authorized for AppEEARS — sign in once at <https://appeears.earthdatacloud.nasa.gov/> to grant access. |
| `ENVAR_NO_CACHE` | unset | Force a re-fetch even when `_cache/daymet/<key>/` already has the result. |

## Prerequisites

- Docker (Docker Desktop or Colima) with `linux/amd64` emulation on
  Apple Silicon. The two DeGAUSS images are pulled automatically.
- A NASA EarthData (URS) account with AppEEARS authorization. The
  AppEEARS sign-in step is one-time; without it the daymet container
  returns *"Failed to login"* and the run aborts.
- `uv` (PEP 723 inline-script runner). Host-side deps: none beyond
  stdlib.
- Network access to `ghcr.io` (images) and AppEEARS
  (`appeears.earthdatacloud.nasa.gov`) the first time you run; after
  that, `_cache/daymet/<key>/` lets you re-run offline as long as
  the input hasn't changed.
