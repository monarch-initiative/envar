#!/usr/bin/env python3
"""generate_narr_variants.py — generate sidecars for 28 additional NARR
monolevel variables, reusing the curated/validated rhum sidecar as the
shared base (same source_dataset/spatial_reference/temporal_reference
day-boundary-convention/CRS/license facts -- all genuinely shared, one
run, one product).

VARIABLES table below encodes per-variable facts gathered from NOAA
PSL's monolevel documentation (short names confirmed against
https://psl.noaa.gov/data/gridded/data.narr.monolevel.html) and CF
Standard Names (https://cfconventions.org/standard-names.html) where a
match exists; ENVAR: mint used where CF has no defined term, following
the same convention already used elsewhere in this schema (e.g. Heat
Index, WBGT). This is a generation SCRIPT for this one batch, not a
permanent schema-mapping tool.

Deliberately EXCLUDED from this batch (see this dataset's README):
rcq, rcs, rcsol, rct (radar/satellite composite QC fields, undocumented
beyond short codes on the public page -- could not responsibly assign
standard_name/units without fabricating meaning), bmixl.hl1, mconv.hl1,
pottmp.hl1 (hybrid-level-1 boundary-layer research fields, no standard
health-exposure use), hlcy, lftx4, cdcon, cdlyr, mcdc, hcdc, lcdc, mslet,
pres.tropo, pottmp.sfc, mstav, cnwat, bgrun, ssrun, snom, snohf, acpcp
(lower relevance / redundant with an already-curated variable -- see
README for the full accounting).
"""
import copy
from pathlib import Path

import yaml

HERE = Path(__file__).parent
DATASET_DIR = HERE.parent / "datasets" / "narr"
SOURCE_MODE = "synthetic"
BASE_SIDECAR = DATASET_DIR / "outputs" / SOURCE_MODE / "envar" / "sidecar_rhum.yaml"

# fixture_col_name: dict(narr_short_name, label, standard_name, units_ucum,
#   agg (mean/sum/maximum/minimum), value_data_type, vmin, vmax)
VARIABLES = {
    "air_2m": dict(narr_name="air.2m", label="daily mean air temperature at 2 m",
                   standard_name="CF:air_temperature", units_ucum="Cel", agg="mean",
                   vmin=-50, vmax=55),
    "dpt_2m": dict(narr_name="dpt.2m", label="daily mean dew point temperature at 2 m",
                   standard_name="CF:dew_point_temperature", units_ucum="Cel", agg="mean",
                   vmin=-50, vmax=40),
    "pres_sfc": dict(narr_name="pres.sfc", label="daily mean surface air pressure",
                      standard_name="CF:surface_air_pressure", units_ucum="Pa", agg="mean",
                      vmin=50000, vmax=108000),
    "apcp": dict(narr_name="apcp", label="daily total precipitation",
                 standard_name="CF:precipitation_amount", units_ucum="mm", agg="sum",
                 vmin=0, vmax=500),
    "prate": dict(narr_name="prate", label="daily mean precipitation rate",
                  standard_name="CF:precipitation_flux", units_ucum="kg/(m2.s)", agg="mean",
                  vmin=0, vmax=0.01),
    "crain": dict(narr_name="crain", label="categorical rain flag (daily any-rain indicator)",
                  standard_name="ENVAR:categorical_rain_flag", units_ucum="1",
                  agg="maximum", vmin=0, vmax=1, data_type="binary_flag"),
    "csnow": dict(narr_name="csnow", label="categorical snow flag (daily any-snow indicator)",
                  standard_name="ENVAR:categorical_snow_flag", units_ucum="1",
                  agg="maximum", vmin=0, vmax=1, data_type="binary_flag"),
    "cfrzr": dict(narr_name="cfrzr", label="categorical freezing rain flag",
                  standard_name="ENVAR:categorical_freezing_rain_flag", units_ucum="1",
                  agg="maximum", vmin=0, vmax=1, data_type="binary_flag"),
    "cicep": dict(narr_name="cicep", label="categorical ice pellets flag",
                  standard_name="ENVAR:categorical_ice_pellets_flag", units_ucum="1",
                  agg="maximum", vmin=0, vmax=1, data_type="binary_flag"),
    "weasd": dict(narr_name="weasd", label="daily mean water equivalent of accumulated snow depth",
                  standard_name="ENVAR:snow_water_equivalent", units_ucum="mm", agg="mean",
                  vmin=0, vmax=500),
    "snod": dict(narr_name="snod", label="daily mean snow depth",
                 standard_name="CF:surface_snow_thickness", units_ucum="m", agg="mean",
                 vmin=0, vmax=5),
    "snowc": dict(narr_name="snowc", label="daily mean snow cover fraction",
                  standard_name="CF:surface_snow_area_fraction", units_ucum="%", agg="mean",
                  vmin=0, vmax=100),
    "dswrf": dict(narr_name="dswrf", label="daily mean downward shortwave radiation flux",
                  standard_name="CF:surface_downwelling_shortwave_flux_in_air",
                  units_ucum="W/m2", agg="mean", vmin=0, vmax=450),
    "uswrf_sfc": dict(narr_name="uswrf.sfc", label="daily mean upward shortwave radiation flux at surface",
                       standard_name="CF:surface_upwelling_shortwave_flux_in_air",
                       units_ucum="W/m2", agg="mean", vmin=0, vmax=150),
    "dlwrf": dict(narr_name="dlwrf", label="daily mean downward longwave radiation flux",
                  standard_name="CF:surface_downwelling_longwave_flux_in_air",
                  units_ucum="W/m2", agg="mean", vmin=100, vmax=500),
    "ulwrf_sfc": dict(narr_name="ulwrf.sfc", label="daily mean upward longwave radiation flux at surface",
                       standard_name="CF:surface_upwelling_longwave_flux_in_air",
                       units_ucum="W/m2", agg="mean", vmin=200, vmax=650),
    "gflux": dict(narr_name="gflux", label="daily mean ground heat flux",
                  standard_name="CF:downward_heat_flux_in_soil", units_ucum="W/m2", agg="mean",
                  vmin=-150, vmax=200),
    "lhtfl": dict(narr_name="lhtfl", label="daily mean surface latent heat flux",
                  standard_name="CF:surface_upward_latent_heat_flux", units_ucum="W/m2",
                  agg="mean", vmin=-50, vmax=500),
    "shtfl": dict(narr_name="shtfl", label="daily mean surface sensible heat flux",
                  standard_name="CF:surface_upward_sensible_heat_flux", units_ucum="W/m2",
                  agg="mean", vmin=-50, vmax=600),
    "hpbl": dict(narr_name="hpbl", label="daily mean planetary boundary layer height",
                 standard_name="CF:atmosphere_boundary_layer_thickness", units_ucum="m",
                 agg="mean", vmin=0, vmax=5000),
    "tcdc": dict(narr_name="tcdc", label="daily mean total cloud cover",
                 standard_name="CF:cloud_area_fraction", units_ucum="%", agg="mean",
                 vmin=0, vmax=100),
    "pr_wtr": dict(narr_name="pr_wtr", label="daily mean precipitable water",
                   standard_name="CF:atmosphere_mass_content_of_water_vapor", units_ucum="kg/m2",
                   agg="mean", vmin=0, vmax=70),
    "cape": dict(narr_name="cape", label="daily mean convective available potential energy",
                 standard_name="CF:atmosphere_convective_available_potential_energy",
                 units_ucum="J/kg", agg="mean", vmin=0, vmax=6000),
    "cin": dict(narr_name="cin", label="daily mean convective inhibition",
                standard_name="ENVAR:convective_inhibition", units_ucum="J/kg", agg="mean",
                vmin=-1000, vmax=0),
    "veg": dict(narr_name="veg", label="daily mean vegetation fraction",
                standard_name="CF:vegetation_area_fraction", units_ucum="%", agg="mean",
                vmin=0, vmax=100),
    "albedo": dict(narr_name="albedo", label="daily mean surface albedo",
                   standard_name="CF:surface_albedo", units_ucum="%", agg="mean",
                   vmin=0, vmax=100),
    "evap": dict(narr_name="evap", label="daily total evaporation",
                 standard_name="ENVAR:total_evaporation_amount", units_ucum="mm", agg="sum",
                 vmin=0, vmax=30),
    "vis": dict(narr_name="vis", label="daily mean surface visibility",
                standard_name="CF:visibility_in_air", units_ucum="m", agg="mean",
                vmin=0, vmax=30000),
}


