# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""
Read all three systems' outputs and produce a comparability report.

This is the small downstream sidecar-diff utility from step 8 of the
heat scenario, in miniature. It does three things:

1. Print the Daymet vs GridMET Tmax values side by side, per patient-day.
2. Diff the slots that matter for cross-source comparability across the
   two upstream EnVar sidecars (source dataset, day boundary, extraction
   method, units, etc.).
3. Confirm that the OMOP external_exposure.exposure_source_value column
   resolves back to a real sidecar in omop-gaia/outputs/sidecars/.

Run from examples/heat/:
    uv run --script scripts/verify.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

DAYMET_CSV    = ROOT / "degauss"   / "outputs" / "cohort_addresses_geocoded_daymet.csv"
DAYMET_SC     = ROOT / "degauss"   / "outputs" / "envar" / "cohort_addresses_geocoded_daymet.provenance.json"
GRIDMET_CSV   = ROOT / "amadeus"   / "outputs" / "gridmet_tmmx.csv"
GRIDMET_SC    = ROOT / "amadeus"   / "outputs" / "envar" / "gridmet_tmmx.provenance.yaml"
OMOP_EXP      = ROOT / "omop-gaia" / "outputs" / "external_exposure.csv"
OMOP_SIDECARS = ROOT / "omop-gaia" / "outputs" / "envar" / "sidecars"
OMOP_MANIFEST = ROOT / "omop-gaia" / "outputs" / "envar" / "MANIFEST.json"
OMOP_GAIA_CAT = ROOT / "omop-gaia" / "outputs" / "gaia_catalog"


def need(p: Path) -> Path:
    if not p.exists():
        print(f"  MISSING: {p.relative_to(ROOT)}", file=sys.stderr)
        sys.exit(2)
    return p


def read_csv(p: Path) -> list[dict]:
    with p.open() as f:
        return list(csv.DictReader(f))


def side_by_side() -> None:
    print()
    print("=" * 78)
    print("  Daymet vs GridMET — same patient-day, two methods")
    print("=" * 78)

    dm = {(r["person_id"], r["date"]): r for r in read_csv(need(DAYMET_CSV))}
    gm = {(r["person_id"], r["date"]): r for r in read_csv(need(GRIDMET_CSV))}

    keys = sorted(set(dm) & set(gm))
    print(f"\n  {'person':>8}  {'date':>10}  {'daymet (°C)':>14}  {'gridmet (°C)':>14}  {'Δ°C':>7}")
    print("  " + "-" * 65)
    diffs = []
    for k in keys:
        dm_t = float(dm[k]["tmax"])
        gm_t = float(gm[k]["value_celsius"])
        d = dm_t - gm_t
        diffs.append(d)
        print(f"  {k[0]:>8}  {k[1]:>10}  {dm_t:>14.2f}  {gm_t:>14.2f}  {d:>+7.2f}")

    if diffs:
        n = len(diffs)
        avg = sum(diffs) / n
        amx = max(abs(x) for x in diffs)
        print(f"\n  n = {n}   mean Δ = {avg:+.2f} °C   max |Δ| = {amx:.2f} °C")


def sidecar_diff() -> None:
    print()
    print("=" * 78)
    print("  Sidecar diff — Daymet vs GridMET, slots that matter")
    print("=" * 78)

    dm = json.loads(need(DAYMET_SC).read_text())
    gm = yaml.safe_load(need(GRIDMET_SC).read_text())

    slots = [
        ("variable.cf_standard_name",          ["variable", "cf_standard_name"]),
        ("variable.cf_cell_methods",           ["variable", "cf_cell_methods"]),
        ("variable.units_ucum",                ["variable", "units_ucum"]),
        ("source_dataset.short_code",          ["source_dataset", "short_code"]),
        ("source_dataset.version",             ["source_dataset", "version"]),
        ("source_dataset.doi",                 ["source_dataset", "doi"]),
        ("spatial.native_spatial_resolution_m",["spatial", "native_spatial_resolution_m"]),
        ("spatial.extraction_method",          ["spatial", "extraction_method"]),
        ("temporal.day_boundary_convention",   ["temporal", "day_boundary_convention"]),
        ("temporal.temporal_aggregation_method",["temporal", "temporal_aggregation_method"]),
        ("exposure_model.type",                ["exposure_model", "type"]),
        ("tool_run.tool_name",                 ["tool_run", "tool_name"]),
        ("tool_run.tool_version",              ["tool_run", "tool_version"]),
    ]

    def dig(d: dict, path: list[str]) -> object:
        for p in path:
            if not isinstance(d, dict) or p not in d:
                return None
            d = d[p]
        return d

    print(f"\n  {'slot':<42}  {'daymet':<28}  {'gridmet':<28}  same?")
    print("  " + "-" * 110)
    for label, path in slots:
        a = dig(dm, path)
        b = dig(gm, path)
        same = "✓" if a == b else "✗"
        print(f"  {label:<42}  {str(a)[:26]:<28}  {str(b)[:26]:<28}    {same}")


