# GaiaCatalog → EnVar sidecar (linkml-map) — D2.2 metadata coverage

A declarative linkml-map trans-spec from a real GaiaCatalog entry to the EnVar
micro-schema sidecar (`EnvironmentalExposureRecord`), built to answer two
questions the D2.2 audit (EnVar-Tracker #4) poses but leaves open:

> **Question:** What's missing from the three above metadata files? Do we have
> specific fields in the proposed EnVar metadata sidecar that are not being met
> with these files?

and the SOW gap whose section is currently the placeholder `Text`:

> **No minimal metadata standard for geospatial-based EDoHs**

## Result

A GaiaCatalog entry fills **19 of the 119 slots** carried by the eight
**required** composite blocks (**16%**). Counting the whole record — optional
blocks and top-level scalars included — it fills **22 of 178** leaf slots
(**12%**). **16 required slots have no source in the catalog**, and **3 of the 8
required blocks come out entirely empty**.

That 16 is 15 + 1: the table below subtotals **15** required-unfilled slots
across the eight required composite blocks, and the sixteenth is `subject`, a
required *top-level scalar* counted in its own section further down. The split
is easy to misread as an arithmetic error, so it is worth stating plainly —
and `subject` is the more interesting of the two halves (see
[finding 1](#1-two-required-blocks-cannot-exist-at-catalog-time-a-third-is-stated-only-in-prose)).

```
required composite blocks
                        filled   empty   total   required unfilled
------------------------------------------------------------------
variable_identity            8      10      18   3
spatial_reference            3       9      12   3
temporal_reference           2       7       9   3
exposure_model               0      11      11   1  <-- entirely empty
data_layout                  1      12      13   1
source_dataset               5      13      18   1
tool_run                     0      17      17   2  <-- entirely empty
linkage_method               0      21      21   1  <-- entirely empty
------------------------------------------------------------------
SUBTOTAL                    19     100     119   15

optional composite blocks (excluded from the headline figure)
  uncertainty 0/13 · derived_heat_metric 0/26 · provenance_chain 0/3
  health_layer_linkage 0/4 · deposit_metadata 0/9

top-level scalar slots
  subject 0/1 (required) · schema_version 1/1 · provenance_id 1/1 · phi_status 1/1
```

Which figure to quote depends on the claim. **16%** answers "how much of what
EnVar *requires* can a catalog supply"; **12%** answers "how much of the sidecar
does a catalog describe at all". The 12% denominator does include
`derived_heat_metric` — 26 heat-specific slots with nothing to say about a PM2.5
dataset — so the fairest whole-record figure excluding it is **22/152 (14%)**.
The findings below quote the required-block figure.

The output **does not validate** against the EnVar micro-schema. That is the
finding, not a defect — `linkml-validate` enumerates exactly which required
fields a catalog entry cannot supply.

`linkml-validate` reports 324 errors: 17 per record across 19 records, plus one
spurious `None is not of type 'object'`. That last one is a linkml-map output
quirk, not a finding — `map-data` terminates the YAML stream with a trailing
`---`, which parses as a 20th, empty document.

The 17 per-record errors are the **16 missing required slots** above plus **one
value error**: `source_native_format` carries the catalog's stated `shp`, which
the EnVar enum does not admit (finding 6). A stated-but-unrepresentable value is
a different kind of gap from an absent one, so `coverage_report.py` counts it as
filled while the validator counts it as an error. Both are correct; the
difference is the whole point of finding 6.

## Mapping rule

A target slot is populated **only where the catalog states the value**. Anything
requiring inference from prose, from a column-naming convention, or from
knowledge of a particular extraction run is deliberately left empty. Filling
those with plausible guesses would erase the measurement.

Two normalizations are allowed, because they are lossless restatements rather
than inferences: string→number casts on `minValue`/`maxValue` (the catalog
stores `"83"`, EnVar types it numeric), and reducing the bbox ring to four
bounds (the catalog's ring is axis-aligned and already labelled bbox).

One further exception is a *selection* rather than a normalization: the catalog
states a CRS five times, under names that do not say which is the storage CRS
and which the analytic one (finding 7), so the transform picks `dct:conformsTo`.
Recorded here because it is a judgement call, and the rule above is otherwise
meant to leave no room for one.

## Files

| File | Role |
|---|---|
| `../fixtures/` | The real `OHDSI/gaiaCatalog` entry for `global_pm25_concentration_1998_2016`, vendored unmodified — all three metadata files |
| `gaia_catalog.source.yaml` | Source schema for a flattened catalog variable row (stands in for Bryan's `gaia_catalog_addition` branch) |
| `prepare_gaia.py` | Flattens the three metadata files into one row per measured variable |
| `gaia_to_envar_record.transform.yaml` | The trans-spec: `GaiaVariableRow` → `EnvironmentalExposureRecord` |
| `coverage_report.py` | Counts filled / empty / required-unfilled per block, resolving the record through `SchemaView` so imported slots and `slot_usage` overrides induce the same way `linkml-validate` induces them |
| `envar_model.py` | Locates the pinned EnVar schema and checks the installed model matches `uv.lock` |
| `test_claims.py` | Checks the headline numbers, and the findings' statements of fact, against the fixtures and the pinned model |

## Run

The EnVar model is a project dependency, pinned to an exact
`linkml-microschemas-envar` commit by `uv.lock`; `uv sync` from the repo root
installs it. `envar_model.py` locates its schema and refuses to run if the
installed commit is not the pinned one.

```bash
cd examples/gaia-catalog/linkml
ENVAR=$(uv run python envar_model.py)

# 1. flatten the catalog entry to one row per measured variable
uv run python prepare_gaia.py ../fixtures --out inputs/gaia_variable_rows.json

# 2. transform. NOTE: map-data needs a DIRECTORY containing a <SourceType>.json —
#    a single JSON file holding a list is passed through untransformed, silently.
mkdir -p indir out && cp inputs/gaia_variable_rows.json indir/GaiaVariableRow.json
uv run linkml-map map-data -T gaia_to_envar_record.transform.yaml \
  -s gaia_catalog.source.yaml --target-schema "$ENVAR" \
  -o out/envar_records.yaml indir/

# 3. the gap, enumerated two ways
uv run linkml-validate -s "$ENVAR" -C EnvironmentalExposureRecord out/envar_records.yaml
uv run python coverage_report.py out/envar_records.yaml
```

The headline numbers, and the statements of fact in the findings below, are
checked by `test_claims.py` (`uv run pytest examples/gaia-catalog/linkml` from
the repo root). What the tests cannot check is the interpretation; that is
where review is worth spending.

## Findings

### 1. Two required blocks cannot exist at catalog time; a third is stated only in prose

`exposure_model`, `linkage_method` and `tool_run` come out empty — 49 slots
between them — but not for the same reason, and the recommendation differs.

**Cannot exist at catalog time: `linkage_method`, `tool_run`.** A catalog entry
describes a *published dataset*; these blocks describe *what someone did with
it* — how it was joined to a patient cohort, which tool ran with which
arguments. The catalog does describe *a* run: DCAT `prov:action` carries GDSC's
own ETL pseudo-code. That is the catalog's ingestion of the dataset, not an
extraction against a cohort, so it does not fill `tool_run`. The JSON-LD
`about[0].potentialAction.description` — the catalog's slot for that
transformation — is the literal string `"TODO"`.

`subject` fails for the same reason. It is required, and it is inherited from
the imported LinkML Microschema Profile rather than declared in a local
`envar_*.yaml`, so a tool that walks only the schema directory will not see it
at all. There is no cohort until someone runs an extraction against one.

**Stated, with no structured home: `exposure_model`.** The catalog does state
the model, in the dataset description: PM2.5 grids from MODIS, MISR and SeaWiFS
aerosol optical depth with GWR, and country averages that are
population-weighted. That is `exposure_model_type` and `exposure_model_inputs`
— and `population_weighting_source` — in prose. Same class of gap as
`temporal_aggregation_method` ("average annual concentration", also prose),
and fixable on the catalog side in a way the two blocks above are not.

**Implication for EnVar:** this is the producer-stage / linkage-stage split
already agreed for the model — linkage-stage fields non-required so a
producer-only sidecar validates — reached here from the catalog side. The
catalog can supply the producer layer, partly in prose; the linkage layer has to
be emitted by the extraction tool at run time.

Two of the 16 required gaps are EnVar's own: `native_spatial_resolution_m` is
required and typed float on a vector polygon dataset, and
`day_boundary_convention` is required on annual data. Neither has a
`missing_reason` companion, while `extraction_buffer_m` and
`population_weighting_source` do. Filed as
[linkml-microschemas-envar#42](https://github.com/monarch-initiative/linkml-microschemas-envar/issues/42).

### 2. The year is in the catalog, just not in the JSON-LD

All 19 measured variables (`avpmu_1998` … `avpmu_2016`) share a single
`propertyID` — `2052499839`. In the JSON-LD the year lives only in the column
name and in per-variable `startDate`/`endDate`.

But the catalog does distinguish the years at the identifier level. The
per-variable `attributes` strings in the ETL and DCAT files end in a distinct
Gaia concept id per year — `gaia-407` for 1998 through `gaia-425` for 2016 —
and that id appears nowhere in the JSON-LD. The WG's metadata template puts the
source concept in `propertyID` and the Gaia concept in `alternateName`; this
entry has no `alternateName` anywhere. The discriminator exists in the profile;
the deployed entry does not emit it.

No field states that the table is wide, so `data_layout.table_orientation` is
unfillable even though the entry plainly is wide.

### 3. `propertyID` and `unitCode` carry OMOP concept ids

Here `propertyID` is an OMOP concept id (`"2052499839"`) and `unitCode` is an
OMOP concept id for the unit (`"32964"`). schema.org defines `unitCode` as a
UN/CEFACT common code or a URL, so a bare OMOP id there is outside its own
vocabulary, and nothing in the entry says which vocabulary either code is from.

`2052499839` sits in the 2-billion custom range, so the vocabulary-provenance
problem documented in D2.2's vocabulary section reappears *inside* the metadata
layer. `units_ucum` is required by EnVar and cannot be filled, because what the
catalog offers is an opaque concept id and free-text prose
(`"micrograms/cubic meter"`).

Two more slots look like mapping bugs until you check the vocabularies:

| catalog states | EnVar wants | why it is left empty |
|---|---|---|
| `qudt:dataType` = `double` | `value_data_type` (required) ∈ `continuous_numeric`, `categorical`, `binary_flag`, `count`, `event_marker` | `double` is a *storage* type; the enum is *measurement semantics*. A double can hold a count or a binary flag. Filling it is inference. |
| `dct:rights` = `Public Domain` | `source_license_spdx` (recommended) | "Public Domain" is not an SPDX identifier. `CC0-1.0` would be a guess about which public-domain instrument applies. |

Both are cases where the catalog *does* state something and EnVar *does* have a
slot, yet no honest mapping exists — the gap is in the vocabulary binding, not
in the presence of data.

### 4. `version` does not mean the dataset's version

The JSON-LD `version` (`"2026-08-23"`) and DCAT `gdsc:version`
(`"2026-08-23T15:55:26Z"`) are both timestamps of the catalog record. The
dataset version — `v1` — appears only inside title strings, never as a field of
its own. So `source_dataset_version`, a required EnVar slot, has no reliable
source despite the catalog appearing to carry two version fields.

### 5. The three files overlap heavily, and JSON-LD is not a superset

The ETL and DCAT files duplicate each other in places: the upstream SEDAC URL is
both `etl.source` and `dcat:downloadURL`, the per-variable `attributes` block is
identical in both, and so is the bbox.

The JSON-LD is the richest file but not a superset. The per-year Gaia concept
ids (finding 2), `local_epsg` and `gdsc:analyticConformsTo` (finding 7), and the
ETL pseudo-code (finding 1) appear only in the other two. Any model of the
catalog has to read all three files; Bryan's branch is right to define
`DCATMetaData` / `ETLMetaData` / `JSONLDMetaData` as separate classes.

### 6. An EnVar-side gap, not a Gaia one

`source_native_format` is an enum of `netcdf4_cf`, `hdf5`, `geotiff`, `grib1`,
`grib2`, `csv_station_observations`, `zarr`, `parquet`. The catalog says `shp`.
The format enum covers raster and array formats but no vector formats, so any
vector entry in the catalog will fail the same way. This one is a fix for the
micro-schema, not for Gaia.

### 7. The CRS is stated five times, under names that do not say what each one is

| where | value |
|---|---|
| `meta_dcat_*` → `dct:conformsTo` | `EPSG:4326` |
| `meta_dcat_*` → `gdsc:analyticConformsTo` | `EPSG:3857` |
| `meta_json-ld_*` → `additionalProperty[Spatial_reference_system]` | `https://epsg.io/4326` |
| `meta_etl_*` → `epsg` | `EPSG:4326` |
| `meta_etl_*` → `local_epsg` | `EPSG:3857` |

These do not disagree. `gdsc:analyticConformsTo` says what the 3857 values are:
the analytic projection, against 4326 as the storage CRS. But that is two
things under five names, and only one of them says which is which. The
transform takes `dct:conformsTo` as the storage CRS — a judgement call a
consumer should not have to make.

The bbox is the control case: it is stated three times (JSON-LD
`spatialCoverage[].geo.polygon`, `dcat:bbox`, ETL `extent`), and all three give
the same coordinates.

Redundant metadata that mostly agrees is worse than a single field: it reads as
corroboration while quietly carrying a disagreement — or, as here, an
unlabelled distinction that looks like one.

## Status and limits

- One catalog entry (`global_pm25_concentration_1998_2016`), chosen because it
  is the running example in the D2.2 audit document. The coverage numbers are
  from this entry; they are indicative, not a catalog-wide measurement. A sweep
  over all 15 datastore entries would be needed to claim general figures.
  Within this entry all 19 records share one fill signature, so the table
  describes every record rather than just the first. `coverage_report.py`
  verifies that and warns when it stops holding — which it will in a sweep, as
  soon as entries with different metadata completeness are mixed.
- The source schema here is a stand-in. The authoritative model belongs in
  `linkml-ohdsi-gis-extension-envar` (branch `gaia_catalog_addition`). That
  branch currently lists its Gaia slots without defining them and leaves
  "How to model nested variables?" open — the flattening in `prepare_gaia.py` is
  one concrete answer to that question.
- Only `variableMeasured` entries carrying a `propertyID` become records (19 of
  28). The rest are geometry and label columns. `propertyID` is a proxy for
  "is a measured exposure"; the catalog has no explicit marker.
