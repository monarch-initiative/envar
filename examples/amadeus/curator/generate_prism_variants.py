#!/usr/bin/env python3
"""generate_prism_variants.py — generate sidecars for PRISM's other 6
daily variables (ppt, tmin, tmean, tdmean, vpdmin, vpdmax), reusing the
already-curated/validated tmax sidecar as the shared base.

amadeus's download_prism() supports exactly these 7 variables (CRAN
amadeus.pdf: "ppt", "tmean", "tmin", "tmax", "tdmean", "vpdmin",
"vpdmax") -- this is amadeus's REAL, bounded PRISM coverage, not an
arbitrary subset. tmax is already curated by hand; this script fills in
the other 6 using the same spatial/temporal/source/exposure/linkage/
tool_run facts (all genuinely shared -- same PRISM AN81d product, same
run, same everything except the variable itself), with per-variable
identity facts looked up from PRISM's own documentation
(PRISM_datasets.pdf: "Units and scaling: tmin, tmax, tmean, tdmean (deg
C); ppt (mm); vpdmin, vpdmax (hPa)").

This is a generation SCRIPT for this one batch, not a permanent
schema-mapping tool -- the facts it encodes were researched, not
templated blindly, and it isn't meant to be reused against a changed
schema without re-checking (see SKILL.md's golden rule).
"""
import copy
from pathlib import Path

import yaml

HERE = Path(__file__).parent
DATASET_DIR = HERE.parent / "datasets" / "prism"
# Which output tree to read the base from / write variants into. Both
# "synthetic" (from run.py) and "real" (from amadeus_extract.R) trees
# have the same internal shape, so this is the only line to change once
# a real R run exists and you want to curate that instead.
SOURCE_MODE = "synthetic"
BASE_SIDECAR = DATASET_DIR / "outputs" / SOURCE_MODE / "envar" / "sidecar_tmax.yaml"

# Per-variable deltas. Units confirmed: PRISM_datasets.pdf "Units and
# scaling: tmin, tmax, tmean, tdmean (deg C); ppt (mm); vpdmin, vpdmax (hPa)"
VARIANTS = {
    "ppt": {
        "variable_label": "daily total precipitation",
        "standard_name": "CF:precipitation_amount",
        "cf_cell_methods": "time: sum",
        "units_ucum": "mm",
        "temporal_aggregation_method": "sum",
        "value_range_plausible_min": 0,
        "value_range_plausible_max": 500,
        "concept_mappings": ["ECTO:0000012"],
    },
    "tmin": {
        "variable_label": "daily minimum air temperature at 2 m",
        "standard_name": "CF:air_temperature",
        "cf_cell_methods": "time: minimum",
        "units_ucum": "Cel",
        "temporal_aggregation_method": "minimum",
        "value_range_plausible_min": -60,
        "value_range_plausible_max": 50,
        "concept_mappings": ["ECTO:0000012"],
    },
    "tmean": {
        "variable_label": "daily mean air temperature at 2 m",
        "standard_name": "CF:air_temperature",
        "cf_cell_methods": "time: mean",
        "units_ucum": "Cel",
        "temporal_aggregation_method": "mean",
        "value_range_plausible_min": -50,
        "value_range_plausible_max": 55,
        "concept_mappings": ["ECTO:0000012"],
    },
    "tdmean": {
        "variable_label": "daily mean dew point temperature at 2 m",
        "standard_name": "CF:dew_point_temperature",
        "cf_cell_methods": "time: mean",
        "units_ucum": "Cel",
        "temporal_aggregation_method": "mean",
        "value_range_plausible_min": -50,
        "value_range_plausible_max": 40,
        "concept_mappings": [],
    },
    "vpdmin": {
        "variable_label": "daily minimum vapor pressure deficit",
        # No CF standard name for VPD -- minted per schema's own convention
        # for non-CF health-relevant quantities.
        "standard_name": "ENVAR:vapor_pressure_deficit",
        "cf_cell_methods_omit": True,  # CF cell_methods is conditionally-core
                                        # on standard_name using CF: prefix --
                                        # correctly OMITTED here, not left blank
        "units_ucum": "hPa",
        "temporal_aggregation_method": "minimum",
        "value_range_plausible_min": 0,
        "value_range_plausible_max": 100,
        "concept_mappings": [],
    },
    "vpdmax": {
        "variable_label": "daily maximum vapor pressure deficit",
        "standard_name": "ENVAR:vapor_pressure_deficit",
        "cf_cell_methods_omit": True,
        "units_ucum": "hPa",
        "temporal_aggregation_method": "maximum",
        "value_range_plausible_min": 0,
        "value_range_plausible_max": 120,
        "concept_mappings": [],
    },
}


def main() -> None:
    base_text = BASE_SIDECAR.read_text()
    base = yaml.safe_load(base_text)

    for var, delta in VARIANTS.items():
        doc = copy.deepcopy(base)
        doc["provenance_id"] = f"01PRISM{var.upper()}PHXAMADEUSDEMO01-prism-{var}"

        vi = doc["variable_identity"]
        vi["variable_name"] = var
        vi["variable_label"] = delta["variable_label"]
        vi["standard_name"] = delta["standard_name"]
        if delta.get("cf_cell_methods_omit"):
            vi.pop("cf_cell_methods", None)
        else:
            vi["cf_cell_methods"] = delta.get(
                "cf_cell_methods", f"time: {delta['temporal_aggregation_method']}"
            )
        vi["units_ucum"] = delta["units_ucum"]
        vi["value_range_plausible_min"] = delta["value_range_plausible_min"]
        vi["value_range_plausible_max"] = delta["value_range_plausible_max"]
        if delta["concept_mappings"]:
            vi["concept_mappings"] = delta["concept_mappings"]
        else:
            vi.pop("concept_mappings", None)

        doc["data_layout"]["value_column"] = var
        doc["temporal_reference"]["temporal_aggregation_method"] = delta[
            "temporal_aggregation_method"
        ]

        out_path = DATASET_DIR / "outputs" / SOURCE_MODE / "envar" / f"sidecar_{var}.yaml"
        header = (
            f"# Amadeus -> PRISM AN81d daily {var} -- EnVar sidecar.\n"
            f"# Generated from the curated/validated tmax sidecar's shared base\n"
            f"# (same PRISM product, same run, same spatial/temporal/source/\n"
            f"# exposure_model/linkage/tool_run facts) plus per-variable facts\n"
            f"# looked up from PRISM's own documentation -- see\n"
            f"# curator/generate_prism_variants.py for the sourced deltas and\n"
            f"# curation_log.md for the shared-base sourcing.\n"
        )
        with out_path.open("w") as fh:
            fh.write(header)
            yaml.safe_dump(doc, fh, sort_keys=False, default_flow_style=False, width=100)
        print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