def main() -> None:
    base = yaml.safe_load(BASE_SIDECAR.read_text())

    for col, meta in VARIABLES.items():
        doc = copy.deepcopy(base)
        doc["provenance_id"] = f"01NARR{col.upper().replace('_','')}PHXDEMO01-narr-{col}"

        vi = doc["variable_identity"]
        vi["variable_name"] = meta["narr_name"]
        vi["variable_label"] = meta["label"]
        vi["standard_name"] = meta["standard_name"]
        if meta["standard_name"].startswith("CF:"):
            vi["cf_cell_methods"] = f"time: {meta['agg']}"
        else:
            vi.pop("cf_cell_methods", None)
        vi["units_ucum"] = meta["units_ucum"]
        vi.pop("units_display", None)
        vi["value_data_type"] = meta.get("data_type", "continuous_numeric")
        vi["value_range_plausible_min"] = meta["vmin"]
        vi["value_range_plausible_max"] = meta["vmax"]

        doc["data_layout"]["value_column"] = col
        doc["temporal_reference"]["temporal_aggregation_method"] = meta["agg"]

        out_path = DATASET_DIR / "outputs" / SOURCE_MODE / "envar" / f"sidecar_{col}.yaml"
        header = (
            f"# Amadeus -> NARR {meta['narr_name']} -- EnVar sidecar.\n"
            f"# Generated from the curated/validated rhum sidecar's shared base\n"
            f"# (same NARR product, same run, same spatial/temporal/source/\n"
            f"# exposure_model/linkage/tool_run facts) plus per-variable facts\n"
            f"# researched for this batch -- see\n"
            f"# curator/generate_narr_variants.py for the sourced deltas and\n"
            f"# curation_log.md for the shared-base sourcing and exclusions.\n"
        )
        with out_path.open("w") as fh:
            fh.write(header)
            yaml.safe_dump(doc, fh, sort_keys=False, default_flow_style=False, width=100)
        print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
