---
description: Curate or re-curate the NARR EnVar sidecars (30 by default, or one variable if given as an argument), then validate.
argument-hint: "[variable]  e.g. rhum, wind, air_2m, dswrf, cape ... — omit for all 30"
---

Follow `.claude/skills/envar-amadeus-curator/SKILL.md` for the full
curation procedure. This command scopes it to NARR.

**Dataset**: `examples/amadeus/datasets/narr/`
**Base sidecars** (hand-curated, full narrative logs): `outputs/synthetic/envar/sidecar_rhum.yaml`, `sidecar_wind.yaml`
**Variant generator** (the other 28): `examples/amadeus/curator/generate_narr_variants.py`
**Scope reminder**: unlike PRISM, amadeus does NOT bound NARR's variable
list — it's a pass-through to NOAA's naming. The current 30 are a
curated comprehensive subset, not amadeus's own boundary. See
`outputs/synthetic/envar/curation_log_extended.md`'s exclusion table before adding
a new variable — check whether it was deliberately excluded (and why)
before assuming it's simply missing.

If `$ARGUMENTS` names a variable already in scope:
1. If it's `rhum` or `wind` (the bases) — re-run full manual curation
   from SKILL.md step 2 onward.
2. Otherwise — update its entry in `generate_narr_variants.py`'s
   `VARIABLES` dict against the current schema/facts, regenerate just
   that one, validate it.

If `$ARGUMENTS` names a variable NOT currently in scope (e.g. one of the
excluded fields, or a NOAA monolevel field not yet considered):
1. Check `curation_log_extended.md`'s exclusion table first — if it's
   there, tell the user why it was excluded and ask whether to override
   that decision rather than silently adding it.
2. If genuinely new: confirm the short name against NOAA PSL's monolevel
   catalog (don't guess spelling/units), add a real entry to
   `VARIABLES` in `generate_narr_variants.py` with a properly sourced
   `standard_name`/units/aggregation (CF where one exists, `ENVAR:`
   mint otherwise — never fabricate a CF term that doesn't exist),
   regenerate, validate.

If `$ARGUMENTS` is empty — do the full dataset:
1. Re-curate `rhum` and `wind` per SKILL.md, from a fresh schema pull.
2. Run `python examples/amadeus/curator/generate_narr_variants.py` to
   regenerate the other 28.
3. Validate all 30:
   ```
   cd examples/amadeus
   ENVAR_OFFLINE=1 python curator/validate.py datasets/narr/outputs/synthetic/envar/sidecar_*.yaml
   ```
4. Report a summary table and flag anything newly BLOCKED.
5. Update the curation logs for whatever actually changed.

Never touch `examples/heat/amadeus/` — scoped to
`examples/amadeus/datasets/narr/` only.
