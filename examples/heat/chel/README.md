# CHEL — extreme heat days on the H3 grid

The heat scenario's three patients, linked to **CHEL**, the CLAD Hex
Environmental Linkage that All of Us uses to attach environmental context to
participants. CHEL publishes CDC/ATSDR Environmental Justice Index (EJI)
variables re-expressed on the H3 resolution-3 grid (about 12,000 km² per
cell). Its 2024 release carries `E_NEHD`, the **annual mean number of extreme
heat days over 2018–2022**. That window is the heat cohort's observation
window, so it is the CHEL variable this scenario needs.

The linkage follows the hexagon route of the
[AMIA 2026 RWD workshop](https://github.com/rwdcollaborative/amia-2026-rwd-workshop).
The workshop gives every synthetic OMOP person an H3 res-3 hexagon through
their county (`staging/augment.py`, `build_location()`). Its hexagon notebook
stops one join short of CHEL. This example makes that join, by two routes, and
records each one in an EnVar sidecar:

| Route | Residence → hexagon | Effective resolution |
|---|---|---|
| `point` | the res-3 cell containing the residence coordinate (`h3.latlng_to_cell`) | H3 res-3 cell |
| `county` | residence → county FIPS (FCC Census Area API, 2020 blocks) → the one hexagon the workshop crosswalk assigns that county | county |

Both routes join CHEL on `h3_id`. CHEL's own `hex_id` is local to CLAD, and the
workshop doesn't have it.

## Running

```bash
# from examples/heat/
just chel            # fetch pinned inputs, link, write data + one sidecar per route
```

Inputs are fetched at pinned commits: `cladteam/CHEL@4dd219e`
(`data/CHEL_hex3_2024.csv`) and `rwdcollaborative/amia-2026-rwd-workshop@cf3a05c`
(`staging/data/h3res3_countyfips_cw.csv`). The county comes from the live FCC
API. Fetched files are cached in `.cache/`, and `ENVAR_OFFLINE=1` re-runs from
that cache. The cache is not committed: neither upstream repository declares a
licence, so this repo doesn't redistribute their files.

## Result

| person | county | `point` hexagon | `E_NEHD` | `county` hexagon | `E_NEHD` |
|---|---|---|---|---|---|
| 91204 (Phoenix) | Maricopa, 04013 | `8329b6fffffffff` | **17.15 d** | `8348e9fffffffff` | **15.61 d** |
| 91205 (Phoenix) | Maricopa, 04013 | `8329b6fffffffff` | **17.15 d** | `8348e9fffffffff` | **15.61 d** |
| 91206 (Tucson) | Pima, 04019 | `8348e8fffffffff` | 15.41 d | `8348e8fffffffff` | 15.41 d |

**The two Phoenix patients get a different hexagon depending on the route.**
Their residences sit in the cell CHEL indexes as `hex_id` 88, which holds 2.4
million people and has 17.15 extreme heat days per year (national percentile
0.75). The workshop crosswalk assigns all of Maricopa County to a different
cell, with 15.61 days (percentile 0.59). That is 1.54 fewer heat days a year
for the same address, and the only difference is the linkage rule. For Tucson,
the county's assigned hexagon is the residence's own, so both routes agree.

In `external_exposure.csv` the two routes' rows are identical apart from the
value and `exposure_source_value`. Only the sidecar that `exposure_source_value`
points to says how the value was linked (`linkage.strategy`,
`linkage.effective_spatial_resolution`, `linkage.assignment_rule`).

## What the sidecars have to say that the schema can't

The sidecars use the heat scenario's sidecar shape. Checked against the EnVar
micro-schema pinned in this repo's `uv.lock` (`linkml-microschemas-envar@dcdb549`),
these are the places where they can't use a schema value. Every one is a gap,
not a bug:

- **No county-to-hexagon linkage strategy.** `LinkageStrategyEnum` has
  `area_membership_residence_in_polygon` (the `point` route), but nothing for
  "the residence's county, then the hexagon assigned to that county". That
  hexagon need not contain the residence, so the sidecar writes
  `county_assigned_h3_hexagon`, which is not in the enum.
- **No plain tabular format.** `SourceNativeFormatEnum` has
  `csv_station_observations` but nothing for a gridded table published as CSV,
  so the sidecar writes `CSV`.
- **No CF standard name, day boundary or model type for the variable.** EJI
  documents `E_NEHD` as "the annual mean number of extreme heat days, using
  data from 2018–2022" from the CDC National Environmental Public Health
  Tracking Network. It doesn't give the threshold, the day boundary or the
  model behind it. The sidecar leaves the CF standard name,
  `day_boundary_convention` and `exposure_model_type` empty rather than
  guessing.
- **No home for an H3 resolution.** `native_spatial_resolution_m` is a float in
  metres. The sidecar states "H3 resolution 3" in the free-text descriptor.

Five more things the sidecars record have no slot at all:

- **Effective resolution vs. grid resolution.** On the `county` route the
  value is a hexagon's, but the spatial precision is the county's.
- **The undocumented assignment rule.** The workshop repo doesn't say how each
  county's one hexagon was chosen.
- **Which kind of null the sentinel is.** CHEL writes `-999` (and `-999.0`)
  for "no data". The schema's `missing_value_sentinel` can hold the value, but
  nothing says which null kind a dataset-level sentinel stands for. CHEL's
  `Documentation.md` §4.3.3 distinguishes structural nulls, derived nulls and
  true zeros, but doesn't say which one `-999` encodes either. The pipeline
  maps it to NULL and says so.
- **Release selection.** The CHEL README's linkage example assigns a release
  by enrollment year: 2015–2018 → CHEL 2022, 2019–2022 → CHEL 2024. Patients
  91204 and 91205 start their observation period in 2018, so that rule would
  send them to CHEL 2022, **which has no extreme heat days**. This pipeline
  picks the release per variable instead, and the sidecar records both the
  choice and who it affects.
- **Producer-stage aggregation.** CHEL's tract-to-hexagon operator for
  `E_NEHD` is inferred, not stated. `Documentation.md` §2.6 says climate inputs
  use area-weighted or intersection-based aggregation "depending on source
  format". The sidecar uses `area_weighted_polygon_mean` and explains the
  inference in a note.

## Layout

```
chel/
├── run.py                              link + emit (PEP 723, uv run --script)
├── outputs/
│   ├── chel_nehd_point.csv             person × hexagon × value, point route
│   ├── chel_nehd_county.csv            person × hexagon × value, county route
│   ├── external_exposure.csv           OMOP shape (CONTRACT.md); exposure_source_value → sidecar
│   ├── run_manifest.json               pinned inputs, sha256s, match counts
│   └── envar/chel_nehd_{point,county}.provenance.yaml   EnVar sidecars
└── .cache/                             fetched upstream files (gitignored)
```
