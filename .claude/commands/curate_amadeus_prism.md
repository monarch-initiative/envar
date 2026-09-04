---
description: Curate or re-curate all 7 PRISM EnVar sidecars (or one variable if given as an argument), then validate.
argument-hint: "[variable]  e.g. tmax, tmin, tmean, tdmean, ppt, vpdmin, vpdmax — omit for all 7"
---

Follow `.claude/skills/envar-amadeus-curator/SKILL.md` for the full
curation procedure (schema-fresh, cited lookups, validate-and-repair
loop, never invent a value). This command scopes that procedure to the
PRISM dataset specifically.

**Dataset**: `examples/amadeus/datasets/prism/`
**Base sidecar** (hand-curated, full narrative log): `outputs/synthetic/envar/sidecar_tmax.yaml`
**Variant generator** (the other 6, sharing the base's spatial/temporal/
source/license facts): `examples/amadeus/curator/generate_prism_variants.py`
**Full variable set** (amadeus's own bounded PRISM coverage — confirmed
against CRAN `amadeus.pdf`, not an arbitrary subset): `tmax`, `tmin`,
`tmean`, `tdmean`, `ppt`, `vpdmin`, `vpdmax`

If `$ARGUMENTS` names one of those 7 variables:
1. If it's `tmax` (the base) — re-run the full manual curation procedure
   from SKILL.md step 2 onward (pull schema fresh, re-verify looked-up
   facts, redraft, validate).
2. Otherwise — open `generate_prism_variants.py`, re-check/update that
   variable's entry in `VARIANTS` against the current schema and any new
   provider facts, then run just that one variant's generation and
   validation.
3. Update `outputs/synthetic/envar/curation_log.md` (if base) or
   `curation_log_extended.md` (if variant) with what changed and why.

If `$ARGUMENTS` is empty — do the full dataset:
1. Re-curate the base (`tmax`) per SKILL.md, from a fresh schema pull.
2. Run `python examples/amadeus/curator/generate_prism_variants.py` to
   regenerate the other 6 from the refreshed base.
3. Validate all 7:
   ```
   cd examples/amadeus
   ENVAR_OFFLINE=1 python curator/validate.py datasets/prism/outputs/synthetic/envar/sidecar_*.yaml
   ```
4. Report a short summary table (variable, Core score, readiness %) and
   flag anything newly BLOCKED or newly resolvable that wasn't before.
5. Update `curation_log.md` / `curation_log_extended.md` for whatever
   actually changed — don't rewrite entries that didn't change.

Never touch `examples/heat/amadeus/` — this command is scoped to
`examples/amadeus/datasets/prism/` only.
