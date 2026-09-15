#!/usr/bin/env python3
"""generate_aqs_variants.py — generate sidecars for 4 additional NAAQS
criteria pollutants (PM10, CO, NO2, SO2), reusing the curated/validated
PM2.5 sidecar as the shared base (same monitor network, same run, same
spatial/temporal/source/license facts -- all genuinely shared).

Parameter codes and averaging conventions confirmed against EPA's own
AQS documentation (AQS Concepts / AQS Basics training materials;
ace-methods-criteria-pollutants doc): PM10=81102 (24-hr mean, ug/m3),
CO=42101 (daily max 8-hr running avg, ppm), NO2=42602 (daily max 1-hr,
ppb), SO2=42401 (daily max 1-hr, ppb). This is a DELIBERATE scope
expansion beyond the original PM2.5-only decision, not amadeus's own
boundary -- amadeus's download_aqs() takes an arbitrary parameter_code.
Not further expanded to Ozone (44201) or Lead (14129/85129) -- see this
dataset's README for why.

NOTE on `temporal_aggregation_method` for CO/NO2/SO2: EPA's actual daily
summary statistic for these three is a MAX-OF-a-sub-daily-average (e.g.
CO's is the daily max of 8-hour running means), a two-stage aggregation
the schema's single-enum slot cannot fully represent. `maximum` is used
as the closest single value (it IS a daily maximum), with the underlying
sub-daily averaging window noted in curation_log.md rather than silently
lost.

NOTE on units: `ppm`/`ppb` are used for readability rather than strict
UCUM canonical form (which would be `10*-6`/`10*-9`) -- flagged in
curation_log.md, not a silent simplification.
"""
import copy
from pathlib import Path

import yaml

HERE = Path(__file__).parent
DATASET_DIR = HERE.parent / "datasets" / "aqs"
SOURCE_MODE = "synthetic"
BASE_SIDECAR = DATASET_DIR / "outputs" / SOURCE_MODE / "envar" / "sidecar_pm25.yaml"

VARIABLES = {
    "pm10": dict(
        param_code=81102, label="daily mean PM10 mass concentration (24-hour, STP)",
        standard_name="CF:mass_concentration_of_pm10_ambient_aerosol_particles_in_air",
        units_ucum="ug/m3", agg="mean", vmin=0, vmax=600,
    ),
    "co": dict(
        param_code=42101, label="daily maximum 8-hour running average carbon monoxide",
        standard_name="CF:mole_fraction_of_carbon_monoxide_in_air",
        units_ucum="ppm", agg="maximum", vmin=0, vmax=50,
    ),
    "no2": dict(
        param_code=42602, label="daily maximum 1-hour nitrogen dioxide",
        standard_name="CF:mole_fraction_of_nitrogen_dioxide_in_air",
        units_ucum="ppb", agg="maximum", vmin=0, vmax=500,
    ),
    "so2": dict(
        param_code=42401, label="daily maximum 1-hour sulfur dioxide",
        standard_name="CF:mole_fraction_of_sulfur_dioxide_in_air",
        units_ucum="ppb", agg="maximum", vmin=0, vmax=500,
    ),
}


def main() -> None:
    base = yaml.safe_load(BASE_SIDECAR.read_text())

    for col, meta in VARIABLES.items():
        doc = copy.deepcopy(base)
        doc["provenance_id"] = f"01AQS{col.upper()}PHXDEMO01-aqs-{col}"

        vi = doc["variable_identity"]
        vi["variable_name"] = f"{col}_{meta['param_code']}"
        vi["variable_label"] = meta["label"]
        vi["standard_name"] = meta["standard_name"]
        vi["cf_cell_methods"] = f"time: {meta['agg']}"
        vi["units_ucum"] = meta["units_ucum"]
        vi.pop("units_display", None)
        vi["value_range_plausible_min"] = meta["vmin"]
        vi["value_range_plausible_max"] = meta["vmax"]

        doc["data_layout"]["value_column"] = col
        doc["temporal_reference"]["temporal_aggregation_method"] = meta["agg"]

        # source_dataset_name should reflect the specific pollutant/parameter,
        # not silently keep saying "PM2.5"
        doc["source_dataset"]["source_dataset_name"] = (
            f"EPA Air Quality System (AQS) Pre-Generated Data Files -- "
            f"Daily Summary, parameter {meta['param_code']}"
        )

        out_path = DATASET_DIR / "outputs" / SOURCE_MODE / "envar" / f"sidecar_{col}.yaml"
        header = (
            f"# Amadeus -> EPA AQS {col.upper()} (parameter {meta['param_code']}) -- EnVar sidecar.\n"
            f"# Generated from the curated/validated PM2.5 sidecar's shared base\n"
            f"# (same monitor network, same run, same spatial/temporal/source/\n"
            f"# exposure_model/linkage/tool_run facts) plus per-pollutant facts\n"
            f"# researched for this batch -- see\n"
            f"# curator/generate_aqs_variants.py for the sourced deltas and\n"
            f"# curation_log.md for the shared-base sourcing and exclusions.\n"
        )
        with out_path.open("w") as fh:
            fh.write(header)
            yaml.safe_dump(doc, fh, sort_keys=False, default_flow_style=False, width=100)
        print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
