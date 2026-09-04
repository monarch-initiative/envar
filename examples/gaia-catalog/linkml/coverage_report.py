#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""coverage_report.py — measure how much of an EnVar sidecar a Gaia entry fills.

Walks the EnvironmentalExposureRecord composite blocks, and for each reports how
many slots the transform populated, how many it left empty, and — the number
that matters — how many REQUIRED slots the catalog could not supply.

This is the measurement behind the D2.2 claim that OMOP-GIS/GaiaCatalog metadata
is inadequate for environmental exposure data: not an assertion, but a count of
required fields with no source.
"""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import yaml

BLOCKS = [
    ("variable_identity", "VariableIdentity"),
    ("data_layout", "DataLayout"),
    ("spatial_reference", "SpatialReference"),
    ("temporal_reference", "TemporalReference"),
    ("source_dataset", "SourceDataset"),
    ("exposure_model", "ExposureModel"),
    ("linkage_method", "LinkageMethod"),
    ("tool_run", "ToolRun"),
]


def load_schema(schema_dir: Path) -> tuple[dict, dict]:
    classes: dict = {}
    slots: dict = {}
    for f in glob.glob(str(schema_dir / "*.yaml")):
        doc = yaml.safe_load(Path(f).read_text()) or {}
        classes.update({k: (v or {}) for k, v in (doc.get("classes") or {}).items()})
        slots.update({k: (v or {}) for k, v in (doc.get("slots") or {}).items()})
    return classes, slots


def required(name: str, cls: dict, slots: dict) -> bool:
    usage = (cls.get("slot_usage") or {}).get(name) or {}
    return bool(usage.get("required") or (slots.get(name) or {}).get("required"))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("records", type=Path, help="transform output YAML")
    p.add_argument("schema_dir", type=Path, help="EnVar micro-schema schema/ directory")
    args = p.parse_args()

    classes, slots = load_schema(args.schema_dir)
    # map-data emits a multi-document YAML stream, one document per record.
    records = [d for d in yaml.safe_load_all(args.records.read_text()) if d]
    rec = records[0]

    print(f"Records emitted: {len(records)}")
    print(f"Analysing: {rec.get('provenance_id')}\n")

    hdr = f"{'block':22} {'filled':>7} {'empty':>7} {'total':>7}   required unfilled"
    print(hdr)
    print("-" * len(hdr))

    tot_filled = tot_slots = 0
    gaps: list[tuple[str, str]] = []

    for slot_name, class_name in BLOCKS:
        cls = classes.get(class_name, {})
        names = cls.get("slots", []) or []
        present = rec.get(slot_name) or {}
        filled = [n for n in names if present.get(n) not in (None, "", [], {})]
        unfilled_req = [n for n in names if n not in filled and required(n, cls, slots)]
        gaps += [(slot_name, n) for n in unfilled_req]
        tot_filled += len(filled)
        tot_slots += len(names)
        flag = "  <-- entirely empty" if not filled else ""
        print(
            f"{slot_name:22} {len(filled):>7} {len(names) - len(filled):>7} {len(names):>7}"
            f"   {len(unfilled_req)}{flag}"
        )

    print("-" * len(hdr))
    pct = 100.0 * tot_filled / tot_slots if tot_slots else 0.0
    print(f"{'TOTAL':22} {tot_filled:>7} {tot_slots - tot_filled:>7} {tot_slots:>7}   {len(gaps)}")
    print(f"\nComposite-block coverage: {tot_filled}/{tot_slots} slots ({pct:.0f}%)")
    print(f"Required slots the catalog cannot supply: {len(gaps)}\n")

    for block, name in gaps:
        print(f"  {block}.{name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
