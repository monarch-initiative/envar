#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""run.py -- EPA AQS PM2.5/PM10/CO/NO2/SO2 (amadeus `_aqs`), OFFLINE/SYNTHETIC ONLY.

For real (non-synthetic) AQS data, use amadeus_extract.R in this same
folder -- confirms amadeus's download step; the point-in-time extraction
is hand-written (amadeus doesn't expose AQS through calculate_covariates()
-- see ../../README.md).

Reads the one shared, static cohort file at ../../input/patient_locations.csv.
Generates synthetic values deterministically from a base PM2.5 series,
scaled per pollutant -- not physically rigorous, illustrative only.

Output:
  outputs/synthetic/aqs_all_params.csv   person_id, date, lat, lon, value, monitor_distance_m, pm10, co, no2, so2
  outputs/synthetic/run_manifest.json    facts only
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
INPUT_CSV = HERE / ".." / ".." / "input" / "patient_locations.csv"
TOOL_NAME = "amadeus"
AMADEUS_VERSION_TARGET = "2.0.2"
R_VERSION_STRING = "R version 4.4.0 (2024-04-24)"
# Confirmed against EPA's own AQS documentation (AQS Concepts / AQS Basics).
PARAMS = {"pm25": 88101, "pm10": 81102, "co": 42101, "no2": 42602, "so2": 42401}

PM25_BASE = {
    "91204": ([8.4, 9.1, 11.3, 7.6, 6.9, 14.2, 10.5, 8.8], 2100),
    "91205": ([8.1, 8.9, 10.9, 7.3, 6.6, 13.7, 10.1, 8.5], 3400),
    "91206": ([6.2, 6.8, 8.1, 5.9, 5.4, 9.8, 7.7, 6.5], 1800),
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_patient_locations() -> list[dict]:
    with INPUT_CSV.open() as fh:
        return list(csv.DictReader(fh))


def scale(series: list[float], lo: float, hi: float) -> list[float]:
    smin, smax = min(series), max(series)
    return [round(lo + (v - smin) / (smax - smin) * (hi - lo), 3) for v in series]


def generate_synthetic(person_id: str, dates: list[str]) -> list[dict]:
    pm25_series, dist = PM25_BASE[person_id]
    pm10 = scale(pm25_series, 12.0, 28.0)
    co = scale(pm25_series, 0.15, 0.45)
    no2 = scale(pm25_series, 8.0, 22.0)
    so2 = scale(pm25_series, 0.5, 3.0)
    return [
        {
            "date": date, "value": pm25_series[i], "monitor_distance_m": dist,
            "pm10": pm10[i], "co": co[i], "no2": no2[i], "so2": so2[i],
        }
        for i, date in enumerate(dates)
    ]


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
            row = {"person_id": loc["person_id"], "date": r["date"], "lat": loc["lat"], "lon": loc["lon"]}
            row.update(r)
            del row["date"]
            row["date"] = r["date"]
            rows_out.append(row)

    outputs_dir = HERE / "outputs" / "synthetic"
    (outputs_dir / "envar").mkdir(parents=True, exist_ok=True)
    out_csv = outputs_dir / "aqs_all_params.csv"
    fieldnames = ["person_id", "date", "lat", "lon", "value", "monitor_distance_m", "pm10", "co", "no2", "so2"]
    with out_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows_out)

    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = {
        "dataset_short_code": "aqs",
        "variable_name": [f"{k}_{v}" for k, v in PARAMS.items()],
        "tool_name": TOOL_NAME,
        "tool_version": AMADEUS_VERSION_TARGET,
        "r_version": R_VERSION_STRING,
        "execution_mode": "synthetic_offline_fixture",
        "run_timestamp_utc": run_ts,
        "r_call": (
            "for (p in c(" + ", ".join(str(v) for v in PARAMS.values()) + ")) { "
            "download_data(dataset_name='aqs', year=2022, parameter_code=p, ...) }; "
            "<point extraction NOT via calculate_covariates() -- see ../../README.md>"
        ),
        "input_file": "../../input/patient_locations.csv",
        "input_file_sha256": sha256_file(INPUT_CSV),
        "input_row_count": len(locs),
        "output_file": "outputs/synthetic/aqs_all_params.csv",
        "output_file_sha256": sha256_file(out_csv),
        "output_row_count": len(rows_out),
        "output_columns": fieldnames,
        "extraction_window_start": locs[0]["start_date"],
        "extraction_window_end": locs[0]["end_date"],
        "raster_reported": {"resolution_m": None, "crs": None, "native_units_as_stored": None},
        "_honesty_note": (
            "execution_mode=synthetic_offline_fixture: VALUES are illustrative "
            "placeholders, not real AQS output. See ../../README.md. Point-network "
            "structure, not a raster -- see ../../README.md's known-issues note."
        ),
    }
    with (outputs_dir / "run_manifest.json").open("w") as fh:
        json.dump(manifest, fh, indent=2)

    print(f"wrote {out_csv} ({len(rows_out)} rows)")
    print(f"wrote {outputs_dir / 'run_manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
