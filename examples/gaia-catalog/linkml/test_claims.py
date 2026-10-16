"""test_claims.py — the README's statements of fact, checked.

Each test is named for the finding it backs. Run from the repo root:

    uv run pytest examples/gaia-catalog/linkml

Searches for where a value appears ("only in", "absent from") run across all
three metadata files, never a targeted lookup, so a claim cannot pass by
looking in the wrong place.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from linkml_runtime.utils.schemaview import SchemaView

from envar_model import schema_path

HERE = Path(__file__).parent
FIXTURES = HERE.parent / "fixtures"
KINDS = ("dcat", "etl", "json-ld")


def load(kind: str) -> dict:
    return json.loads(next(FIXTURES.glob(f"meta_{kind}_*.json")).read_text())


@pytest.fixture(scope="session")
def meta() -> dict:
    return {k: load(k) for k in KINDS}


def files_containing(meta: dict, needle: str) -> set[str]:
    return {k for k, doc in meta.items() if needle in json.dumps(doc, ensure_ascii=False)}


@pytest.fixture(scope="session")
def sv() -> SchemaView:
    return SchemaView(str(schema_path()))


@pytest.fixture(scope="session")
def measured(variables) -> list[dict]:
    return [v for v in variables if "propertyID" in v]


@pytest.fixture(scope="session")
def variables(meta) -> list[dict]:
    return meta["json-ld"]["variableMeasured"]


@pytest.fixture(scope="session")
def avpmu_attributes(meta) -> list[str]:
    return [a for a in meta["etl"]["attributes"] if a.startswith("avpmu_")]


@pytest.fixture(scope="session")
def pipeline(tmp_path_factory) -> dict:
    """Run the README's three steps once; return the records and tool output."""
    work = tmp_path_factory.mktemp("pipeline")
    rows = work / "rows.json"
    indir = work / "indir"
    records = work / "envar_records.yaml"
    indir.mkdir()
    schema = str(schema_path())

    def run(*cmd: str) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)

    run("python", "prepare_gaia.py", str(FIXTURES), "--out", str(rows)).check_returncode()
    shutil.copy(rows, indir / "GaiaVariableRow.json")
    run(
        "linkml-map", "map-data", "-T", "gaia_to_envar_record.transform.yaml",
        "-s", "gaia_catalog.source.yaml", "--target-schema", schema,
        "-o", str(records), str(indir),
    ).check_returncode()
    validate = run("linkml-validate", "-s", schema, "-C", "EnvironmentalExposureRecord", str(records))
    coverage = run("python", "coverage_report.py", str(records))
    coverage.check_returncode()
    return {
        "records": [d for d in yaml.safe_load_all(records.read_text()) if d],
        "errors": [ln for ln in (validate.stdout + validate.stderr).splitlines() if ln.startswith("[ERROR]")],
        "coverage": coverage.stdout,
    }


# ── Result ────────────────────────────────────────────────────────────────

def test_result_records_and_signature(pipeline):
    assert len(pipeline["records"]) == 19
    assert "All records share one fill signature" in pipeline["coverage"]


def test_result_coverage_figures(pipeline):
    out = pipeline["coverage"]
    assert re.search(r"Required-block coverage: 19/119 slots \(16%\)", out)
    assert re.search(r"Whole-record coverage:\s+22/178 leaf slots \(12%\)", out)
    assert re.search(r"derived_heat_metric\s+0\s+26\s+26", out)  # 22/152 without it


def test_result_block_table(pipeline):
    expected = {
        "variable_identity": (8, 18, 3), "spatial_reference": (3, 12, 3),
        "temporal_reference": (2, 9, 3), "exposure_model": (0, 11, 1),
        "data_layout": (1, 13, 1), "source_dataset": (5, 18, 1),
        "tool_run": (0, 17, 2), "linkage_method": (0, 21, 1),
    }
    for block, (filled, total, unfilled) in expected.items():
        row = rf"^{block}\s+{filled}\s+{total - filled}\s+{total}\s+{unfilled}"
        assert re.search(row, pipeline["coverage"], re.M), block


