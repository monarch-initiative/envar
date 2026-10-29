# amadeus — multi-dataset EnVar curation (separate from examples/heat/amadeus)

This folder is **independent** of `examples/heat/amadeus/` — nothing here
reads, imports, or modifies anything under `examples/heat/`, except one
read-only file (see Input below). That folder's single gridMET pipeline
is left exactly as it is.

## What's here

| Dataset | amadeus fn suffix | Variables | Notes |
|---|---|---|---|
| PRISM | `_prism` | **All 7** amadeus supports: `tmax`, `tmin`, `tmean`, `tdmean`, `ppt`, `vpdmin`, `vpdmax` | amadeus's real, bounded PRISM coverage |
| NARR | `_narr` | **30 curated monolevel variables** (comprehensive subset — amadeus doesn't bound NARR's variable list) | Only dataset feeding a derived heat metric |
| AQS | `_aqs` | **5 NAAQS criteria pollutants**: PM2.5, PM10, CO, NO2, SO2 | Point-network structure, not a raster — see `curation_log.md` in its output folder |

**42 validated `EnvironmentalExposureRecord` sidecars total** (7 + 30 + 5),
all Core-complete, 71-74% readiness, zero validation failures.

## Why agentic curation

`examples/heat/amadeus/run.py` writes its own hand-shaped provenance YAML
directly in Python. That's fine for a fixed schema, but EnVar is
**actively under revision** upstream — a hardcoded field-mapping script
goes stale every time the schema changes. Instead, curation here is a
Claude Code Skill (`.claude/skills/envar-amadeus-curator/SKILL.md`) that
pulls the *current* schema fresh each time, looks up whatever a script
can't know (DOI, license, day-boundary convention), drafts the sidecar,
and validates against the schema's real completeness checker — repairing
until it passes or explicitly flagging what it can't resolve. Every field
traces to the manifest, a cited lookup, or a flagged unknown — never a
silent guess.

## Input

One shared, static file: `input/patient_locations.csv` — 3 patients,
converted once from `examples/heat/data/patients_example1.json`
(read-only; never modified, never re-read at run time). All 3 datasets
extract for the same people and the same 8-day window
(`2022-07-15` → `2022-07-22`), so every sidecar here is directly
comparable to the gridMET/Daymet sidecars already in `examples/heat/`.

## Layout

```text
amadeus/
├── README.md                       this file
├── input/
│   └── patient_locations.csv        the one shared input, see above
├── curator/
│   ├── validate.py                  wraps the real linkml_microschemas_envar checker
│   ├── generate_prism_variants.py   propagates a curated base sidecar to the other 6 PRISM variables
│   ├── generate_narr_variants.py    same, for NARR's other 28 variables
│   └── generate_aqs_variants.py     same, for AQS's other 4 pollutants
└── datasets/
    └── <prism|narr|aqs>/
        ├── run.py                  Python, OFFLINE/SYNTHETIC ONLY — no real online path
        ├── amadeus_extract.R       real R, real amadeus — the only real-data path
        └── outputs/
            ├── synthetic/           written by run.py
            │   ├── <name>_all_vars.csv    ONE wide file: all patients, all that
            │   │                           dataset's variables as columns
            │   ├── run_manifest.json      see Contract below
            │   └── envar/
            │       ├── sidecar_<var>.yaml      one per variable
            │       ├── curation_log.md          full narrative for the hand-curated base
            │       ├── curation_log_extended.md table-form sourcing for the generated variants
            │       └── validation_report*.txt
            └── real/                written by amadeus_extract.R — empty until someone runs it
```

Most variables per dataset are not hand-curated individually — one base
variable (`tmax`/`rhum`/`pm25`) is curated following `SKILL.md` in full,
then `curator/generate_<name>_variants.py` propagates its shared facts
(CRS, license, extraction method) to the rest, varying only the
per-variable deltas (units, standard name, aggregation method).

## Contract: what `run_manifest.json` may state as fact

This is the boundary between the deterministic script and the agentic
curator. The manifest may contain **only** things the extraction script
can know without interpretation — no schema vocabulary, no enum values,
no judgment calls (DOI, license, citation, day-boundary convention,
target concept status, plausible value ranges — none of that belongs
here; it's the curator's job).

```jsonc
{
  "dataset_short_code": "prism",
  "variable_name": ["tmax", "tmin", "..."],  // ALL of this dataset's curated variables
  "tool_name": "amadeus",
  "tool_version": "2.0.2",
  "execution_mode": "real_amadeus" | "synthetic_offline_fixture",
  "run_timestamp_utc": "2026-...Z",
  // Real amadeus is 3 functions: download_data() -> process_covariates()
  // -> calculate_covariates(), looped per variable -- NOT one combined call.
  "r_call": "...",
  "input_file": "../../input/patient_locations.csv",
  "input_file_sha256": "...",
  "output_file": "outputs/synthetic/prism_all_vars.csv",  // one wide file, all variables as columns
  "output_file_sha256": "...",
  "output_row_count": 24,
  "output_columns": ["person_id", "date", "lat", "lon", "tmax", "..."],
  "extraction_window_start": "2022-07-15",
  "extraction_window_end": "2022-07-22",
  // amadeus/terra-reported facts (resolution, crs) when actually available --
  // omit (don't guess) anything not actually reported.
  "raster_reported": {"resolution_m": null, "crs": null, "native_units_as_stored": null}
}
```

---

## Running it

