#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""prepare.py — denormalize study_window onto each patient.

Generic data-prep step (not transform logic): copies the top-level
study_window.start/end down onto every patient as window_start/window_end so
the declarative linkml-map trans-spec can populate per-row dates with a plain
`populated_from`, instead of reaching across the parent/child scope boundary
(which linkml-map's per-object expr evaluation cannot do). This is the sort of
denormalization dm-bip's `cleaners`/`prepare_input` layer is responsible for.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input_json", type=Path)
    p.add_argument("--out", type=Path, default=Path("inputs/patients_prepared.json"))
    args = p.parse_args()

    doc = json.loads(args.input_json.read_text())
    window = doc["study_window"]
    for pat in doc["patients"]:
        pat["window_start"] = window["start"]
        pat["window_end"] = window["end"]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2))
    print(f"wrote {args.out} ({len(doc['patients'])} patients, window {window['start']}..{window['end']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