def test_result_sixteen_required_gaps(pipeline):
    gaps = pipeline["coverage"].split("cannot supply: ")[1]
    assert gaps.startswith("16")
    assert re.search(r"^\s+subject$", gaps, re.M)


def test_result_validation_errors(pipeline):
    errors = pipeline["errors"]
    assert len(errors) == 17 * 19 + 1
    assert sum("None is not of type 'object'" in e for e in errors) == 1
    assert sum("'shp' is not one of" in e for e in errors) == 19


def test_result_measured_variables(variables, measured):
    assert (len(measured), len(variables)) == (19, 28)


def test_tier_and_required_partition(sv):
    """Core tier and LinkML `required` coincide, apart from these exceptions."""
    record = "EnvironmentalExposureRecord"
    mismatched = []
    for block in sv.class_slots(record):
        induced = sv.induced_slot(block, record)
        if induced.range not in sv.all_classes():
            continue
        for name in sv.class_slots(induced.range):
            slot = sv.induced_slot(name, induced.range)
            tier = slot.annotations["tier"].value if "tier" in slot.annotations else None
            required = bool(slot.required and induced.required)
            if (tier == "core") != required:
                mismatched.append(f"{block}.{name}")
    assert mismatched == ["derived_heat_metric.heat_metric_family"]


# ── Finding 1 ─────────────────────────────────────────────────────────────

def test_f1_three_blocks_empty_49_slots(pipeline):
    totals = [
        int(re.search(rf"^{block}\s+0\s+\d+\s+(\d+)", pipeline["coverage"], re.M).group(1))
        for block in ("exposure_model", "tool_run", "linkage_method")
    ]
    assert sum(totals) == 49


def test_f1_subject_comes_from_profile(sv):
    assert sv.induced_slot("subject", "EnvironmentalExposureRecord").required
    local = {s for p in schema_path().parent.glob("envar_*.yaml")
             for s in (yaml.safe_load(p.read_text()).get("slots") or {})}
    assert "subject" not in local


def test_f1_exposure_model_stated_in_prose(meta):
    description = meta["json-ld"]["description"]
    for term in ("MODIS, MISR and SeaWiFS", "Aerosol Optical Depth", "GWR", "population-weighted"):
        assert term in description


def test_f1_transformation_slot_is_todo(meta):
    assert meta["json-ld"]["about"][0]["potentialAction"]["description"] == "TODO"


def test_f1_catalog_carries_its_own_etl_script(meta):
    assert "GDSC ETL" in meta["dcat"]["prov:action"]


def test_f1_rigid_required_slots_have_no_escape(sv):
    for cls, slot, rng in [
        ("SpatialReference", "native_spatial_resolution_m", "float"),
        ("TemporalReference", "day_boundary_convention", None),
    ]:
        induced = sv.induced_slot(slot, cls)
        assert induced.required
        assert rng is None or induced.range == rng
        assert f"{slot}_missing_reason" not in sv.all_slots()
    for slot in ("extraction_buffer_m", "population_weighting_source"):
        assert f"{slot}_missing_reason" in sv.all_slots()


def test_f1_dataset_is_vector_and_annual(meta, measured):
    assert meta["dcat"]["adms:representationTechnique"] == "vector"
    for v in measured:
        assert v["startDate"][4:] == "-01-01" and v["endDate"][4:] == "-12-31"


# ── Finding 2 ─────────────────────────────────────────────────────────────

def test_f2_one_property_id(measured):
    assert {v["propertyID"] for v in measured} == {"2052499839"}


def test_f2_per_year_gaia_ids_outside_jsonld(meta, avpmu_attributes):
    ids = [a.rsplit(";", 1)[1] for a in avpmu_attributes]
    assert ids == [f"gaia-{n}" for n in range(407, 426)]
    for gaia_id in ids:
        assert files_containing(meta, gaia_id) == {"etl", "dcat"}