```bash
# ── Setup (once) ──────────────────────────────────────────
git clone https://github.com/monarch-initiative/envar.git
cd envar
git clone https://github.com/monarch-initiative/linkml-microschemas-envar.git ..
pip install -e ../linkml-microschemas-envar
pip install linkml pyyaml

# ── Scenario 1: Python, synthetic (no network, no setup) ─────
# writes to outputs/synthetic/
cd examples/amadeus/datasets/prism && python run.py && cd -
cd examples/amadeus/datasets/narr  && python run.py && cd -
cd examples/amadeus/datasets/aqs   && python run.py && cd -
# There is no Python "online" scenario -- an earlier PRISM direct-API
# path was removed because it bypassed amadeus entirely. Real data only
# comes from R (Scenario 2).

# ── Scenario 2: R, real amadeus (no Docker, no credentials) ──
# writes to outputs/real/
R -e 'install.packages(c("amadeus","jsonlite","digest","sf"))'   # or: just install-r-deps
cd examples/amadeus/datasets/prism && Rscript amadeus_extract.R && cd -
cd examples/amadeus/datasets/narr  && Rscript amadeus_extract.R && cd -
cd examples/amadeus/datasets/aqs   && Rscript amadeus_extract.R && cd -

# ── Curation (Claude Code — regenerate/re-map sidecars) ──────
# defaults to outputs/synthetic/ unless you tell it real/ has content
/curate_amadeus_prism            # all 7
/curate_amadeus_prism vpdmax     # one variable
/curate_amadeus_narr             # all 30
/curate_amadeus_narr air_2m      # one variable
/curate_amadeus_aqs              # all 5
/curate_amadeus_aqs no2          # one pollutant

# ── Curation (manual, no Claude Code) ─────────────────────────
# each script's SOURCE_MODE variable (top of file) picks synthetic|real —
# defaults to "synthetic"; edit it to point at outputs/real/ instead
cd examples/amadeus/curator
python generate_prism_variants.py   # regenerate 6 from sidecar_tmax.yaml
python generate_narr_variants.py    # regenerate 28 from sidecar_rhum.yaml
python generate_aqs_variants.py     # regenerate 4 from sidecar_pm25.yaml

# ── Validation ────────────────────────────────────────────────
cd examples/amadeus
python curator/validate.py datasets/prism/outputs/synthetic/envar/sidecar_tmax.yaml   # one file
python curator/validate.py datasets/prism/outputs/synthetic/envar/sidecar_*.yaml      # one dataset
python curator/validate.py $(find datasets -name "sidecar*.yaml")                     # everything (42, both trees)

# ── Add a participant ─────────────────────────────────────────
# edit: examples/amadeus/input/patient_locations.csv (add a row)
# then rerun any/all of Scenario 1/2 above — picked up automatically

# ── Add a variable to an existing dataset ─────────────────────
# 1. edit run.py                              -> add var + its synthetic-value formula
# 2. edit amadeus_extract.R                   -> add var to its var-list constant
# 3. edit curator/generate_<name>_variants.py -> add entry to VARIABLES/VARIANTS dict
# 4. rerun: python run.py && python curator/generate_<name>_variants.py
# 5. validate

# ── Add a new dataset ──────────────────────────────────────────
mkdir -p examples/amadeus/datasets/<name>/outputs/{synthetic/envar,real/envar}
# copy an existing run.py + amadeus_extract.R as templates, adapt --
# both read ../../input/patient_locations.csv, no per-dataset input needed
# hand-curate one base sidecar (SKILL.md), then optionally write
# curator/generate_<name>_variants.py for additional variables
```

**When the schema changes upstream**: nothing here needs manual
updating — `curator/validate.py` and the Claude Code Skill both pull the
current schema automatically on every run. Just re-validate everything
(`find datasets -name "sidecar*.yaml"` above) to see what newly fails,
then re-curate anything BLOCKED.

**R confidence differs by dataset** — I have not run any of the 3
`amadeus_extract.R` scripts (no R interpreter reachable in the sandbox
that built this), so treat them as carefully-written-but-untested:
- **NARR**: highest confidence — reproduces the exact call pattern amadeus's
  own vignette demonstrated, just looped over 30 variables instead of 1.
- **PRISM**: the 3-function pattern is followed by analogy; PRISM's exact
  `download_data()` argument shape wasn't independently confirmed.
- **AQS**: lowest confidence, flagged in the script's own header — amadeus
  only confirms the *download* step; the nearest-monitor point extraction
  is hand-written R against EPA's public file format, not verified
  against what amadeus actually writes to disk.

If you run one of these and hit an error, that's expected on the first
pass — please report back what broke so it can be corrected with a real
result instead of continued guessing.

## Honesty about what actually ran

This sandbox's network is limited to package registries (GitHub, PyPI,
npm) — no route to PRISM/NOAA/EPA's data services, and no CRAN mirror to
install the R `amadeus` package. So:

- **The schema and its checker are real.** `linkml-microschemas-envar` was
  cloned and installed here, and `curator/validate.py` runs the actual
  `envar-check` tool — the same one that scored the existing examples.
- **Every dataset's `outputs/synthetic/*.csv` is generated on the fly**
  by `run.py` from a fixed formula (see each script) — physically
  plausible for Phoenix/Tucson AZ, July 2022, but not real provider
  output. Deterministic (same values every run), not random.
- **`outputs/real/` is empty** until someone runs `amadeus_extract.R`
  with actual R + network access.
- **Every sidecar was independently validated** with the real checker,
  and every provenance/methodology fact was either taken from the
  manifest or looked up live with a cited source — see each dataset's
  `curation_log.md` for the full field-by-field trail, including
  judgment calls that couldn't be resolved to a single confirmed fact
  (flagged explicitly, not glossed over).
