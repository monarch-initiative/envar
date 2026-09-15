#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""run.py -- PRISM daily Tmax + 6 more (amadeus `_prism`), OFFLINE/SYNTHETIC ONLY.

For real (non-synthetic) PRISM data sourced through actual amadeus, use
amadeus_extract.R in this same folder -- real R, amadeus's confirmed
download_data() -> process_covariates() -> calculate_covariates() API.
This script has no online path: an earlier version made a direct HTTP
call to PRISM's own REST API, bypassing amadeus entirely -- removed.

Reads the one shared, static cohort file at ../../input/patient_locations.csv
(converted once from examples/heat/data/patients_example1.json -- see
../../README.md). Generates synthetic Tmax/Tmin/Tmean/Tdmean/Ppt/VPD
values deterministically (same formula every run, not random) --
physically plausible for Phoenix/Tucson AZ, July 2022, not real PRISM
output. See ../../README.md's "Honesty about what actually ran" section.

Output:
  outputs/synthetic/prism_all_vars.csv   person_id, date, lat, lon, tmax, tmin, ...
  outputs/synthetic/run_manifest.json    facts only -- see ../../README.md's Contract section
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
PRISM_VARS = ["tmax", "tmin", "tmean", "tdmean", "ppt", "vpdmin", "vpdmax"]

# Deterministic synthetic Tmax series per patient (Phoenix/Tucson AZ,
# July 2022 heatwave), then physically-consistent derived variables
# (tmin < tmean < tmax; a small monsoon-onset ppt event mid-window that
# raises tdmean and lowers VPD). Not random -- reruns are reproducible.
TMAX_BASE = {
    "91204": [43.9, 44.4, 45.6, 46.1, 46.7, 45.0, 44.2, 43.3],
    "91205": [43.7, 44.2, 45.3, 45.9, 46.4, 44.8, 44.0, 43.1],
    "91206": [41.1, 41.7, 42.8, 43.3, 43.9, 42.2, 41.4, 40.6],
}
PPT_PATTERN = [0.0, 0.0, 0.0, 0.2, 3.8, 6.1, 0.4, 0.0]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_patient_locations() -> list[dict]:
    with INPUT_CSV.open() as fh:
        return list(csv.DictReader(fh))


def generate_synthetic(person_id: str, dates: list[str]) -> list[dict]:
    tmax_series = TMAX_BASE[person_id]
    rows = []
    for i, date in enumerate(dates):
        tmax = tmax_series[i]
        tmin = round(tmax - 14.0, 1)
        tmean = round((tmax + tmin) / 2, 1)
        ppt = PPT_PATTERN[i]
        tdmean = round(8.0 + ppt * 1.3, 1)
        vpd_base = 45.0 - ppt * 3.5
        rows.append({
            "date": date, "tmax": tmax, "tmin": tmin, "tmean": tmean,
            "tdmean": tdmean, "ppt": ppt,
            "vpdmin": round(max(vpd_base - 15, 5.0), 1),
            "vpdmax": round(vpd_base, 1),
        })
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
            row = {"person_id": loc["person_id"], "date": r["date"], "lat": loc["lat"], "lon": loc["lon"]}
            for v in PRISM_VARS:
                row[v] = r[v]
            rows_out.append(row)

    outputs_dir = HERE / "outputs" / "synthetic"
    (outputs_dir / "envar").mkdir(parents=True, exist_ok=True)
    out_csv = outputs_dir / "prism_all_vars.csv"
    fieldnames = ["person_id", "date", "lat", "lon"] + PRISM_VARS
    with out_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows_out)

    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = {
        "dataset_short_code": "prism",
        "variable_name": PRISM_VARS,
        "tool_name": TOOL_NAME,
        "tool_version": AMADEUS_VERSION_TARGET,
        "r_version": R_VERSION_STRING,
        "execution_mode": "synthetic_offline_fixture",
        "run_timestamp_utc": run_ts,
        "r_call": (
            "for (v in c(" + ", ".join(f"'{v}'" for v in PRISM_VARS) + ")) { "
            "download_data(dataset_name='prism', year=2022, variable=v, ...); "
            "proc <- process_covariates(covariate='prism', date=c('2022-07-15','2022-07-22'), variable=v, ...); "
            "calculate_covariates(covariate='prism', from=proc, locs=locs, locs_id='id', radius=0, geom='sf') }"
        ),
        "input_file": "../../input/patient_locations.csv",
        "input_file_sha256": sha256_file(INPUT_CSV),
        "input_row_count": len(locs),
        "output_file": "outputs/synthetic/prism_all_vars.csv",
        "output_file_sha256": sha256_file(out_csv),
        "output_row_count": len(rows_out),
        "output_columns": fieldnames,
        "extraction_window_start": locs[0]["start_date"],
        "extraction_window_end": locs[0]["end_date"],
        "raster_reported": {
            "resolution_m": None,
            "crs": None,
            "native_units_as_stored": {
                "tmax": "Cel", "tmin": "Cel", "tmean": "Cel", "tdmean": "Cel",
                "ppt": "mm", "vpdmin": "hPa", "vpdmax": "hPa",
            },
        },
        "_honesty_note": (
            "execution_mode=synthetic_offline_fixture: VALUES are illustrative "
            "placeholders generated by this script's formula (see TMAX_BASE), "
            "not real PRISM output. See ../../README.md."
        ),
    }
    with (outputs_dir / "run_manifest.json").open("w") as fh:
        json.dump(manifest, fh, indent=2)

    print(f"wrote {out_csv} ({len(rows_out)} rows)")
    print(f"wrote {outputs_dir / 'run_manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