def test_f2_no_alternate_name(meta):
    assert files_containing(meta, "alternateName") == set()


# ── Finding 3 ─────────────────────────────────────────────────────────────

def test_f3_codes_are_omop_ids(measured):
    assert {v["unitCode"] for v in measured} == {"32964"}
    assert int(measured[0]["propertyID"]) >= 2_000_000_000


def test_f3_slot_requirements(sv):
    assert sv.induced_slot("units_ucum", "VariableIdentity").required
    assert sv.induced_slot("value_data_type", "VariableIdentity").required
    assert not sv.induced_slot("source_license_spdx", "SourceDataset").required


def test_f3_stated_values(meta, measured):
    assert {v["qudt:dataType"] for v in measured} == {"double"}
    assert meta["dcat"]["dct:rights"] == "Public Domain"


# ── Finding 4 ─────────────────────────────────────────────────────────────

def test_f4_versions_are_timestamps(meta, sv):
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", meta["json-ld"]["version"])
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T[\d:]+Z", meta["dcat"]["gdsc:version"])
    assert sv.induced_slot("source_dataset_version", "SourceDataset").required


def test_f4_v1_only_inside_titles(meta):
    def values(node):
        if isinstance(node, dict):
            for v in node.values():
                yield from values(v)
        elif isinstance(node, list):
            for v in node:
                yield from values(v)
        else:
            yield str(node)

    hits = [v for doc in meta.values() for v in values(doc) if re.search(r"\bv1\b", v)]
    assert hits and all(len(v) > len("v1") for v in hits)


# ── Finding 5 ─────────────────────────────────────────────────────────────

def test_f5_etl_and_dcat_duplicate(meta):
    etl, dcat = meta["etl"], meta["dcat"]
    assert etl["source"] == dcat["dcat:downloadURL"]
    assert etl["attributes"] == dcat["gdsc:attributes"]
    assert etl["extent"] == dcat["dcat:bbox"]


def test_f5_jsonld_is_not_a_superset(meta):
    for needle in ("gaia-407", "analyticConformsTo", "local_epsg", "GDSC ETL"):
        assert "json-ld" not in files_containing(meta, needle), needle


# ── Finding 6 ─────────────────────────────────────────────────────────────

def test_f6_format_enum_has_no_vector_format(sv, meta):
    enum = sv.induced_slot("source_native_format", "SourceDataset").range
    assert set(sv.get_enum(enum).permissible_values) == {
        "netcdf4_cf", "hdf5", "geotiff", "grib1", "grib2",
        "csv_station_observations", "zarr", "parquet",
    }
    assert meta["etl"]["format"] == "shp"


# ── Finding 7 ─────────────────────────────────────────────────────────────

def test_f7_crs_stated_five_times(meta):
    dcat, etl, jsonld = meta["dcat"], meta["etl"], meta["json-ld"]
    srs = [p["value"] for p in jsonld["additionalProperty"] if p["propertyID"].endswith("Spatial_reference_system")]
    assert [dcat["dct:conformsTo"], srs, etl["epsg"]] == ["EPSG:4326", ["https://epsg.io/4326"], "EPSG:4326"]
    assert [dcat["gdsc:analyticConformsTo"], etl["local_epsg"]] == ["EPSG:3857", "EPSG:3857"]


def test_f7_bbox_agrees_three_times(meta):
    def coords(text: str) -> list[float]:
        return [float(x) for x in re.findall(r"-?\d+\.\d+", text)]

    polygon = next(p["geo"]["polygon"] for p in meta["json-ld"]["spatialCoverage"] if "geo" in p)
    assert coords(polygon) == coords(meta["dcat"]["dcat:bbox"]) == coords(meta["etl"]["extent"])


def test_f7_transform_takes_conforms_to(pipeline):
    for record in pipeline["records"]:
        assert "EPSG:4326" in json.dumps(record["spatial_reference"])
