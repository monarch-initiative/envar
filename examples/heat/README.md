# EnVar heat scenario — runnable end-to-end example

A working, three-way pipeline that takes the **same** patient cohort and runs
it through the **three** systems the heat scenario describes:

| Folder | System | What it does | Data source |
|---|---|---|---|
| `degauss/`   | **DeGAUSS** (NIEHS, Cincinnati Children's)        | Geocodes addresses → coordinates, then extracts daily Tmax from a 1 km gridded weather product. | U.S. Census geocoder + ORNL Daymet Single-Pixel API |
| `amadeus/`   | **Amadeus** (NIEHS, CHORDS)                       | Extracts daily Tmmx from a different 4 km gridded weather product at the same coordinates.       | Northwest Knowledge Network THREDDS (GridMET) |
| `omop-gaia/` | **OMOP CDM / OHDSI GIS (GAIA)**                   | Assembles the Daymet and GridMET outputs into OMOP `person`, `location`, `external_exposure` rows that point back to the upstream EnVar sidecars. | Reads the two outputs above |

Same input. Three implementations. Three outputs.

## Layout

```
examples/heat/
├── justfile                          orchestration (uv run, no project install)
├── README.md                         this file
├── data/
│   └── patients_example1.json        canonical input — 3 patients, 8-day window
├── degauss/
│   ├── translate.py                  patients_example1.json → DeGAUSS input CSV
│   ├── run.py                        geocode + daymet, emit EnVar sidecar
│   └── outputs/                      *.csv + *.provenance.json
├── amadeus/
│   ├── translate.py                  patients_example1.json → Amadeus locations table
│   ├── run.py                        GridMET point extraction, emit EnVar sidecar
│   └── outputs/                      *.csv + *.provenance.yaml
└── omop-gaia/
    ├── translate.py                  patients_example1.json → OMOP person + location
    ├── run.py                        boots the real OHDSI gaiaDB container,
    │                                 registers Daymet+GridMET via
    │                                 backbone.load_jsonld_file(), runs the
    │                                 real working.spatial_join_exposure() to
    │                                 populate external_exposure, exports the
    │                                 OMOP CSVs + the EnVar sidecar layer.
    ├── gaia/jsonld/                  JSON-LD descriptors fed into gaiaDB
    ├── gaia/sql/                     EnVar patches CREATE OR REPLACE-d onto
    │                                 working.spatial_join_exposure (see
    │                                 outputs/NATIVE_METADATA.md for the bug
    │                                 they fix) + a per-day variant
    ├── fixtures/                     bundled upstream outputs so the example
    │                                 still runs with ENVAR_OFFLINE=1
    └── outputs/                      person.csv, location.csv,
                                      external_exposure.csv (per-day),
                                      external_exposure_gaia_native.csv
                                      (gaia-native, window-wide dates),
                                      gaia_catalog/, gaia_db/, envar/sidecars/,
                                      envar/MANIFEST.json
```

## Running

```bash
# from examples/heat/
just degauss         # geocode + Daymet Tmax at each patient's address
just amadeus         # GridMET Tmmx at each patient's coordinates
just omop            # assemble both into OMOP rows
just verify          # compare the two Tmax series side by side
just all             # run all of the above in sequence
just clean           # wipe outputs/
```

All Python is invoked via `uv run --script`, so each script declares its
dependencies inline (PEP 723) and the example needs no project-wide install.

## What's shared and what's per-system

**Shared input** — `data/patients_example1.json`. Carries: `person_id`, sex,
year-of-birth, full address, pre-resolved geocode (lat/lon + precision/score),
observation period.

Each `translate.py` reads that file and emits the per-system input format:
- DeGAUSS wants a CSV with an `address` column (and a separate file with `lat`/`lon` for the daymet step).
- Amadeus wants a CSV with `person_loc_id`, `lat`, `lon`, `date` rows.
- OMOP wants `person` and `location` tables in OMOP CDM v5.4 column order.

**Shared output contract** — each system writes both data and an EnVar
provenance sidecar:

```
{system}/outputs/{file}.csv          the values
{system}/outputs/{file}.provenance.{json,yaml}   the EnVar sidecar
```

The OMOP system reads both sidecars and links them via the
`exposure_source_value` column on every `external_exposure` row (see the
heat-scenario document §5).

## Heads-up on real data

- The DeGAUSS containers are real images (`ghcr.io/degauss-org/geocoder:3.3.0`,
  `ghcr.io/degauss-org/daymet:1.0.0`). Docker Desktop must be running.
- The Daymet container downloads NetCDF tiles via NASA AppEEARS — that's
  the genuine slow path (10–60 min per run depending on AppEEARS queue load).
- You need a NASA EarthData account (free,
  <https://urs.earthdata.nasa.gov/users/new>) **with AppEEARS authorized**
  (sign in once at <https://appeears.earthdatacloud.nasa.gov/> to grant
  access). Then set `DAYMET_USERNAME` and `DAYMET_PASSWORD` before running.
- The Amadeus container runs `amadeus 2.0.0` + `terra` against the
  Northwest Knowledge Network THREDDS endpoint for GridMET.
- The U.S. Census geocoder is rate-limited but tolerant of small batches.
- The `omop-gaia` step boots the **real OHDSI gaiaDB Docker image**
  (built locally from a clone of <https://github.com/OHDSI/gaiaDB>; the
  image tag `gaia-db` is reused if already present). The pipeline calls
  `backbone.load_jsonld_file()` and `working.spatial_join_exposure()`
  inside that container — no Python fallback, no hand-written
  external_exposure rows. Two SQL patches are applied to the upstream
  function (a column-ambiguity bugfix and a per-day-date variant) — see
  `omop-gaia/outputs/NATIVE_METADATA.md` and the manifest's
  `gaia_pipeline.envar_sql_patches_applied` block.

There is no Python fallback for any of the three pipelines. If a service
or container is unavailable, the script exits non-zero. The `omop-gaia`
step accepts `ENVAR_OFFLINE=1` to feed in bundled
`omop-gaia/fixtures/` instead of live upstream outputs — the real
gaia-db container is still booted; only the Daymet/GridMET inputs come
from disk.

## Companion deck

The narrative slide deck `envar-heat-scenario-slides.html` lives alongside
the source-of-truth scenario doc in the internal `niehs_standards` working
repo (`~/ws/notes/niehs_standards/docs/`). The headline values on the
slides — **43.91 °C** from Daymet vs **42.65 °C** from GridMET on 2022-07-19
at person 91204's coordinates, a **+1.26 °C** disagreement — come straight
from this pipeline. Run `just all && just verify` and you'll see the same
numbers, plus the full sidecar diff across the two sources and a confirmation
that every OMOP `external_exposure.exposure_source_value` resolves to a real
sidecar.
