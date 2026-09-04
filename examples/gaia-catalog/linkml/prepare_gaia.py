#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""prepare_gaia.py — flatten a GaiaCatalog entry into per-variable source rows.

A GaiaCatalog dataset directory carries its metadata in three files
(`meta_dcat_*`, `meta_etl_*`, `meta_json-ld_*`). Each holds a different slice:
DCAT the citation/rights layer, ETL the acquisition layer, JSON-LD the richest
and the only one describing individual measured variables.

An EnVar sidecar describes ONE variable, so a catalog entry fans out: this
script emits one `GaiaVariableRow` per measured variable, with the dataset-level
metadata from all three files denormalized onto it. Same shape as
`../../heat/omop-gaia/linkml/prepare_omop.py` — a constant denormalization
standing in for the cleaners layer.

Only `variableMeasured` entries carrying a `propertyID` are emitted. In the
catalog that field marks a column bound to an OMOP concept, which is the closest
available signal for "this is a measured exposure" as opposed to a geometry or
label column (`urbid`, `stndrdname`, ...).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def find_meta(d: Path, kind: str) -> Path:
    hits = sorted(d.glob(f"meta_{kind}_*.json"))
    if not hits:
        raise SystemExit(f"no meta_{kind}_*.json in {d}")
    return hits[0]


def term_code(mt: list, set_name: str) -> str:
    """Pull the chosen termCode for a named DefinedTermSet out of measurementTechnique."""
    for entry in mt:
        if entry.get("inDefinedTermSet", {}).get("name") == set_name:
            return entry.get("termCode", "")
    return ""


def bbox_polygon(coverage: list) -> str:
    for place in coverage:
        geo = place.get("geo")
        if geo:
            return geo.get("polygon", "")
    return ""


def bbox_bounds(polygon: str) -> dict:
    """Reduce the catalog's bbox polygon ring to west/south/east/north bounds.

    `spatialCoverage[].geo.polygon` is a flat "lon lat lon lat ..." ring, while
    EnVar's `spatial_extent_bbox` is four numbers. The ring is already
    axis-aligned and labelled bbox in the catalog, so this is a lossless
    normalization, not an inference.
    """
    nums = [float(n) for n in polygon.split()]
    if len(nums) < 8 or len(nums) % 2:
        return {}
    lons, lats = nums[0::2], nums[1::2]
    return {
        "bbox_west": min(lons),
        "bbox_south": min(lats),
        "bbox_east": max(lons),
        "bbox_north": max(lats),
    }


def place_name(coverage: list) -> str:
    for place in coverage:
        if "geo" not in place and place.get("name"):
            return place["name"]
    return ""


def additional_property(props: list, property_id: str) -> str:
    for p in props:
        if p.get("propertyID") == property_id:
            return p.get("value", "")
    return ""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("catalog_dir", type=Path, help="GaiaCatalog dataset directory")
    p.add_argument("--out", type=Path, default=Path("inputs/gaia_variable_rows.json"))
    args = p.parse_args()

    jsonld = json.loads(find_meta(args.catalog_dir, "json-ld").read_text())
    dcat = json.loads(find_meta(args.catalog_dir, "dcat").read_text())
    etl = json.loads(find_meta(args.catalog_dir, "etl").read_text())

    mt = jsonld.get("measurementTechnique", [])
    coverage = jsonld.get("spatialCoverage", [])

    # Dataset-level metadata, stamped onto every variable row.
    dataset = {
        "dataset_id": jsonld.get("@id", ""),
        "dataset_name": jsonld.get("name", ""),
        "dataset_description": jsonld.get("description", ""),
        "dataset_url": jsonld.get("url", ""),
        "dataset_type": jsonld.get("type", ""),
        "catalog_version": jsonld.get("version", ""),
        "date_published": jsonld.get("datePublished", ""),
        "date_modified": jsonld.get("dateModified", ""),
        "keywords": "; ".join(jsonld.get("keywords", [])),
        "language": jsonld.get("@language", ""),
        # measurementTechnique: nested DefinedTermSets, one per facet
        "data_representation": term_code(mt, "dataRepresentation"),
        "vector_geometry": term_code(mt, "vectorGeometry"),
        # spatialCoverage: a named Place plus a bbox Place carrying a GeoShape
        "spatial_place_name": place_name(coverage),
        "spatial_bbox_polygon": bbox_polygon(coverage),
        **bbox_bounds(bbox_polygon(coverage)),
        "crs": additional_property(
            jsonld.get("additionalProperty", []),
            "http://dbpedia.org/resource/Spatial_reference_system",
        ),
        # DCAT — citation and rights
        "identifier": dcat.get("dct:identifier", ""),
        "creator": "; ".join(dcat.get("dct:creator", [])),
        "publisher": "; ".join(dcat.get("dct:publisher", [])),
        "rights": dcat.get("dct:rights", ""),
        "issued": dcat.get("dct:issued", ""),
        "accrual_periodicity": dcat.get("dct:accrualPeriodicity", ""),
        "landing_page": dcat.get("dcat:landingPage", ""),
        "conforms_to": dcat.get("dct:conformsTo", ""),
        "checksum": dcat.get("spdx:checksum", ""),
        # ETL — acquisition
        "etl_source_url": etl.get("source", ""),
        "etl_structure": etl.get("structure", ""),
        "etl_geometry": etl.get("geometry", ""),
        "etl_epsg": etl.get("epsg", ""),
        "etl_local_epsg": etl.get("local_epsg", ""),
        "etl_format": etl.get("format", ""),
        "etl_download_method": etl.get("download", ""),
        "etl_last_updated": etl.get("last_updated", ""),
        "etl_update_frequency": etl.get("update_frequency", ""),
        "etl_nodata": ";".join(etl.get("nodata", [])),
        "etl_table": etl.get("table", ""),
    }

    rows = []
    for var in jsonld.get("variableMeasured", []):
        if "propertyID" not in var:
            continue
        rows.append(
            {
                **dataset,
                "variable_name": var.get("name", ""),
                "variable_description": var.get("description", "").strip('"'),
                "property_id": var.get("propertyID", ""),
                "data_type": var.get("qudt:dataType", ""),
                "unit_code": var.get("unitCode", ""),
                "unit_text": var.get("unitText", ""),
                "min_value": var.get("minValue", ""),
                "max_value": var.get("maxValue", ""),
                "start_date": var.get("startDate", ""),
                "end_date": var.get("endDate", ""),
            }
        )

    if not rows:
        raise SystemExit("no variableMeasured entries carried a propertyID")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, indent=2) + "\n")

    total = len(jsonld.get("variableMeasured", []))
    print(f"wrote {args.out} ({len(rows)} of {total} variables carried a propertyID)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
