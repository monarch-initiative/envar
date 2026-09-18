# D6.1: EnVar ETL Pipeline (LinkML-Map)

**Deliverable 6.1** — *A working ETL pipeline utilizing LinkML-Map to transform raw
environmental data into the newly proposed OMOP CDM structures.*

Status: **delivered**. A declarative linkml-map transformation takes environmental
exposure values plus their EnVar provenance sidecar and produces OHDSI GIS
`ExternalExposure` rows that validate against the published target schema, unmodified.

Usage instructions and full input/output specifications are on the
[ETL Pipeline page](etl.md). This report covers what was built, how it was tested, and
what remains open.

## What was built

The deliverable is a **trans-spec**, not a script: a declarative statement of how each
OMOP column derives from the source, executed by the
[linkml-map](https://linkml.io/linkml-map/) engine. Nothing in the mapping step is
hand-written transformation code.

| Artifact | Role |
|---|---|
| `daymet_to_external_exposure.transform.yaml` | The deliverable — `DaymetValueRow` → `ExternalExposure`, joined to `PersonLocation` |
| `daymet_values.source.yaml` | Source schema for the value table |
| `prepare_omop.py` | Denormalizes sidecar metadata onto each value row |
| `prepare_locations.py` | Builds the OMOP `Location` table and the person → location lookup |

All four live in
[`examples/heat/omop-gaia/linkml/`](https://github.com/monarch-initiative/EnVar/tree/main/examples/heat/omop-gaia/linkml).

### Both endpoints are published schemas

The transformation connects two independently published LinkML schemas rather than
local scaffolding:

- **Target** — [`linkml-ohdsi-gis-extension-envar`](https://github.com/monarch-initiative/linkml-ohdsi-gis-extension-envar),
  the OMOP GIS extension model, consumed **unmodified**.
- **Source** — a schema for the tool's value table, standing in for what
  [schema-automator](https://linkml.io/schema-automator/) would infer in production.

An earlier increment required a local patch to the target schema, because roughly eight
foreign-key and concept-id slots were marked `identifier: true` — which LinkML treats as
required, rejecting OMOP's nullable-FK and `0`-for-unmapped conventions. That was
[filed upstream](https://github.com/monarch-initiative/linkml-ohdsi-gis-extension-envar/issues/2)
and **fixed at the source**. The local patch script is gone, and released linkml-map
0.5.3 is now sufficient — the unreleased build the earlier work pinned is no longer
needed.

This round trip is worth noting on its own: building the pipeline surfaced a real
modelling defect in the target schema, and the fix landed in the model rather than being
worked around downstream.

### Provenance linkage is the point

Every emitted row carries `exposure_source_value = <sidecar provenance_id>`. Given any
`ExternalExposure` row in the output, you can resolve the sidecar that states which
dataset it came from, at what spatial resolution, by what extraction method, under what
temporal aggregation, and from which tool run. That linkage — not the column mapping —
is what distinguishes this from a generic CSV-to-OMOP loader.

## Testing results

The pipeline was exercised against the heat scenario fixture: three patients, an
eight-day window (2022-07-15 → 2022-07-22), real Daymet V4 R1 Tmax extracted by the
DeGAUSS Daymet container.

| Check | Result |
|---|---|
| Row count | 24 `ExternalExposure` rows (3 persons × 8 days) — matches source |
| Schema validation | `linkml-validate -C ExternalExposure` → **No issues found**, against the published schema unpatched |
| Value fidelity | `value_as_number` equals source Tmax on every row |
| Provenance linkage | All 24 rows resolve to a real sidecar |
| Surrogate keys | Unique across all rows |
| `location_id` FK | Integrity holds; join correctness confirmed against the `Location` table |
| Date semantics | `exposure_start_date == exposure_end_date` for point-in-time observations |
| Headline spot-check | Person 91204, 2022-07-19 → 43.93 °C, matching the source table |

Alongside this, the output was tested against the GAIA catalog path
(EnVar-Tracker #94): OMOP table structure validated, and the real OHDSI `gaiaDB`
container path exercised independently in `examples/heat/omop-gaia/`.

### An observation the testing surfaced

The repository holds two independent extractions of Daymet V4 R1 Tmax at the same
coordinates — the DeGAUSS container (NetCDF tile extraction) and the ORNL single-pixel
API. They disagree by up to 0.02 °C; for person 91204 on 2022-07-19, 43.93 °C versus
43.91 °C.

The magnitude is trivial and neither value is wrong. It is worth recording because it is
a miniature of the problem EnVar exists to address: two defensible implementations of
"Daymet Tmax at this point" produce different numbers, and nothing in the OMOP row
itself would tell a downstream analyst which one they have. The provenance sidecar does.

## Known gaps

These are carried forward rather than resolved in D6.1. The
[ETL Pipeline page](etl.md#known-limitations) describes each in full.

1. **Vocabulary mapping** — all four concept-id columns emit `0` (OMOP's unmapped
   sentinel). The largest open gap, and partly upstream of EnVar: OMOP vocabulary
   coverage for environmental exposures is itself incomplete.
2. **Sidecar ↔ micro-schema reconciliation** — the pipeline consumes the heat scenario's
   `CONTRACT.md` sidecar shape, not the formal `EnvironmentalExposureRecord`
   micro-schema from D4.1. Until these reconcile, only three sidecar fields reach OMOP.
3. **Loader-assigned surrogate keys** — `external_exposure_id` is a deterministic demo
   value; real assignment belongs to the loader.
4. **`Location` / `Person` derived from the model** — currently hand-rolled in Python
   alongside the target schema rather than mapped from it.
5. **dm-bip integration** — driven by the bare linkml-map CLI today; wiring through
   dm-bip's generic `map-data` wrapper is a follow-on, not a rewrite.

## What this unblocks

D6.1 closes the ETL leg of Milestone 6 and unblocks **D6.2 (Pilot Study Results)**,
which applies the pipeline to real cohort data. The usage documentation feeds
**D7.1 (dataset generator documentation)** and **D7.2 (developer guidance)** — the
input/output specification is, in effect, the contract a geospatial tool must meet for
its output to land in OMOP through this path.
