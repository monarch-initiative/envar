#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""run.py -- NARR relative humidity + wind speed + 28 more (amadeus `_narr`),
OFFLINE/SYNTHETIC ONLY.

For real (non-synthetic) NARR data, use amadeus_extract.R in this same
folder -- real R, amadeus's confirmed download_data() -> process_covariates()
-> calculate_covariates() API.

Reads the one shared, static cohort file at ../../input/patient_locations.csv.
Generates synthetic values deterministically (hash-seeded, not random --
reruns are reproducible) -- physically plausible for Phoenix/Tucson AZ,
July 2022, not real NARR output. See ../../README.md.

wind_speed IS computed for real here (sqrt(uwnd^2+vwnd^2)) -- that
arithmetic is real even though uwnd/vwnd are synthetic.

Output:
  outputs/synthetic/narr_all_vars.csv   person_id, date, lat, lon, rhum, wind_speed, ...
  outputs/synthetic/run_manifest.json   facts only
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
INPUT_CSV = HERE / ".." / ".." / "input" / "patient_locations.csv"
TOOL_NAME = "amadeus"
AMADEUS_VERSION_TARGET = "2.0.2"
R_VERSION_STRING = "R version 4.4.0 (2024-04-24)"

# Curated subset of NOAA PSL's NARR monolevel catalog (~30 of ~45
# available short names -- amadeus itself is variable-name-agnostic for
# NARR, this is a chosen comprehensive subset, not amadeus's own bound).
NARR_OTHER_VARS = [
    "air_2m", "dpt_2m", "pres_sfc", "apcp", "prate", "crain", "csnow",
    "cfrzr", "cicep", "weasd", "snod", "snowc", "dswrf", "uswrf_sfc",
    "dlwrf", "ulwrf_sfc", "gflux", "lhtfl", "shtfl", "hpbl", "tcdc",
    "pr_wtr", "cape", "cin", "veg", "albedo", "evap", "vis",
]

RANGES = {
    "air_2m": (28.0, 36.0), "dpt_2m": (2.0, 20.0), "pres_sfc": (95000.0, 96500.0),
    "apcp": (0.0, 8.0), "prate": (0.0, 0.0002), "crain": (0, 1), "csnow": (0, 0),
    "cfrzr": (0, 0), "cicep": (0, 0), "weasd": (0.0, 0.0), "snod": (0.0, 0.0),
    "snowc": (0.0, 0.0), "dswrf": (280.0, 340.0), "uswrf_sfc": (30.0, 55.0),
    "dlwrf": (330.0, 400.0), "ulwrf_sfc": (430.0, 490.0), "gflux": (-10.0, 40.0),
    "lhtfl": (10.0, 60.0), "shtfl": (150.0, 320.0), "hpbl": (1500.0, 3800.0),
    "tcdc": (5.0, 55.0), "pr_wtr": (10.0, 35.0), "cape": (0.0, 2200.0),
    "cin": (-300.0, 0.0), "veg": (8.0, 25.0), "albedo": (18.0, 28.0),
    "evap": (2.0, 7.0), "vis": (16000.0, 24000.0),
}
BINARY_FLAG_VARS = {"crain", "csnow", "cfrzr", "cicep"}
MONSOON_FACTOR = [0.3, 0.25, 0.2, 0.5, 0.9, 0.75, 0.35, 0.28]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_patient_locations() -> list[dict]:
    with INPUT_CSV.open() as fh:
        return list(csv.DictReader(fh))


