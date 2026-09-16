# ETL Pipeline: Usage and Specifications

How to run the EnVar ETL pipeline, what it requires, what it produces, and where it
falls short. The worked reference implementation is the **heat scenario** — daily
maximum air temperature (Tmax) from [Daymet V4 R1](https://doi.org/10.3334/ORNLDAAC/2129)
assigned to a three-patient cohort — and lives in
[`examples/heat/omop-gaia/linkml/`](https://github.com/monarch-initiative/EnVar/tree/main/examples/heat/omop-gaia/linkml).

## What the pipeline does

It takes two things a geospatial exposure tool produces:

1. a **value table** — one row per (person × day) carrying the measured value, and
2. an **EnVar sidecar** — the provenance record describing *how* that value was
   assigned (source dataset, spatial resolution, extraction method, temporal
   aggregation, tool version, run timestamp)

and emits OMOP CDM rows under the OHDSI GIS `ExternalExposure` extension, with every
row carrying a pointer back to the sidecar that explains it.

```text
   Daymet value table  ─┐
   (person × day Tmax)  ├─► prepare_omop.py ──► DaymetValueRow ─┐
   EnVar sidecar       ─┘    (denormalize)                      │
                                                                ├─► linkml-map ──► ExternalExposure
   geocoder output ──────► prepare_locations.py ──► Location ───┤   (trans-spec)      (+ Location)
                                                  PersonLocation┘
```

The middle step is the deliverable: a declarative
[trans-spec](https://github.com/monarch-initiative/EnVar/blob/main/examples/heat/omop-gaia/linkml/daymet_to_external_exposure.transform.yaml)
that linkml-map executes. The two Python scripts around it are *preparation*, not
transformation — they reshape inputs into the flat records linkml-map consumes.

!!! note "Why the prepare steps exist"
    linkml-map derives each output object from one source object. The sidecar describes
    a whole extraction run, not a single row, and linkml-map's per-object expressions
    cannot reach parent-scope values — so `prepare_omop.py` denormalizes the run-level
    metadata onto each value row first. Likewise `prepare_locations.py` builds the
    `person_id → location_id` lookup that the trans-spec's `joins` block resolves
    against.

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | ≥ 3.11 | |
| [`linkml-map`](https://pypi.org/project/linkml-map/) | 0.5.3 | Released version is sufficient |
| [`linkml`](https://pypi.org/project/linkml/) | 1.11.1 | Supplies `linkml-validate` |
| Target schema | — | [`linkml-ohdsi-gis-extension-envar`](https://github.com/monarch-initiative/linkml-ohdsi-gis-extension-envar), used **unmodified** |

```bash
uv venv .venv
uv pip install --python .venv/bin/python linkml-map linkml
```

!!! warning "`uv venv` ships no pip"
    `python -m pip install` fails inside a `uv venv`. Use
    `uv pip install --python <venv>/bin/python` as above.

The mapping step needs no Docker and no network. Producing the *inputs* does — see
[Generating the inputs](#generating-the-inputs).

## Input specification

### 1. Value table (CSV)

One row per (person × day). For the heat scenario this is
`degauss/outputs/cohort_addresses_geocoded_daymet.csv`, produced by the DeGAUSS
Daymet container.

| Column | Type | Required | Description |
|---|---|---|---|
| `person_id` | integer | yes | OMOP person identifier |
| `date` | date | yes | ISO-8601 observation day |
| `tmax` | float | yes | Daily maximum air temperature, °C (UCUM `Cel`) |

Additional columns are ignored. The source schema declaring these is
[`daymet_values.source.yaml`](https://github.com/monarch-initiative/EnVar/blob/main/examples/heat/omop-gaia/linkml/daymet_values.source.yaml);
it stands in for the schema a production pipeline would infer via
[schema-automator](https://linkml.io/schema-automator/).

### 2. EnVar sidecar (JSON)

The provenance record emitted alongside the value table. The pipeline reads three
fields from it:

| Sidecar path | Becomes | Example |
|---|---|---|
| `provenance_id` | `exposure_source_value` | `01KT4EDTA3GAXAG0DMRCHHGAJA-daymet` |
| `variable.units_ucum` | `dose_unit_source_value` | `Cel` |
| `exposure_model.type` | carried, not yet mapped | `spatial_interpolation` |

The full sidecar carries considerably more (spatial resolution, CRS, extraction method,
temporal aggregation, day-boundary convention, source DOI, license, tool version, row
counts) — see the heat scenario's
[`CONTRACT.md`](https://github.com/monarch-initiative/EnVar/blob/main/examples/heat/CONTRACT.md).
Only the three fields above reach OMOP today; the rest is addressed under
[Known limitations](#known-limitations).

### 3. Geocoder output (CSV)

Used to build the OMOP `Location` table and the person → location lookup. Requires
`person_id`, `lat`, `lon`, and address components (`matched_street`, `matched_city`,
`matched_state`, `matched_zip`).

## Running the pipeline

```bash
cd examples/heat/omop-gaia/linkml
TARGET=<path>/linkml_ohdsi_gis_extension_envar.yaml
```

**Step 1 — prepare.** Denormalize the sidecar onto the value rows, and build the
`Location` table plus the `person_id → location_id` lookup:

```bash
uv run --script prepare_omop.py \
  ../../degauss/outputs/cohort_addresses_geocoded_daymet.csv \
  ../../degauss/outputs/envar/cohort_addresses_geocoded_daymet.provenance.json \
  --out inputs/daymet_values_prepared.csv

uv run --script prepare_locations.py \
  ../../degauss/outputs/cohort_addresses_geocoded.csv
```

**Step 2 — transform.** linkml-map reads a *directory* containing one file per source
class, named `<SourceType>.csv`:

```bash
mkdir -p indir out
cp inputs/daymet_values_prepared.csv indir/DaymetValueRow.csv
cp inputs/PersonLocation.csv          indir/PersonLocation.csv

linkml-map map-data \
  -T daymet_to_external_exposure.transform.yaml \
  -s daymet_values.source.yaml \
  --target-schema "$TARGET" \
  -f csv -o out/external_exposure.csv indir/
```

!!! danger "`map-data` needs a directory, not a file"
    Passing a single CSV path **silently yields zero rows** — no error, no warning. The
    directory must contain a file named exactly `<SourceType>.csv` for each class the
    trans-spec references, including join targets.

**Step 3 — validate:**

```bash
linkml-validate -s "$TARGET" -C ExternalExposure out/external_exposure.csv
```

Expected output: `No issues found`.

## Output specification

### `ExternalExposure` (OHDSI GIS extension)

One row per (person × day). Column derivations:

| OMOP column | Derived from | Notes |
|---|---|---|
| `external_exposure_id` | `person_id` + `date` | Deterministic demo surrogate; see limitations |
| `person_id` | `person_id` | |
| `location_id` | `PersonLocation` join | Resolved via `person_id` |
| `value_as_number` | `tmax` | The measured value |
| `exposure_start_date` | `date` | Point-in-time observation: start == end |
| `exposure_end_date` | `date` | |
| `exposure_source_value` | sidecar `provenance_id` | **The provenance link** |
| `dose_unit_source_value` | sidecar `variable.units_ucum` | e.g. `Cel` |
| `exposure_concept_id` | — | `0` (unmapped) |
| `exposure_type_concept_id` | — | `0` (unmapped) |
| `exposure_relationship_concept_id` | — | `0` (unmapped) |
| `unit_concept_id` | — | `0` (unmapped) |

The concept-id columns are emitted as `0` — OMOP's standard *unmapped concept* sentinel
— rather than left null. The target schema requires all but `unit_concept_id`, and `0`
states the gap in OMOP's own vocabulary instead of leaving a hole.

### `Location` (OMOP CDM v5.4)

Emitted by `prepare_locations.py`, deduplicated by address:

| Column | Source |
|---|---|
| `location_id` | Assigned sequentially |
| `address_1`, `city`, `state`, `zip` | Geocoder match fields |
| `latitude`, `longitude` | Geocoder coordinates |

### Reference run

Against the bundled heat fixture the pipeline produces **24 `ExternalExposure` rows**
(3 persons × 8 days) and a **3-row `Location` table**, validating clean against the
published target schema with no local patches.

## Known limitations

**Vocabulary mapping is unresolved.** All four concept-id columns emit `0`. This is the
largest open gap and it is not an oversight in the mapping — the sidecar's own
`target_concept_id` is a declared gap (`concept_status: gap`), and OMOP's vocabulary
coverage for environmental exposures is itself incomplete. Expanding that coverage is
active work with the OHDSI GIS Working Group.

**Surrogate keys are demo values.** `external_exposure_id` is computed deterministically
from `person_id` and `date` so that the required key is populated and the output
validates. In a real deployment, surrogate-key assignment belongs to the loader.

**Sidecar shape is not yet the micro-schema.** The pipeline consumes the heat scenario's
`CONTRACT.md` sidecar shape, not the formal
[`EnvironmentalExposureRecord`](https://github.com/matentzn/linkml-microschemas-envar)
micro-schema (D4.1). Reconciling the two is pending, and until it lands only three
sidecar fields reach OMOP — the spatial, temporal, and exposure-model blocks that carry
most of EnVar's value are not yet represented in the OMOP output.

**`Location` and `Person` are built alongside the model, not from it.** The target
schema now defines `Location` and `Person` classes, but `prepare_locations.py`
hand-rolls the `Location` table in Python. It should derive from the model through a
trans-spec like `ExternalExposure` does.

**Single-source only.** The pipeline handles one sidecar per value table, so joining the
run-level metadata is a constant denormalization. Multi-source exposure assembly is
untested.

**Run through bare `linkml-map`.** The reference run invokes the linkml-map CLI
directly. [`dm-bip`](https://github.com/monarch-initiative/dm-bip)'s `map-data` target
is a generic wrapper around the same call, so wiring this through dm-bip is a follow-on
rather than a rewrite.

### Upstream tool constraints

Three linkml-map behaviours the trans-spec or the run instructions work around:

- **Directory-only input** (above) — a single file path silently produces nothing.
- **Constant derivations.** On 0.5.3, `value: 0` gets an identity `populated_from`
  injected, producing a spurious "source slot not found" error per constant. The
  trans-spec uses `expr: "0"` instead; the output is identical. Tracked as
  [linkml-map#326](https://github.com/linkml/linkml-map/issues/326).
- **Trailing document separator.** `map-data` ends its YAML stream with a trailing
  `---`, so `linkml-validate` on YAML output reports one spurious
  `None is not of type 'object'`. CSV output is unaffected.

## Generating the inputs

The mapping step consumes committed fixtures, so it runs offline. Regenerating those
fixtures from live sources requires more:

```bash
cd examples/heat
just degauss    # DeGAUSS geocoder + Daymet containers → value table + sidecar
just amadeus    # GridMET via THREDDS → comparison series
just omop       # full OHDSI gaiaDB path (boots the real gaia-db container)
just verify     # cross-pipeline comparison
```

These need Docker, network access to `ghcr.io` and the data services, and — for the
DeGAUSS Daymet container — a NASA EarthData account with AppEEARS authorized. See the
[heat scenario README](https://github.com/monarch-initiative/EnVar/blob/main/examples/heat/README.md)
for details.

!!! note "Two Daymet paths, two slightly different answers"
    The repository contains two independent extractions of Daymet V4 R1 Tmax at the same
    coordinates: the **DeGAUSS container** (NetCDF tile extraction), which is what this
    pipeline consumes, and the **ORNL single-pixel API**, used by the `omop-gaia` GAIA
    leg. They disagree by up to 0.02 °C — for person 91204 on 2022-07-19, 43.93 °C
    versus 43.91 °C. Same dataset, same point, different extraction implementation.
    It is a small disagreement, but it is exactly the class of difference EnVar's
    provenance sidecar exists to make visible.
