---
name: envar-amadeus-curator
description: >
  Curates EnVar (linkml-microschemas-envar) EnvironmentalExposureRecord
  sidecar YAML files from an amadeus extraction run_manifest.json under
  examples/amadeus/datasets/*/. Use this skill whenever the user asks to
  "curate a sidecar", "generate/regenerate an envar sidecar", "run the
  amadeus curator", mentions a run_manifest.json needing a sidecar, asks
  to fix/repair a BLOCKED or invalid EnVar sidecar, or wants to add a new
  amadeus dataset to examples/amadeus/. Also use it proactively if you
  notice a dataset folder under examples/amadeus/datasets/ has an
  outputs/<tree>/run_manifest.json but no outputs/<tree>/envar/sidecar.yaml, or has a
  sidecar that predates a schema change. Do NOT use this for the
  unrelated examples/heat/amadeus/ pipeline — that folder has its own
  hand-written translate step and is intentionally left alone.
---

# EnVar Amadeus Curator

Each dataset has TWO parallel output trees under `outputs/`:
`outputs/synthetic/` (written by `run.py`, Python, offline placeholder
data) and `outputs/real/` (written by `amadeus_extract.R`, real amadeus).
They have identical internal shape. Below, `<tree>` means whichever one
you're curating against — check `run_manifest.json`'s `execution_mode`
field to confirm which tree a given manifest belongs to before assuming.
Default to `synthetic/` unless the person specifies otherwise or you can
see `real/` actually has content (it starts empty).

Turns a deterministic `run_manifest.json` (facts an R/Python extraction
script can state with zero interpretation) into a schema-valid
`EnvironmentalExposureRecord` sidecar YAML — by reading the schema fresh
each time, not from memory. This is the point of doing this with an agent
instead of a hardcoded mapping script: `linkml-microschemas-envar` changes
regularly (new slots, tier changes, enum edits), and a script goes stale
the moment it does. You don't.

**Golden rule: never invent a value.** Every field in the sidecar must
trace to exactly one of three sources, and `curation_log.md` must say
which:
1. **`manifest`** — copied or trivially derived from `run_manifest.json`.
2. **`looked-up: <url or doc>`** — from provider documentation you
   actually fetched (web_search / web_fetch), with the source recorded.
3. **`flagged-unknown`** — you could not determine it. Set the slot to
   `null` and populate its `*_missing_reason` sibling if one exists
   (schema convention — check `envar_common.yaml`'s
   `MissingValueReasonEnum` first). If no `*_missing_reason` sibling
   exists and the slot is Core, this is a **blocking gap** — say so
   plainly rather than filling in a plausible-looking guess. If the slot
   structurally doesn't fit the data you have, pick the least-wrong
   defensible value AND say so plainly in `curation_log.md` — do not
   silently paper over a structural mismatch.

## Procedure

### 1. Load the manifest

Read `datasets/<name>/outputs/run_manifest.json`. This tells you the
dataset short code, variable name, tool version, file hashes, row counts,
extraction window, and whatever amadeus/terra reported about the raster
(`raster_reported.resolution_m`, `.crs`, native units). Treat every other
field as unknown until you resolve it in step 3.

### 2. Get the current schema — do not use a cached mental model of it

The schema lives in the sibling repo `linkml-microschemas-envar`, not in
this repo. Before drafting anything:

```bash
# from the envar repo root
if [ -d ../linkml-microschemas-envar ]; then
  git -C ../linkml-microschemas-envar pull --ff-only
else
  git clone --depth 1 https://github.com/monarch-initiative/linkml-microschemas-envar.git ../linkml-microschemas-envar
fi
pip install --break-system-packages -e ../linkml-microschemas-envar -q
pip install --break-system-packages linkml -q   # needed for full jsonschema validation, not just completeness scoring
```

Then actually read the current slot definitions and tier annotations —
don't assume they match what's documented in this SKILL.md (they will
drift; that's the entire premise of doing this agentically):

```bash
ls ../linkml-microschemas-envar/src/linkml_microschemas_envar/schema/
```

Read at minimum `envar_record.yaml` (the top-level class + which blocks
are required), `envar_variable.yaml`, `envar_spatial.yaml`,
`envar_temporal.yaml`, `envar_source.yaml`, `envar_toolrun.yaml`, and
`envar_common.yaml` (shared enums, including `MissingValueReasonEnum`).
Skim `envar_layout.yaml`, `envar_linkage.yaml`, `envar_model.yaml`,
`envar_uncertainty.yaml`, `envar_health_layer.yaml` for the blocks your
dataset touches. If the variable is a derived heat metric, also read
`envar_heat_metric.yaml`.

Look at `examples/scenarios/standards/amadeus_gridmet_tmmx.yaml` and
`examples/daymet_tmax_phoenix_2022_07_19.yaml` in that repo as field-shape
references — they show the *style* (nesting, string formats, comment
conventions) but never copy their *values*; every value in your output
must come from this run's manifest or a real lookup.

### 3. Resolve everything the manifest doesn't cover

For each Core and Recommended slot not already filled from the manifest,
resolve it by web-fetching the provider's own documentation (PRISM
Climate Group, NOAA PSL for NARR, EPA AQS technical docs — whichever
applies). Typical lookups needed every
time: `source_dataset_doi`, `source_dataset_version`,
`source_producer_institution`, `source_license_spdx`,
`source_citation_apa`, `day_boundary_convention`,
`temporal_coverage_start/end`, `standard_name` (CF where one exists),
`concept_status` (almost always `gap` for environmental variables today —
check OHDSI Athena if unsure), `value_data_type`.

Do not reuse a value you looked up for a different dataset without
re-verifying it applies (e.g. day-boundary convention is
product-specific, not org-specific).

### 4. Draft the sidecar

Write `datasets/<name>/outputs/<tree>/envar/sidecar.yaml` conforming to
`EnvironmentalExposureRecord`. Use the field-shape references from step 2
for style. `data_layout` describes *this run's* companion CSV columns —
read them from `run_manifest.json`'s `output_columns`, don't assume.

### 5. Validate — with the real checker, not by eye

```bash
python examples/amadeus/curator/validate.py datasets/<name>/outputs/<tree>/envar/sidecar.yaml
```

This wraps `linkml_microschemas_envar.checker`, the exact tool that
scores every example on the schema's own docs site. Save its output to
`outputs/<tree>/envar/validation_report.txt`.

### 6. Repair loop

If BLOCKED or invalid: fix the reported slots and re-validate. Up to 3
attempts. If still blocked after 3 attempts, stop — write the remaining
blockers plainly into `curation_log.md` under a `## Still blocking`
heading rather than looping forever or forcing a fake value through.

### 7. Write the curation log

`datasets/<name>/outputs/<tree>/envar/curation_log.md` — one line per non-trivial
field: `slot_name: source (manifest | looked-up: <cite> | flagged-unknown)`.
This is the audit trail; a human should be able to check any single field
against its stated source in under a minute.

### 8. Human checkpoint

Stop and report to the user: final readiness %, what's still
missing/flagged, and anything you logged as a known-issue candidate. Do
not commit or consider this "done" — DOI/license/citation claims in
particular need human sign-off before they go anywhere near a
publication-facing repo.

## Known schema friction to watch for

- **Point-network products (AQS/IMPROVE) vs `native_spatial_resolution_m`**:
  this Core slot assumes a grid cell size. A monitoring-station network has
  no natural cell size. Don't invent one — see
  the dataset's `curation_log.md` for the treatment used so far, and
  note any new case there too.
- **`day_boundary_convention` is per-product, not per-org**: two datasets
  from the same producer can use different conventions. Always verify per
  dataset, never inherit from a sibling sidecar.
- **`concept_status` and `value_data_type`** are the two slots that
  blocked the existing `amadeus_gridmet_tmmx.yaml` example — they're easy
  to forget because amadeus itself has no equivalent concept. Set them
  explicitly every time; don't let them fall through.
- **`tool_run.run_arguments` needs a real, checked call shape, not a
  plausible-looking guess.** A past pass fabricated a single
  `calculate_covariates(dataset, locs=..., variables=..., date_start=...,
  date_end=...)` call for every dataset, which does not match amadeus's
  actual API (`download_data()` -> `process_covariates()` ->
  `calculate_covariates()`, three separate calls, confirmed against the
  package's own `download_data` vignette). This field feels like a
  low-stakes implementation detail; it isn't — treat it with the same
  "looked-up, cited" discipline as any other field, not as a template to
  fill in from a plausible pattern.
- **Never round-trip an already-curated sidecar through a generic
  `yaml.safe_load()` + `yaml.safe_dump()`** to make a small edit — PyYAML
  drops all comments, silently destroying the header and inline
  justification comments that make a sidecar auditable. Either edit the
  specific line(s) with targeted string replacement, or manually
  re-add every comment the round-trip would drop. (The
  `generate_*_variants.py` scripts are safe from this — they build a
  fresh file with their own header each time, they don't edit an
  existing curated file in place.)
