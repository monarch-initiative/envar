# Curation log — PRISM tmax

Curated 2026-09-02 by Claude, following `.claude/skills/envar-amadeus-curator/SKILL.md`.
Schema checked out at `linkml-microschemas-envar` HEAD as of this date.
Final validation: **Core 33/33 ✓, valid, 74% readiness** (see `validation_report.txt`).

Legend: `manifest` = copied from `run_manifest.json`. `looked-up: <source>` =
fetched from provider documentation during this session, cited. `schema` =
required literal value dictated by the schema itself (e.g. an enum name).
`judgment-call` = a defensible choice where the schema's fixed vocabulary
doesn't have an exact match — flagged, not silently resolved.

## variable_identity
- `variable_name: tmax` — manifest
- `standard_name: CF:air_temperature` — schema convention (same CF term used by every other Tmax record in this schema's examples: gridMET, Daymet)
- `cf_cell_methods: "time: maximum"` — schema convention, matches `temporal_aggregation_method: maximum`
- `units_ucum: Cel` — looked-up: PRISM FAQ (https://prism.oregonstate.edu/faq/) — "temperature units are in degrees Celsius." No native_units_ucum/scale/offset needed: **unlike gridMET's Kelvin-packed THREDDS output, PRISM ships Tmax already in °C.**
- `concept_status: gap` — looked-up (by absence): no OMOP concept found for daily PRISM Tmax; consistent with every other Tmax scenario in this schema's own examples
- `value_data_type: continuous_numeric` — schema enum, unambiguous for a temperature value
- `value_range_plausible_min/max: -50/60` — schema convention, same bounds used in every other ambient-Tmax example in this repo

## spatial_reference
- `native_spatial_resolution_m: 4000` — looked-up: PRISM FAQ — "PRISM 4km resolution data has always been available for free to the public... The 800m versions... are available to users for a fee" (as of March 2025, 800m is also free, but amadeus's default download still targets the 4km product — **not independently re-verified against amadeus's source code in this session; flagged**)
- `crs: EPSG:4269` — looked-up, general knowledge cross-referenced against the `prism` R package's documented CRS (NAD83 geographic); **not verified against a primary PRISM technical document in this session — moderate confidence, not the same tier as the day-boundary or resolution facts below**
- `extraction_method: nearest_cell` — judgment-call: amadeus's own gridMET sidecar (`examples/scenarios/standards/amadeus_gridmet_tmmx.yaml`) declares `nearest_cell` for the same tool's default `calculate_covariates()` behavior; PRISM-specific default not independently verified, inferred by analogy to the sibling amadeus example
- `source_native_format: geotiff` — judgment-call: PRISM's FAQ states rasters are distributed as Cloud-Optimized GeoTIFF (COG) as of Oct 2025; the schema's `NativeFormatEnum` has no `geotiff_cog` value, so `geotiff` was chosen as the closest valid match. **Flagged in `curator/known-issues.md`.**

## temporal_reference
- `day_boundary_convention: ending_1200_gmt` — looked-up: Climate Data Guide (https://climatedataguide.ucar.edu/climate-data/prism-high-resolution-spatial-climate-data-united-states-maxmin-temp-dewpoint) — "A 'PRISM day' is defined as 1200 UTC-1200 UTC... uses a day-ending naming convention." **High confidence — the schema itself names PRISM as the canonical example for this exact enum value.**
- `temporal_coverage_start: 1981-01-01` — looked-up: PRISM Group FAQ / dataset description — daily AN81d coverage begins 1981-01-01
- `temporal_coverage_end` — flagged-unknown: PRISM is a live, continuously-updated product; no single "coverage end" date is stable enough to assert without re-verifying at curation time. Left absent (Recommended, non-blocking) rather than guessed.

## source_dataset
- `source_dataset_doi` — flagged-unknown, `missing_reason: not_provided_by_source`: PRISM's continuously-updated public dataset has no single dataset DOI (unlike Daymet). The *methodology paper* has a DOI (used in `source_citation_apa`), but that is a citation, not a dataset DOI — kept distinct per the schema's own distinction.
- `source_dataset_version: current` — judgment-call, same convention the existing gridMET example uses for a continuously-updated product
- `source_producer_institution` — looked-up: prism.oregonstate.edu / re3data.org record
- `source_citation_apa` — looked-up: Daly et al. 2008, IJC, https://doi.org/10.1002/joc.1688 (PRISM's own citation guidance points to this as the methods citation)
- `source_license_spdx: LicenseRef-PRISM-Terms-of-Use` — judgment-call: looked up PRISM's actual terms (https://prism.oregonstate.edu/terms/ — "All data... may be freely reproduced and distributed" with an attribution requirement). This is **not a clean SPDX match** (not CC0, not CC-BY — no share-alike/attribution-license formalism, just a plain-English permissive term). Used the `LicenseRef-` SPDX convention for non-standard licenses rather than picking the nearest-sounding real SPDX id, which would misrepresent the actual terms. **Flagged in known-issues.md.**
- `source_dataset_spatial_extent` — looked-up: CONUS, consistent across every PRISM source

## exposure_model
- `exposure_model_type: spatial_interpolation` — schema enum, directly justified: PRISM = "Parameter-elevation Regressions on Independent Slopes Model," i.e. a regression-based spatial interpolation of station data using elevation as a covariate — this is definitionally what the enum value describes
- `exposure_model_inputs` — looked-up: station networks + DEM, per every PRISM methodology description found
- `exposure_model_known_biases` — looked-up: mountainous/station-sparse degradation is the standard caveat in PRISM literature; not a specific risk for this scenario's Phoenix/Tucson locations (noted)

## linkage_method
- `linkage_strategy: point_extraction_at_residence` — matches the scenario (point residence coordinates, no buffer)
- `geocoding_precision_propagated: range` — manifest-adjacent: taken from the shared cohort file's own geocoding precision field (`range`), not re-derived
- `address_period_alignment: address_history_from_emr` — schema convention, matches sibling examples' handling of the same cohort

## tool_run
- `tool_name`, `tool_version`, `run_arguments`, `run_timestamp_utc`, hashes, row counts — all `manifest`
- `tool_description` — used to preserve the `execution_mode: synthetic_offline_fixture` fact from the manifest, since the strict schema's `ToolRun` class has **no `execution_mode` slot** (unlike the informal shorthand sidecar shape `examples/heat/amadeus/run.py` uses internally). This was the first validation failure hit — logged here so it's not lost if someone rewrites this record from scratch.

## Still missing (Recommended, non-blocking, left honest rather than guessed)
`bias_correction_applied`, `data_completeness_pct`, `exposure_model_cross_validation_r2`,
`health_layer_linkage` (+ children), `model_aggregate_uncertainty`, `null_semantics_column`,
`per_value_uncertainty_*`, `privacy_transformation*`, `provenance_chain_steps`,
`source_dataset_temporal_coverage`, `temporal_coverage_end`, `uncertainty` block contents,
`value_uncertainty_column`. None of these are things amadeus's PRISM path is known to emit;
filling them would mean inventing values PRISM's own pipeline doesn't produce.
