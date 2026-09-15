# Curation log — EPA AQS PM2.5 (parameter 88101)

Curated 2026-09-02 by Claude, following `.claude/skills/envar-amadeus-curator/SKILL.md`.
Final validation: **Core 33/33 ✓, valid, 71% readiness**, no repair loop
needed (validated clean on first draft — enum values checked against the
schema before writing, not after).

This is the schema's own stated "generalisation check" — a non-heat
variable — and structurally the most different of the three new datasets:
a **point monitoring-station network**, not a raster grid. That
difference forced two real judgment calls, both pre-flagged in
`curator/known-issues.md` *before* this record was drafted.

## The two point-network judgment calls

- **`native_spatial_resolution_m: 0`** — This Core, numeric slot has no
  `*_missing_reason` sibling and no natural value for a station network
  (its own documentation examples all assume a grid cell size). Rather
  than invent a "typical monitor spacing" figure — I searched for one
  (EPA siting-criteria documents, EJ-monitor-distance literature) and
  found no single defensible number to cite — `0` was used as an explicit
  "point, no areal footprint" signal, with
  `native_spatial_resolution_descriptor: "point station network"`
  carrying the real semantics. **This is the least-wrong choice available
  in the current schema, not a resolved fit.** See known-issues.md item 3
  for the suggested schema fix (a `_missing_reason` sibling, or making the
  slot conditionally-core when `extraction_method: point_station_lookup`).
- **`day_boundary_convention: observation_dependent`** — AQS daily
  summaries aggregate sub-daily samples "at the monitor," but I could not
  confirm a single fixed day-boundary rule applied uniformly across every
  reporting monitor/state in the time available. `observation_dependent`
  is the schema's own designated value for exactly this situation ("Day
  boundary follows whatever the underlying observation network uses").
  Using `local_midnight` here would have been a guess dressed as a fact.

## Other fields
- `variable_name: pm25_88101`, `r_call`, hashes, row counts — `manifest`.
- `extraction_method: point_station_lookup` — schema enum, exact
  definitional match ("Direct lookup at a point station observation").
- `crs: EPSG:4269` — looked-up: a real AQS-daily-file processing example
  (University of Miami GDSC catalog entry) shows the standard ingestion
  command using `-s_srs EPSG:4269 -t_srs EPSG:4269` for AQS station
  coordinates (NAD83), giving higher confidence than PRISM's CRS guess.
- `source_native_format: csv_station_observations` — looked-up: EPA's own
  file-format documentation ("All files are comma separated variable
  (CSV) format") — exact enum match, no judgment call needed.
- `source_dataset_doi` — flagged-unknown, `not_provided_by_source`: AQS
  pre-generated files have no DOI; EPA's own citation guidance (see
  `source_citation_apa`) cites the database itself, not a versioned DOI.
- `source_citation_apa` — looked-up verbatim from EPA's own suggested
  citation text (Air Data Frequent Questions page).
- `source_license_spdx: public-domain-us-gov` — looked-up: US federal
  agency data, the schema's own named escape hatch for exactly this case
  — the cleanest license call of all three new datasets (no `LicenseRef-`
  workaround needed, unlike PRISM).
- `concept_status: gap` — consistent with the schema's own note that even
  its canonical PM2.5 scenario leaves this null-with-reason today.
- `linkage_method.linkage_max_distance_to_station_m: 50000` —
  judgment-call: a commonly-cited epidemiological convention (studies
  excluding person-days with no monitor within ~50 km) rather than an
  EPA-specified threshold. Logged as a modeling choice, not a fact from
  either amadeus or EPA.
- `exposure_model_type: direct_measurement` — schema enum; AQS monitors
  are physical instruments reporting measured (not modeled) concentrations
  — the one dataset among the three new ones that isn't a gridded model
  product, which is itself worth noting as a contrast for anyone
  comparing this record to `prism` (spatial_interpolation) or
  `narr` (reanalysis).

## Still missing (Recommended, non-blocking)
Same general shape as the other two datasets' gaps — `uncertainty` block,
`provenance_chain_steps`, `health_layer_linkage`, `temporal_coverage_start/end`,
per-value uncertainty columns. Not fabricated.
