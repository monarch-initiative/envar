#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
translate.py — canonical patients JSON -> Amadeus patient_locations.csv.

Amadeus's `calculate_covariates()` consumes an `sf`-style point table: one row
per (person × location) with `lat`, `lon`, and a temporal window. Since the
canonical fixture carries one address per patient, `person_loc_id` == `person_id`
(stringified) here. The temporal window is taken from the study window.

This is the input shape that the upstream R code would normally build before
calling `amadeus::download_data("gridmet", ...)` + `calculate_covariates(...)`.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "input_json",
        type=Path,
        help="Path to canonical patients JSON (e.g. ../data/patients_example1.json)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path("inputs/patient_locations.csv"),
        help="Output CSV path (default: inputs/patient_locations.csv)",
    )
    args = p.parse_args()

    with args.input_json.open() as fh:
        doc = json.load(fh)

    window = doc["study_window"]
    start = window["start"]
    end = window["end"]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["person_loc_id", "lat", "lon", "start_date", "end_date"])
        for pat in doc["patients"]:
            geo = pat["geocoded"]
            w.writerow(
                [
                    str(pat["person_id"]),
                    geo["lat"],
                    geo["lon"],
                    start,
                    end,
                ]
            )

    print(f"wrote {args.out} ({len(doc['patients'])} rows, window {start}..{end})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