def omop_link() -> None:
    print()
    print("=" * 78)
    print("  OMOP link integrity — does every exposure_source_value resolve?")
    print("=" * 78)

    rows = read_csv(need(OMOP_EXP))
    sidecar_dir = need(OMOP_SIDECARS)
    manifest = json.loads(need(OMOP_MANIFEST).read_text())

    by_id: dict[str, list[dict]] = {}
    for r in rows:
        by_id.setdefault(r["exposure_source_value"], []).append(r)

    print(f"\n  external_exposure rows: {len(rows)}")
    print(f"  distinct exposure_source_values: {len(by_id)}")
    print()
    print(f"  {'provenance_id':<40}  {'rows':>6}  {'sidecar present?':<18}")
    print("  " + "-" * 70)

    all_ok = True
    for pid, group in sorted(by_id.items()):
        candidates = list(sidecar_dir.glob(f"{pid}.*"))
        present = "yes" if candidates else "NO"
        if not candidates:
            all_ok = False
        print(f"  {pid:<40}  {len(group):>6}  {present:<18}")

    print()
    if all_ok:
        print("  ✓ every exposure_source_value resolves to a sidecar")
    else:
        print("  ✗ at least one exposure_source_value does not resolve — see above")
        sys.exit(3)

    # spot-check the slide example
    spot = [r for r in rows if r["person_id"] in ("91204", 91204) and r["exposure_start_date"] == "2022-07-19"]
    if spot:
        print()
        print("  Spot-check person 91204 / 2022-07-19:")
        for r in spot:
            print(f"    value_as_number = {r['value_as_number']}  unit=Cel  source={r['exposure_source_value']}")


def execution_modes() -> None:
    """Tell the reader which run path each upstream took (real tool vs fallback)."""
    print()
    print("=" * 78)
    print("  Execution mode — which pipeline actually ran?")
    print("=" * 78)

    dm = json.loads(need(DAYMET_SC).read_text())
    gm = yaml.safe_load(need(GRIDMET_SC).read_text())
    dm_mode = dm.get("tool_run", {}).get("execution_mode", "unknown")
    gm_mode = gm.get("tool_run", {}).get("execution_mode", "unknown")
    dm_digest = dm.get("tool_run", {}).get("container_image_digest")
    gm_digest = gm.get("tool_run", {}).get("container_image_digest")

    print()
    print(f"  DeGAUSS / Daymet  execution_mode = {dm_mode}")
    if dm_digest:
        print(f"                    container_image_digest = {dm_digest[:25]}...")
    print(f"  Amadeus / GridMET execution_mode = {gm_mode}")
    if gm_digest:
        print(f"                    container_image_digest = {gm_digest[:25]}...")


def gaia_catalog() -> None:
    """Confirm the OHDSI GIS WG / gaiaCatalog metadata files are present."""
    print()
    print("=" * 78)
    print("  GIS WG / gaiaCatalog files — the OHDSI-native metadata layer")
    print("=" * 78)
    if not OMOP_GAIA_CAT.exists():
        print(f"\n  MISSING: {OMOP_GAIA_CAT.relative_to(ROOT)}", file=sys.stderr)
        sys.exit(2)
    files = sorted(OMOP_GAIA_CAT.glob("*.json"))
    print()
    for f in files:
        size = f.stat().st_size
        print(f"  {f.relative_to(ROOT)}  ({size} B)")
    print()
    print(f"  total: {len(files)} files (expected 6: meta_etl/meta_dcat/meta_json-ld × 2 datasets)")


def main() -> None:
    print("EnVar heat scenario — end-to-end verification")
    print()
    side_by_side()
    execution_modes()
    sidecar_diff()
    omop_link()
    gaia_catalog()
    print()


if __name__ == "__main__":
    main()
