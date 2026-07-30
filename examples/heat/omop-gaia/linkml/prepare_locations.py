#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""prepare_locations.py — build the OMOP Location table + person→location lookup.

Reads the real Census geocoder output and produces:
  - location.csv         the OMOP Location table (one row per unique address),
                         with a surrogate location_id
  - PersonLocation.csv   the person_id → location_id lookup consumed by the
                         daymet → ExternalExposure join

location_id is deduped by address, so two people at the same address share one
Location row (standard OMOP). Here the three addresses are distinct, so it is
one location per person, but the dedupe keeps it correct in general.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("geocoded_csv", type=Path, help="cohort_addresses_geocoded.csv")
    p.add_argument("--location-out", type=Path, default=Path("inputs/location.csv"))
    p.add_argument("--lookup-out", type=Path, default=Path("inputs/PersonLocation.csv"))
    args = p.parse_args()

    with args.geocoded_csv.open() as fh:
        rows = list(csv.DictReader(fh))

    # Assign a surrogate location_id per unique address (dedupe).
    loc_id_by_addr: dict[str, int] = {}
    locations: list[dict] = []
    person_location: list[dict] = []
    for r in rows:
        addr = r["address"]
        if addr not in loc_id_by_addr:
            loc_id = len(loc_id_by_addr) + 1
            loc_id_by_addr[addr] = loc_id
            locations.append({
                "location_id": loc_id,
                "address_1": addr,
                "city": r.get("matched_city", ""),
                "state": r.get("matched_state", ""),
                "zip": r.get("matched_zip", ""),
                "latitude": r.get("lat", ""),
                "longitude": r.get("lon", ""),
            })
        person_location.append({"person_id": r["person_id"], "location_id": loc_id_by_addr[addr]})

    args.location_out.parent.mkdir(parents=True, exist_ok=True)
    with args.location_out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["location_id", "address_1", "city", "state", "zip", "latitude", "longitude"])
        w.writeheader()
        w.writerows(locations)

    args.lookup_out.parent.mkdir(parents=True, exist_ok=True)
    with args.lookup_out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["person_id", "location_id"])
        w.writeheader()
        w.writerows(person_location)

    print(f"wrote {args.location_out} ({len(locations)} locations) and {args.lookup_out} ({len(person_location)} persons)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
