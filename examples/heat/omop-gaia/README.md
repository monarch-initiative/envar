# omop-gaia — isolated OMOP / OHDSI-GIS heat pipeline

The third leg of the heat scenario. `degauss/` and `amadeus/` produce
their own daily-Tmax series; this folder is a **fully independent
third path** that takes the same canonical patient cohort and runs
it end-to-end through the **real OHDSI gaiaDB / gaiaCore SQL
pipeline** to land OMOP CDM v5.4 `person`, `location`, and OHDSI
GIS-WG `external_exposure` rows on disk, with full EnVar provenance.

Isolation is deliberate. `omop-gaia/run.py` reads nothing from
`degauss/outputs/` or `amadeus/outputs/` — it does its own
geocoding, its own Daymet extraction, and assigns its own
provenance IDs. The three pipelines can therefore be compared as
independent runs (same input, three implementations, three
provenance trails).

## What "real GAIA" means here

The OHDSI GIS Working Group's GAIA stack lives in three repositories:

| Repository | Role |
| --- | --- |
| [`OHDSI/gaiaDB`](https://github.com/OHDSI/gaiaDB) | PostgreSQL + PostGIS schema and SQL functions (`backbone.*`, `working.*`, `vocabulary.*`). |
| [`OHDSI/gaiaCatalog`](https://github.com/OHDSI/gaiaCatalog) | Per-dataset `meta_etl_*.json` / `meta_dcat_*.json` / `meta_json-ld_*.json` catalog files. |
| [`OHDSI/gaiaDocker`](https://github.com/OHDSI/gaiaDocker) | docker-compose orchestration that bundles the lot, including a `gaia-degauss` profile that pulls in the same DeGAUSS geocoder container we run here. |

`run.py` builds the `gaia-db` Docker image straight from the upstream
`OHDSI/gaiaDB` Dockerfile, boots it, loads our cohort and Daymet
values, and calls the real `working.spatial_join_exposure()` inside
that live database. The container image digest and the SQL functions
actually invoked are recorded in the EnVar sidecar manifest.

## Layout

```text
omop-gaia/
├── README.md                  this file
├── run.py                     self-contained end-to-end pipeline
├── gaia/
│   ├── jsonld/
│   │   └── daymet_v4_r1.jsonld.json   Schema.org Dataset descriptor for Daymet tmax
│   └── sql/
│       ├── 00_envar_patch_spatial_join.sql
│       │     fixes a real SELECT * bug in working.spatial_join_exposure
│       └── 10_envar_per_day_spatial_join.sql
│             adds working.envar_spatial_join_perday with per-row dates
├── fixtures/                  bundled API responses for offline runs
│   ├── geocoder/
│   │   └── cohort_addresses_geocoded.csv   raw DeGAUSS geocoder output
│   └── daymet/
│       └── daymet_singlepixel_<person>_<start>_<end>.txt   raw Daymet API responses
└── outputs/                   everything the run produces (see below)
```

There is no `translate.py` here. `run.py` materialises OMOP
`person.csv` and `location.csv` itself from `patients_example1.json`
because the `location` table needs `lat`/`lon` from *this* run's
geocoder, not the pre-resolved coordinates baked into the canonical
JSON.

## What's in `outputs/` after a run

```text
outputs/
├── person.csv                          OMOP CDM v5.4 person
├── location.csv                        OMOP CDM v5.4 location — coords from this run's geocoder
├── daymet_tmax.csv                     per-(person × day) Daymet tmax from the single-pixel API
├── external_exposure.csv               OHDSI GIS WG (per-day dates) from working.envar_spatial_join_perday
├── external_exposure_gaia_native.csv   what gaia-db's own working.spatial_join_exposure produced (window-wide dates)
├── NATIVE_METADATA.md
├── gaia_catalog/                       three native gaiaCatalog files for Daymet
│   ├── meta_etl_daymet_tmax.json
│   ├── meta_dcat_daymet_tmax.json
│   └── meta_json-ld_daymet_tmax.json   exact JSON-LD fed into gaia-db
├── gaia_db/                            live snapshots COPYed out of the running DB
│   ├── data_source.csv                    backbone.data_source after ingestion
│   ├── variable_source.csv                backbone.variable_source
│   ├── location.csv                       working.location
│   ├── location_history.csv               working.location_history
│   └── spatial_join_log.txt               psql NOTICE output from the join calls
└── envar/                              EnVar add-on
    ├── README.md
    ├── MANIFEST.json                   provenance index, gaia_pipeline block, isolation_note
    ├── geocoder.provenance.json        sidecar for this run's DeGAUSS geocode
    └── daymet.provenance.json          sidecar for this run's Daymet extraction (chained to geocoder.provenance)
```

## Pipeline — step by step

`run.py` is organised in five stages.

### Stage 1 — Geocode (DeGAUSS geocoder container)

- Reads `patients_example1.json`, builds an in-memory cohort row list
  (`id`, `address`, `start_date`, `end_date`) matching DeGAUSS's
  expected input shape.
- Runs `ghcr.io/degauss-org/geocoder:3.3.0` against that input. This
  is the *same image* gaiaDocker integrates as the `gaia-degauss`
  profile — so we're using GAIA's own geocoding choice, not "borrowing
  from the sibling DeGAUSS pipeline." The sibling pipeline is not
  consulted.
- The geocoder's native CSV output is cached into
  `fixtures/geocoder/cohort_addresses_geocoded.csv` so subsequent
  `ENVAR_OFFLINE=1` runs work without docker / network.
- Records `geocoder.provenance.json` (image tag, image digest, run
  timestamp, input/output row counts, run mode).

### Stage 2 — Daymet single-pixel extraction (ORNL API)

- For each geocoded patient, GETs
  `https://daymet.ornl.gov/single-pixel/api/data?lat=…&lon=…&vars=tmax&start=…&end=…`.
- Parses the response (small free-form header + `year,yday,tmax` CSV).
- Converts day-of-year to ISO date, clips to study window and
  per-patient observation period.
- Caches raw responses to
  `fixtures/daymet/daymet_singlepixel_<person_id>_<start>_<end>.txt`.
- Records the call count, the endpoint, and the inter-request delay in
  the daymet sidecar's `tool_run.run_meta`.

This is intentionally the simplest live-data path Daymet offers — no
NASA EarthData credentials, no NetCDF download, no bulk-extraction.
Same Daymet V4 R1 dataset; server-side single-pixel extraction.

### Stage 3 — Materialise OMOP `person` / `location` / `daymet_tmax` CSVs

- `person.csv` from the canonical JSON (sex → `gender_concept_id`,
  `year_of_birth`, `location_id = person_id`).
- `location.csv` carries **this run's geocoded coordinates** (from
  stage 1), not the pre-resolved coordinates from the JSON. That is
  the key difference vs the previous implementation — the location
  table reflects the geocoder we just ran.
- `daymet_tmax.csv` is the per-(person × day) intermediate from
  stage 2, written verbatim so the upstream extraction is auditable.

### Stage 4 — Real gaia-db pipeline

1. **Ensure the `gaia-db` image is built.** Looks for `gaia-db:envar-heat`,
   then `gaia-db`. If neither exists, finds a local clone of
   `OHDSI/gaiaDB` (probed paths or `--gaia-db-repo` /
   `ENVAR_GAIA_DB_REPO`) and `docker build -t gaia-db:envar-heat .`'s
   it. Records the image digest in the manifest.
2. **Boot the container.** Names it `gaia-db-envar-heat`, exposes
   PostgreSQL on host port `55433` (override with `--host-port` /
   `ENVAR_GAIA_PORT`). gaia-db's init scripts create the
   `backbone`, `working`, `public`, `vocabulary` schemas and install
   the gaiaCore SQL functions.
3. **Wait for readiness.** Polls `pg_isready` *and* a real
   `pg_catalog` query for `working.spatial_join_exposure` until both
   succeed.
4. **Apply two EnVar SQL patches** inside the live database:
   - `gaia/sql/00_envar_patch_spatial_join.sql` replaces the upstream
     `working.spatial_join_exposure` to fix a real
     column-ambiguity bug — see [§ Limitations](#real-pipeline-limits-this-run-surfaces).
   - `gaia/sql/10_envar_per_day_spatial_join.sql` adds
     `working.envar_spatial_join_perday` that preserves per-row
     `source_date` on the output.
5. **Load locations.** Inserts our three rows into `working.location`
   (with `geom = ST_SetSRID(ST_MakePoint(lon, lat), 4326)` using
   this-run's geocoded coords) and three rows into
   `working.location_history` (`domain_id = 1147314` = Person, the
   value gaiaCore's join function looks for).
6. **Register the Daymet dataset via JSON-LD.** Calls
   `SELECT backbone.load_jsonld_file(pg_read_file(...))` with
   `gaia/jsonld/daymet_v4_r1.jsonld.json`. That's gaiaCore's native
   ingestion path — it populates `backbone.data_source` +
   `backbone.variable_source`. The returned `data_source_uuid` is
   captured for the manifest.
7. **Load the per-day data table.** Creates
   `public.daymet_tmax(person_id, source_date, tmax, wgs_geom)` with
   a GiST index, then bulk-inserts one row per (person × day) from
   `daymet_tmax.csv`.
8. **Run two real SQL joins:**
   - `working.spatial_join_exposure('tmax', 'public.daymet_tmax', …,
     'st_within', 100)` — gaia-native; populates
     `working.external_exposure`.
   - `working.envar_spatial_join_perday('tmax', 'public.daymet_tmax',
     'st_within', 100)` — EnVar variant; populates
     `working.external_exposure_perday`.
   The 100 m buffer turns the otherwise-degenerate point-in-point
   predicate into a real `ST_within`. Both sides of the join are the
   patient's own geocoded coord, so 100 m comfortably matches.
9. **Export everything.** `COPY (SELECT … FROM …) TO '/tmp/X.csv'`
   followed by `docker cp` for: the two `external_exposure` tables
   plus the four `gaia_db/*.csv` snapshots (`data_source`,
   `variable_source`, `location`, `location_history`). The four
   psql stdout blocks from the joins are saved to
   `gaia_db/spatial_join_log.txt`.
10. **Tear down.** `docker rm -f gaia-db-envar-heat` and delete
    throw-away secrets. `ENVAR_GAIA_KEEP=1` leaves the container
    running for hand-inspection (`psql -h localhost -p 55433`).

### Stage 5 — Provenance + manifest

- Generate two ULID-shaped provenance IDs unique to this run:
  `<ulid>-omop-gaia-geocoder` and `<ulid>-omop-gaia-daymet`.
- Write `envar/geocoder.provenance.json` and `envar/daymet.provenance.json`
  (the latter `provenance_chain`-references the former).
- Rewrite the raw gaia-db exports into the contract column order,
  replacing `exposure_source_value = 'tmax'` (the gaia variable name)
  with `<ulid>-omop-gaia-daymet` (our provenance ID).
- Write `envar/MANIFEST.json` with a `gaia_pipeline` block recording
  image ref + digest, container name, host port, SQL functions
  invoked, patches applied, registered datasets, and join row counts.
- Emit `gaia_catalog/meta_{etl,dcat,json-ld}_daymet_tmax.json`. The
  JSON-LD file is byte-identical to the one we fed gaia-db.

## Real-pipeline limits this run surfaces

### `spatial_join_exposure` column-ambiguity bug

The upstream `working.spatial_join_exposure` builds its inner `att`
subquery as `SELECT *, '...'::date AS attr_start_date, '...'::date
AS attr_end_date FROM backbone.variable_source`. When any
JSON-LD-registered variable has those columns populated, the subquery
ends up with two columns of the same name and PostgreSQL aborts with
*"column reference attr_start_date is ambiguous"*. Patched at runtime
in stage 4.4; the patch text is in
`gaia/sql/00_envar_patch_spatial_join.sql` and is referenced from
`MANIFEST.json` under `gaia_pipeline.envar_sql_patches_applied`.

### Per-day exposure date collapses to the variable's window

`working.spatial_join_exposure` writes
`exposure_start_date = GREATEST(att.attr_start_date, gol.start_date)`
on every row, where `att.attr_start_date` is the **variable's**
window-wide date from `backbone.variable_source` — never the per-row
data date. The native gaia output (`external_exposure_gaia_native.csv`)
shows every row stamped `2022-07-15 → 2022-07-22` even though each
row carries a different day's tmax. `working.envar_spatial_join_perday`
reads the date from the data row's `source_date` instead; that's
what populates `external_exposure.csv`.

### Raster ingest gap

gaiaCatalog's ETL generator (`backbone.ingest_raw_data`) only handles
vector inputs via ogr2ogr. Daymet is raster-native NetCDF; there is
no automated raster-ingest path in gaia-db today. omop-gaia
side-steps that by pre-extracting per-point values via the Daymet
single-pixel API (stage 2) before handing them to gaia-db's
spatial-join function.

## Isolation in one diagram

```text
patients_example1.json
        │
        ├─────────────────────────────────────────────┐
        │                                             │
        ▼                                             ▼
   degauss/  ──►  cohort_addresses_geocoded_daymet.csv      omop-gaia/  ──► external_exposure.csv
        │           (its own provenance: -daymet)                 │           (its own provenance: -omop-gaia-daymet)
        │                                             │
        ▼                                             ▼
   amadeus/  ──►  gridmet_tmmx.csv                    (independent geocode, independent Daymet
                  (its own provenance: -gridmet)       single-pixel call, real gaia-db spatial join)
```

The three folders share `data/patients_example1.json` as the only
common ancestor. No row, byte, or provenance ID flows between them.

## How to run

From `examples/heat/`:

```bash
just degauss      # independent: own geocoding + Daymet (container)
just amadeus      # independent: own gridMET (THREDDS NCSS or R)
just omop         # independent: own geocoding + Daymet (single-pixel) + gaia-db spatial join
just verify       # cross-pipeline comparison
```

From this folder directly:

```bash
uv run --script run.py                              # online
ENVAR_OFFLINE=1 uv run --script run.py              # use bundled fixtures
ENVAR_GAIA_KEEP=1 uv run --script run.py            # leave gaia-db running afterwards
ENVAR_GAIA_DB_REPO=/path/to/OHDSI/gaiaDB uv run --script run.py
```

| Env var | Default | Effect |
| --- | --- | --- |
| `ENVAR_OFFLINE` | unset | Force-load geocoder + Daymet from `fixtures/`. The script still boots gaia-db and runs the real spatial join. |
| `ENVAR_GAIA_KEEP` | unset | Leave the `gaia-db-envar-heat` container running after `run.py` exits, so you can `psql -h localhost -p 55433 -U postgres -d gaiacore`. |
| `ENVAR_GAIA_PORT` | `55433` | Host port for gaia-db's PostgreSQL listener. |
| `ENVAR_GAIA_DB_REPO` | unset | Path to a local clone of `OHDSI/gaiaDB`, used when no `gaia-db` image exists locally. |

## Prerequisites

- Docker (Docker Desktop or Colima) running locally.
- Either a pre-built `gaia-db` image on the local Docker daemon, or a
  local clone of `OHDSI/gaiaDB` that `run.py` can build from.
- `uv` (PEP 723 inline-script runner). Host-side deps are minimal:
  only `httpx` (HTTP) and `pyyaml`; psql runs *inside* gaia-db.
- Network access to `ghcr.io` (geocoder image) and
  `daymet.ornl.gov` (single-pixel API). Set `ENVAR_OFFLINE=1` to
  bypass both via the bundled fixtures.
