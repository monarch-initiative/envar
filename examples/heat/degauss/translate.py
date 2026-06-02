#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
translate.py — canonical patients JSON -> DeGAUSS cohort_addresses.csv.

DeGAUSS's geocoder container expects a CSV with at least an `address` column.
We additionally carry the `person_id` (so we can join back) and the
`start_date`/`end_date` from the study window (so the downstream Daymet step
knows the temporal extent for each row).

The `address` value is the DeGAUSS-expected "street + zip" form, e.g.
`100 W Washington St 85003` — no apartment numbers, no city, no state.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def build_address(addr: dict) -> str:
    """Construct DeGAUSS's expected `address` string: `"{street} {zip}"`.

    Prefer an explicit `geocoder_input` if the input JSON carries one (the
    canonical fixture does), otherwise build it from street + zip.
    """
    gi = addr.get("geocoder_input")
    if gi:
        return gi
    return f"{addr['street']} {addr['zip']}"


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
        default=Path("inputs/cohort_addresses.csv"),
        help="Output CSV path (default: inputs/cohort_addresses.csv)",
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
        w.writerow(["person_id", "address", "start_date", "end_date"])
        for pat in doc["patients"]:
            w.writerow(
                [
                    pat["person_id"],
                    build_address(pat["address"]),
                    start,
                    end,
                ]
            )

    print(f"wrote {args.out} ({len(doc['patients'])} rows, window {start}..{end})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
