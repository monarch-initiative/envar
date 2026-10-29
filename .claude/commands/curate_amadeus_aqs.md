---
description: Curate or re-curate the AQS EnVar sidecars (5 NAAQS criteria pollutants by default, or one if given as an argument), then validate.
argument-hint: "[pollutant]  e.g. pm25, pm10, co, no2, so2 — omit for all 5"
---

Follow `.claude/skills/envar-amadeus-curator/SKILL.md` for the full
curation procedure. This command scopes it to AQS.

**Dataset**: `examples/amadeus/datasets/aqs/`
**Base sidecar** (hand-curated, full narrative log): `outputs/synthetic/envar/sidecar_pm25.yaml`
**Variant generator** (the other 4): `examples/amadeus/curator/generate_aqs_variants.py`
**Scope reminder**: originally PM2.5-only by explicit decision, later
expanded to the 5 NAAQS criteria pollutants (PM2.5, PM10, CO, NO2, SO2)
on request. amadeus's `download_aqs()` accepts an arbitrary EPA
`parameter_code` — it is NOT bounded to these 5 the way PRISM is bounded
to its 7. If `$ARGUMENTS` requests Ozone, Lead, or any other AQS
parameter, that's a further scope expansion (same generator-table
pattern) — confirm it's intentional before adding it, same as any other
scope change to this dataset.

If `$ARGUMENTS` names one of the 5 current pollutants:
1. If it's `pm25` (the base) — re-run full manual curation from
   SKILL.md step 2 onward.
2. Otherwise — update its entry in `generate_aqs_variants.py`'s
   `VARIABLES` dict against the current schema/facts, regenerate just
   that one, validate it.

If `$ARGUMENTS` names a pollutant NOT currently in scope:
1. Confirm the parameter code against EPA's own AQS documentation (AQS
   Concepts / AQS Basics docs) — don't guess the code or its averaging
   convention. CO/NO2/SO2's daily-summary statistic is a max-of-a-sub-daily-average,
   not a straightforward daily mean like PM2.5/PM10 — check which applies
   before assuming.
2. Add a properly sourced entry to `generate_aqs_variants.py`'s
   `VARIABLES` dict (parameter code, standard_name — CF where one exists,
   units, aggregation method), add the synthetic-value formula to
   `run.py`, regenerate the sidecar, validate.
3. Update `curation_log_extended.md`'s scope table and this command's
   `argument-hint`/scope reminder to include the new pollutant.

**Known open item — check every run**: amadeus's own docs say AQS "does
not expose AQS through `calculate_covariates()`," meaning every
sidecar's `tool_run.run_arguments` may use the wrong real call shape
(see `curation_log.md`). If you can find amadeus's actual
AQS-to-point-value workflow this run, correct it across all 5 sidecars.
If not, leave it flagged.

**Also re-check the two point-network judgment calls** logged in
`curation_log.md`
(`native_spatial_resolution_m: 0` as a forced placeholder, and
`day_boundary_convention: observation_dependent`) — these apply
identically to all 5 pollutants (same monitor network). If this run turns
up a real citable value for either, replace the placeholder across all 5
and note the source; otherwise leave them as documented workarounds.

**Steps (no argument — full dataset):**
1. Read `outputs/run_manifest.json` and pull the schema fresh (SKILL.md §2).
2. Re-curate `sidecar_pm25.yaml` if anything changed — otherwise confirm
   it's still current.
3. Run `python examples/amadeus/curator/generate_aqs_variants.py` to
   regenerate the other 4 from the refreshed base.
4. Validate all 5:
   `python examples/amadeus/curator/validate.py examples/amadeus/datasets/aqs/outputs/synthetic/envar/sidecar_*.yaml`
5. Fix and repeat per SKILL.md's repair loop until all 5 pass.
6. Update `curation_log.md` / `curation_log_extended.md` for whatever
   actually changed, and report a summary: readiness scores, whether
   either known-issue was resolved this run.

Never touch `examples/heat/amadeus/` — scoped to
`examples/amadeus/datasets/aqs/` only.
