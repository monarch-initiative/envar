# Curation log — NARR relative humidity + wind speed

Curated 2026-09-02 by Claude, following `.claude/skills/envar-amadeus-curator/SKILL.md`.
Two sidecars from one extraction run (`sidecar_rhum.yaml`,
`sidecar_wind.yaml`), both pointing at the same companion CSV via
`data_layout.value_column`. Final validation: **both Core 33/33 ✓, valid,
72% readiness** on the first drafting pass (no repair loop needed this
time — the PRISM pass's mistakes, e.g. list-vs-string for
`exposure_model_known_biases`, were already applied here from the start).

## Facts shared by both records

- `native_spatial_resolution_m: 32000` — looked-up: NOAA PSL — "The NARR
  model uses the very high resolution NCEP Eta Model (32km/45 layer)"
  (https://psl.noaa.gov/data/gridded/data.narr.monolevel.html). Matches
  the schema's own worked example ("NARR ≈ 32000") almost exactly.
- `crs` (PROJ string) — **manifest-adjacent, not looked-up fresh**: taken
  verbatim from the `amadeus` package's own published README example
  output (the `weasd` NARR walkthrough at
  https://niehs.github.io/amadeus/, which prints
  `terra`'s reported CRS for a NARR raster). This is the one CRS value in
  this folder sourced directly from amadeus's own documented output
  rather than independently re-derived, since NARR's Lambert Conformal
  Conic projection has no single canonical EPSG code the way WGS84 does.
- `day_boundary_convention: utc_midnight` — looked-up: NCEI NARR page —
  "All times are in UTC" (https://www.ncei.noaa.gov/products/weather-climate-models/north-american-regional).
  Matches the schema's own stated convention ("NARR / ERA5 sub-daily are
  computed against this").
- `source_license_spdx: CC-BY-4.0` — looked-up: NOAA PSL dataset page —
  "This work is licensed under a Creative Commons Attribution 4.0
  International Licence. There are no restrictions for the use of data."
  **Clean SPDX match, unlike PRISM's case** — worth noting as the
  contrast: not every non-federal-in-the-strict-sense product needs a
  `LicenseRef-` workaround.
- `source_citation_apa` — looked-up: Mesinger et al. (2006), BAMS,
  doi:10.1175/BAMS-87-3-343 — the standard NARR citation per NOAA PSL's
  own citation guidance page.
- `source_dataset_doi` — flagged-unknown, `missing_reason:
  not_provided_by_source`: same situation as PRISM — the paper has a DOI
  (used in the citation), the continuously-served dataset itself does not.
- `source_dataset_version: current` — judgment-call, same convention used
  for PRISM and the existing gridMET example. **Caveat not fully
  resolved**: some sources describe NARR as no longer being actively
  extended past a certain date (superseded by newer reanalyses); this was
  not independently confirmed in this session, so "current" may be
  imprecise. Worth checking before treating this record as final.
- `temporal_resolution` / `temporal_aggregation_method: mean` —
  **judgment-call, not confirmed against amadeus's actual behavior**:
  NARR's native monolevel humidity/wind fields are 3-hourly instantaneous
  values; this record asserts a daily mean was computed to match the
  scenario's daily grain, following the same choice the schema's own
  ERA5-RH example makes (`temporal_aggregation_method: mean`). **This
  extraction script does not itself perform 3-hourly-to-daily
  aggregation** (the fixture already ships one row per day) — when this
  is run for real against amadeus's actual `calculate_covariates("narr",
  ...)` output, verify what aggregation amadeus actually applies and
  correct this field if it differs.
- `exposure_model_type: reanalysis` — schema enum; the schema's own
  description names NARR explicitly ("Data-assimilation reanalysis
  (NARR, ERA5)").

## rhum-specific
- `standard_name: CF:relative_humidity` — matches the schema's own ERA5 RH example.
- Everything else — `manifest` (variable name, hashes, row counts) or `schema` convention.

## wind-specific
- `standard_name: CF:wind_speed` — CF Conventions standard name registry
  includes `wind_speed` as a defined term; not independently re-fetched
  from the CF standard-name table in this session (moderate confidence).
- `wind_speed` itself is **not** an amadeus/NARR native variable — it's
  computed by this run's own `run.py` from `uwnd.10m`/`vwnd.10m` via
  `sqrt(u^2+v^2)`. This is stated explicitly in
  `exposure_model.exposure_model_inputs` rather than presented as if
  amadeus emitted wind_speed directly — an important distinction for
  reproducibility (the derivation step is outside amadeus, in this repo's
  own code).

## Still missing (Recommended, non-blocking)
Same shape as PRISM's list — `uncertainty` block contents,
`provenance_chain_steps`, `health_layer_linkage`, per-value uncertainty
columns, `spatial_extent_bbox`, `temporal_coverage_end`. Not fabricated
because amadeus's NARR path is not known to emit any of these.