def deterministic_frac(key: str) -> float:
    h = hashlib.sha256(key.encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def generate_synthetic(person_id: str, dates: list[str]) -> list[dict]:
    rows = []
    for day_idx, date in enumerate(dates):
        mf = MONSOON_FACTOR[day_idx % len(MONSOON_FACTOR)]
        row = {
            "date": date,
            "rhum": round(14 + mf * 22, 1),
            "uwnd": round(-2.0 + mf * 5.0, 2),
            "vwnd": round(1.0 - mf * 3.0, 2),
        }
        for var, (lo, hi) in RANGES.items():
            if var in BINARY_FLAG_VARS:
                val = 1 if (var == "crain" and mf > 0.7) else 0
            else:
                frac = deterministic_frac(f"{person_id}|{var}|{date}")
                if var in {"apcp", "prate", "tcdc", "pr_wtr", "cin"}:
                    frac = 0.3 * frac + 0.7 * mf
                elif var in {"dswrf", "vis", "shtfl"}:
                    frac = 0.3 * frac + 0.7 * (1 - mf)
                val = round(lo + frac * (hi - lo), 4)
            row[var] = val
        wind_speed = math.sqrt(row["uwnd"] ** 2 + row["vwnd"] ** 2)
        row["wind_speed"] = round(wind_speed, 3)
        rows.append(row)
    return rows


def main() -> int:
    locs = load_patient_locations()
    d0 = datetime.strptime(locs[0]["start_date"], "%Y-%m-%d")
    d1 = datetime.strptime(locs[0]["end_date"], "%Y-%m-%d")
    dates = []
    cur = d0
    while cur <= d1:
        dates.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)

    rows_out: list[dict] = []
    for loc in locs:
        for r in generate_synthetic(loc["person_id"], dates):
            row = {
                "person_id": loc["person_id"], "date": r["date"],
                "lat": loc["lat"], "lon": loc["lon"],
                "rhum": r["rhum"], "uwnd_ms": r["uwnd"], "vwnd_ms": r["vwnd"],
                "wind_speed": r["wind_speed"],
            }
            for v in NARR_OTHER_VARS:
                row[v] = r[v]
            rows_out.append(row)

    outputs_dir = HERE / "outputs" / "synthetic"
    (outputs_dir / "envar").mkdir(parents=True, exist_ok=True)
    out_csv = outputs_dir / "narr_all_vars.csv"
    fieldnames = ["person_id", "date", "lat", "lon", "rhum", "uwnd_ms", "vwnd_ms", "wind_speed"] + NARR_OTHER_VARS
    with out_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows_out)

    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    all_vars = ["rhum.2m", "uwnd.10m", "vwnd.10m -> wind_speed (derived)"] + NARR_OTHER_VARS
    manifest = {
        "dataset_short_code": "narr",
        "variable_name": all_vars,
        "tool_name": TOOL_NAME,
        "tool_version": AMADEUS_VERSION_TARGET,
        "r_version": R_VERSION_STRING,
        "execution_mode": "synthetic_offline_fixture",
        "run_timestamp_utc": run_ts,
        "r_call": (
            "for (v in c('rhum.2m', 'uwnd.10m', 'vwnd.10m', "
            + ", ".join(f"'{v.replace('_', '.')}'" for v in NARR_OTHER_VARS)
            + ")) { download_data(dataset_name='narr', year=2022, variable=v, ...); "
            "proc <- process_covariates(covariate='narr', date=c('2022-07-15','2022-07-22'), variable=v, ...); "
            "calculate_covariates(covariate='narr', from=proc, locs=locs, locs_id='id', radius=0, geom='sf') }"
        ),
        "input_file": "../../input/patient_locations.csv",
        "input_file_sha256": sha256_file(INPUT_CSV),
        "input_row_count": len(locs),
        "output_file": "outputs/synthetic/narr_all_vars.csv",
        "output_file_sha256": sha256_file(out_csv),
        "output_row_count": len(rows_out),
        "output_columns": fieldnames,
        "extraction_window_start": locs[0]["start_date"],
        "extraction_window_end": locs[0]["end_date"],
        "raster_reported": {"resolution_m": None, "crs": None, "native_units_as_stored": None},
        "_honesty_note": (
            "execution_mode=synthetic_offline_fixture: VALUES are illustrative "
            "placeholders, not real NARR output. See ../../README.md."
        ),
    }
    with (outputs_dir / "run_manifest.json").open("w") as fh:
        json.dump(manifest, fh, indent=2)

    print(f"wrote {out_csv} ({len(rows_out)} rows)")
    print(f"wrote {outputs_dir / 'run_manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
