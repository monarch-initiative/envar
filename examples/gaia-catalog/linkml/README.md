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

A GaiaCatalog entry fills **19 of 119** sidecar slots (**16%**). **15 required
slots have no source in the catalog**, and **3 of the 8 required composite
blocks come out entirely empty**.

```
block                   filled   empty   total   required unfilled
------------------------------------------------------------------
variable_identity            8      10      18   3
data_layout                  1      12      13   1
spatial_reference            3       9      12   3
temporal_reference           2       7       9   3
source_dataset               5      13      18   1
exposure_model               0      11      11   1  <-- entirely empty
linkage_method               0      21      21   1  <-- entirely empty
tool_run                     0      17      17   2  <-- entirely empty
------------------------------------------------------------------
TOTAL                       19     100     119   15
```

The output **does not validate** against the EnVar micro-schema. That is the
finding, not a defect — `linkml-validate` enumerates exactly which required
fields a catalog entry cannot supply.

`linkml-validate` reports 324 errors: 17 per record across 19 records, plus one
spurious `None is not of type 'object'`. That last one is a linkml-map output
quirk, not a finding — `map-data` terminates the YAML stream with a trailing
`---`, which parses as a 20th, empty document.

## Mapping rule

A target slot is populated **only where the catalog states the value**. Anything
requiring inference from prose, from a column-naming convention, or from
knowledge of a particular extraction run is deliberately left empty. Filling
those with plausible guesses would erase the measurement.

Two normalizations are allowed, because they are lossless restatements rather
than inferences: string→number casts on `minValue`/`maxValue` (the catalog
stores `"83"`, EnVar types it numeric), and reducing the bbox ring to four
bounds (the catalog's ring is axis-aligned and already labelled bbox).

## Files

| File | Role |
|---|---|
| `../fixtures/` | The real `OHDSI/gaiaCatalog` entry for `global_pm25_concentration_1998_2016`, vendored unmodified — all three metadata files |
| `gaia_catalog.source.yaml` | Source schema for a flattened catalog variable row (stands in for Bryan's `gaia_catalog_addition` branch) |
| `prepare_gaia.py` | Flattens the three metadata files into one row per measured variable |
| `gaia_to_envar_record.transform.yaml` | The trans-spec: `GaiaVariableRow` → `EnvironmentalExposureRecord` |
| `coverage_report.py` | Counts filled / empty / required-unfilled per composite block |

## Run

```bash
cd examples/gaia-catalog/linkml
ENVAR=<path>/linkml-microschemas-envar/src/linkml_microschemas_envar/schema
LM=linkml-map            # released 0.5.3 is sufficient

# 1. flatten the catalog entry to one row per measured variable
uv run --script prepare_gaia.py ../fixtures --out inputs/gaia_variable_rows.json

# 2. transform. NOTE: map-data needs a DIRECTORY containing a <SourceType>.json —
#    a single JSON file holding a list is passed through untransformed, silently.
mkdir -p indir && cp inputs/gaia_variable_rows.json indir/GaiaVariableRow.json
$LM map-data -T gaia_to_envar_record.transform.yaml \
  -s gaia_catalog.source.yaml --target-schema "$ENVAR/envar_record.yaml" \
  -o out/envar_records.yaml indir/

# 3. the gap, enumerated two ways
linkml-validate -s "$ENVAR/envar_record.yaml" -C EnvironmentalExposureRecord out/envar_records.yaml
uv run --script coverage_report.py out/envar_records.yaml "$ENVAR"
```

## Findings

### 1. Three required blocks are unfillable in principle, not by omission

`exposure_model`, `linkage_method` and `tool_run` come out empty — 49 slots
between them. This is not a catalog defect to be fixed by adding fields. A
catalog entry describes a *published dataset*; these blocks describe *what
someone did with it* — which model produced the surface, how it was joined to a
patient cohort, which container ran with which arguments over which inputs.
That information does not exist at catalog time.

**Implication for EnVar:** the sidecar cannot be generated from the catalog. It
must be emitted by the extraction tool at run time, with the catalog supplying
only the dataset-identity layer. This is the concrete baseline of required model
changes that D2.2's DoD asks for.

### 2. Time is modelled as column names

All 19 measured variables (`avpmu_1998` … `avpmu_2016`) share a single
`propertyID` — `2052499839`. The concept identifies the *variable kind*; the
year lives only in the column name and in per-variable `startDate`/`endDate`.
The catalog never states that the table is wide, so `data_layout.table_orientation`
is unfillable even though the entry plainly is wide.

### 3. `propertyID` and `unitCode` are overloaded across the catalog

Here `propertyID` is an OMOP concept id (`"2052499839"`) and `unitCode` is an
OMOP concept id for the unit (`"32964"`). In EnVar's own heat-scenario JSON-LD
fixture the same two fields hold a CF standard-name URL and a UCUM-ish code
(`"CEL"`). Same fields, incompatible meanings, no discriminator.

This connects the two halves of the audit: `2052499839` sits in the 2-billion
custom range, so the vocabulary-provenance problem documented in D2.2's
vocabulary section reappears *inside* the metadata layer. `units_ucum` is
required by EnVar and cannot be filled, because what the catalog offers is an
opaque concept id and free-text prose (`"micrograms/cubic meter"`).

### 4. `version` does not mean the dataset's version

The catalog's `version` (`"2026-08-23"`) is the catalog record's own timestamp.
The dataset version — `v1` — appears only inside the title string. So
`source_dataset_version`, a required EnVar slot, has no reliable source despite
the catalog appearing to carry a version field.

### 5. Things only the ETL file knows

`meta_json-ld_*` is the richest file but not a superset. The upstream source URL
— the actual provenance root, a SEDAC download — appears only in
`meta_etl_*.source`. Any model of the catalog has to read all three files;
Bryan's branch is right to define `DCATMetaData` / `ETLMetaData` / `JSONLDMetaData`
as separate classes.

### 6. An EnVar-side gap, not a Gaia one

`source_native_format` is an enum of `netcdf4_cf`, `hdf5`, `geotiff`, `grib1`,
`grib2`, `csv_station_observations`, `zarr`, `parquet`. The catalog says `shp`.
The micro-schema's format enum covers raster and array formats but no vector
formats, while a large share of the catalog is vector data. This one is a fix
for the micro-schema, not for Gaia.

## Status and limits

- One catalog entry (`global_pm25_concentration_1998_2016`), chosen because it
  is the running example in the D2.2 audit document. The coverage numbers are
  from this entry; they are indicative, not a catalog-wide measurement. A sweep
  over all 15 datastore entries would be needed to claim general figures.
- The source schema here is a stand-in. The authoritative model belongs in
  `linkml-ohdsi-gis-extension-envar` (branch `gaia_catalog_addition`). That
  branch currently lists its Gaia slots without defining them and leaves
  "How to model nested variables?" open — the flattening in `prepare_gaia.py` is
  one concrete answer to that question.
- Only `variableMeasured` entries carrying a `propertyID` become records (19 of
  28). The rest are geometry and label columns. `propertyID` is a proxy for
  "is a measured exposure"; the catalog has no explicit marker.
