#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["linkml-runtime", "pyyaml"]
# ///
"""coverage_report.py — measure how much of an EnVar sidecar a Gaia entry fills.

Resolves EnvironmentalExposureRecord through SchemaView, so imported slots and
slot_usage overrides are induced exactly the way `linkml-validate` induces them.
That matters: `subject` is required and comes from the LinkML Microschema
Profile, not from a local envar_*.yaml, so globbing the schema directory misses
it. The required-unfilled count here is meant to reconcile with the validator.

This is the measurement behind the D2.2 claim that OMOP-GIS/GaiaCatalog metadata
is inadequate for environmental exposure data: not an assertion, but a count of
required fields with no source.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from linkml_runtime.utils.schemaview import SchemaView

RECORD_CLASS = "EnvironmentalExposureRecord"
EMPTY = (None, "", [], {})


def resolve_schema(p: Path) -> Path:
    """Accept either the schema directory or envar_record.yaml itself."""
    return p / "envar_record.yaml" if p.is_dir() else p


def partition(sv: SchemaView) -> tuple[list, list]:
    """Split the record's slots into composite blocks and top-level scalars."""
    blocks, scalars = [], []
    for name in sv.class_slots(RECORD_CLASS):
        induced = sv.induced_slot(name, RECORD_CLASS)
        sub = sv.class_slots(induced.range) if induced.range in sv.all_classes() else []
        (blocks if sub else scalars).append((name, induced, sub))
    return blocks, scalars


def filled_in(rec: dict, block: str, names: list[str]) -> list[str]:
    present = rec.get(block) or {}
    return [n for n in names if present.get(n) not in EMPTY]


def signature(rec: dict, blocks: list) -> tuple:
    return tuple(sorted((b, n) for b, _, sub in blocks for n in filled_in(rec, b, sub)))


def report(rows: list, title: str, flag_empty: bool = True) -> tuple[int, int]:
    print(f"\n{title}")
    print(f"{'':22} {'filled':>7} {'empty':>7} {'total':>7}   required unfilled")
    print("-" * 66)
    tot_filled = tot_slots = 0
    for name, filled, total, unfilled_req in rows:
        flag = "  <-- entirely empty" if flag_empty and not filled and total else ""
        print(f"{name:22} {filled:>7} {total - filled:>7} {total:>7}   {unfilled_req}{flag}")
        tot_filled += filled
        tot_slots += total
    return tot_filled, tot_slots


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("records", type=Path, help="transform output YAML")
    p.add_argument("schema", type=Path, help="EnVar schema dir, or envar_record.yaml")
    args = p.parse_args()

    sv = SchemaView(str(resolve_schema(args.schema)))
    blocks, scalars = partition(sv)

    # map-data emits a multi-document YAML stream, one document per record.
    records = [d for d in yaml.safe_load_all(args.records.read_text()) if d]
    if not records:
        raise SystemExit(f"no records in {args.records}")
    rec = records[0]

    print(f"Records emitted: {len(records)}")
    sigs = {signature(r, blocks) for r in records}
    if len(sigs) == 1:
        print("All records share one fill signature — the table describes every record.")
    else:
        print(
            f"WARNING: {len(sigs)} distinct fill signatures across {len(records)} records. "
            "The table below describes only the first; the totals are NOT entry-wide."
        )
    print(f"Analysing: {rec.get('provenance_id')}")

    gaps: list[str] = []
    required_rows, optional_rows = [], []
    for name, induced, sub in blocks:
        filled = filled_in(rec, name, sub)
        # A required slot inside an absent optional block is not an error, so
        # only required blocks contribute gaps — same rule linkml-validate uses.
        unfilled_req = [
            n for n in sub
            if n not in filled and sv.induced_slot(n, induced.range).required
        ] if induced.required else []
        gaps += [f"{name}.{n}" for n in unfilled_req]
        row = (name, len(filled), len(sub), len(unfilled_req))
        (required_rows if induced.required else optional_rows).append(row)

    req_filled, req_slots = report(required_rows, "required composite blocks")
    print("-" * 66)
    print(f"{'SUBTOTAL':22} {req_filled:>7} {req_slots - req_filled:>7} {req_slots:>7}   {len(gaps)}")

    opt_filled, opt_slots = report(
        optional_rows,
        "optional composite blocks (excluded from the headline figure)",
        flag_empty=False,
    )

    scalar_rows = []
    for name, induced, _ in scalars:
        is_filled = rec.get(name) not in EMPTY
        unfilled_req = int(induced.required and not is_filled)
        if unfilled_req:
            gaps.append(name)
        scalar_rows.append((name, int(is_filled), 1, unfilled_req))
    sc_filled, sc_slots = report(scalar_rows, "top-level scalar slots")

    tot_filled = req_filled + opt_filled + sc_filled
    tot_slots = req_slots + opt_slots + sc_slots

    print("\n" + "=" * 66)
    print(
        f"Required-block coverage: {req_filled}/{req_slots} slots "
        f"({100.0 * req_filled / req_slots:.0f}%)"
    )
    print(
        f"Whole-record coverage:   {tot_filled}/{tot_slots} leaf slots "
        f"({100.0 * tot_filled / tot_slots:.0f}%)"
    )
    print(f"\nRequired slots the catalog cannot supply: {len(gaps)}\n")
    for g in gaps:
        print(f"  {g}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
