#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""prepare_omop.py — denormalize an EnVar sidecar onto a Daymet value table.

Reads the per-(person × day) Daymet value CSV and its matching EnVar
provenance sidecar, and stamps the sidecar's identifying metadata
(provenance_id, units, exposure-model type) onto every value row. The result
feeds the daymet → ExternalExposure trans-spec as flat DaymetValueRow records.

This is the single-source case: one sidecar per value table, so the "join" is a
constant denormalization (the dm-bip cleaners layer's job). The multi-source /
person→location joins are left to the linkml-map `joins` mechanism.

NOTE: the sidecar read here is the pipeline's current CONTRACT-shape sidecar
(variable.units_ucum, exposure_model.type). The durable target is Nico's
micro-schema `EnvironmentalExposureRecord`; reconciling the emitted sidecar to
that schema is tracked separately.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("value_csv", type=Path, help="Daymet value table CSV")
    p.add_argument("sidecar_json", type=Path, help="EnVar provenance sidecar JSON")
    p.add_argument("--out", type=Path, default=Path("inputs/daymet_values_prepared.csv"))
    args = p.parse_args()

    side = json.loads(args.sidecar_json.read_text())
    meta = {
        "provenance_id": side["provenance_id"],
        "units_ucum": side["variable"]["units_ucum"],
        "exposure_model_type": side.get("exposure_model", {}).get("type", ""),
    }

    with args.value_csv.open(newline="") as fh:
        rows = list(csv.DictReader(fh))

    out_cols = ["person_id", "date", "tmax", "provenance_id", "units_ucum", "exposure_model_type"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=out_cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, **meta})

    print(f"wrote {args.out} ({len(rows)} rows, sidecar {meta['provenance_id']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
