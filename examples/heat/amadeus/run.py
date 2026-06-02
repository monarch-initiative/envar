#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "pyyaml>=6.0"]
# ///
"""
run.py — Amadeus-equivalent GridMET (METDATA) Tmmx extraction in Python.

We're not running the R `amadeus` package directly; instead we call the *same*
underlying data service — the Northwest Knowledge Network THREDDS NCSS
endpoint — that `amadeus::download_data("gridmet", variables = "tmmx")` followed
by `amadeus::calculate_covariates("gridmet", ...)` reaches. Output schema
mirrors what the R pipeline would emit, with the EnVar provenance sidecar
declaring the *methodological* differences vs Daymet (statistical_blend vs
spatial_interpolation, 4 km vs 1 km, nearest_cell vs IDW, etc).

CRITICAL packing convention
---------------------------
The CSV that THREDDS NCSS returns is **packed**: the values are int16 with
`scale_factor = 0.1` and `add_offset = 220.0` applied. The CSV header still
says `[unit="K"]` even though the raw value is *not* Kelvin. The true Kelvin
value is `raw * scale_factor + add_offset`. Verified for GridMET tmmx:
on 2022-07-19 at (33.4485, -112.0738) the raw value is 958, which unpacks
to 315.8 K = 42.65 °C. If you skip the unpack step the numbers are
nonsensical (~1000 K). The OPeNDAP endpoint at /thredds/dodsC/... auto-unpacks
via xarray/netCDF4, but adding those deps is heavier than the two-line unpack.

Outputs
-------
Native artefacts (what the amadeus + GridMET ecosystem already produces today):

- outputs/gridmet_tmmx.csv               — one row per (person × day), K + °C
- outputs/gridmet_tmmx.attributes.json   — the R-attribute-style metadata the
                                            amadeus object would carry in
                                            ``attributes(x)`` if serialized
- outputs/gridmet_tmmx.cf_metadata.json  — CF Conventions metadata that ships
                                            in the GridMET NetCDF (fetched
                                            from the THREDDS dataset.xml
                                            endpoint, normalised to JSON)
- outputs/thredds_response_headers.json  — HTTP response headers from one
                                            THREDDS NCSS call
- outputs/NATIVE_METADATA.md             — narrative: what is native vs what
                                            EnVar adds

EnVar additions (what the sidecar contributes on top):

- outputs/envar/gridmet_tmmx.provenance.yaml — EnVar sidecar
- outputs/envar/README.md                    — why this is here, format choice
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml


ENVAR_AMADEUS_IMAGE = "envar-amadeus:4.4"
R_AMADEUS_SCRIPT = "amadeus_extract.R"


# ----------------------------------------------------------------- constants

THREDDS_NCSS = (
    "http://thredds.northwestknowledge.net:8080/thredds/ncss/"
    "agg_met_tmmx_1979_CurrentYear_CONUS.nc"
)
THREDDS_DATASET_XML = THREDDS_NCSS + "/dataset.xml"

R_VERSION_STRING = "R version 4.4.0 (2024-04-24)"

# GridMET tmmx packing — see module docstring.
SCALE_FACTOR = 0.1
ADD_OFFSET = 220.0
K_TO_C = 273.15

HTTP_TIMEOUT_S = 60.0
AMADEUS_VERSION = "1.2.0"
TOOL_NAME = "amadeus"

# Crockford base32 alphabet for ULID-shaped IDs.
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


# ----------------------------------------------------------------- helpers

def ulid_like(seed: bytes) -> str:
    """Build a 26-char Crockford-base32 string. Deterministic given `seed`.

    Not a real ULID (no millisecond prefix); shaped like one so it looks the
    same in downstream OMOP exposure_source_value rows.
    """
    digest = hashlib.sha256(seed).digest()
    # Take 130 bits (26 chars * 5 bits) from the digest, MSB-first.
    n = int.from_bytes(digest[:17], "big")
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[n & 0x1F])
        n >>= 5
    return "".join(reversed(chars))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def worst_precision(patients: list[dict]) -> str:
    """Pick the coarsest geocoding precision across the cohort.

    Order (best → worst): rooftop, range, street, zip, city, state, unknown.
    """
    order = ["rooftop", "range", "street", "zip", "city", "state", "unknown"]
    rank = {p: i for i, p in enumerate(order)}
    worst = -1
    worst_label = "unknown"
    for pat in patients:
        prec = pat.get("geocoded", {}).get("precision", "unknown")
        r = rank.get(prec, len(order) - 1)
        if r > worst:
            worst = r
            worst_label = prec
    return worst_label


# ---------------------------------------------- THREDDS CF metadata + headers

def _xml_attrs_to_dict(elem: ET.Element) -> dict:
    """Convert a `<grid>` / `<axis>` XML element's child <attribute> tags to dict.

    THREDDS dataset.xml encodes CF attributes like:
        <attribute name="standard_name" value="time" />
        <attribute name="scale_factor" type="double" value="0.1" />
    We preserve `name`, `value`, and `type` when present.
    """
    out: dict = {}
    for child in elem.findall("attribute"):
        name = child.get("name")
        if name is None:
            continue
        entry: dict = {"value": child.get("value")}
        t = child.get("type")
        if t is not None:
            entry["type"] = t
        # If there's a single attribute repeated, last one wins (fine for CF).
        out[name] = entry
    return out


def fetch_cf_metadata(
    *, client: httpx.Client, fixtures_dir: Path, offline: bool,
) -> tuple[dict, dict]:
    """Return (cf_metadata_dict, response_headers_dict).

    Pulls the THREDDS dataset.xml, which surfaces the same CF Conventions
    attributes that ship in the underlying GridMET NetCDF (standard_name,
    units, _FillValue, scale_factor, add_offset, grid_mapping, calendar, ...).
    Cached as a fixture so ``ENVAR_OFFLINE=1`` runs work.
    """
    fixture_xml = fixtures_dir / "thredds_dataset.xml"
    fixture_hdr = fixtures_dir / "thredds_dataset_headers.json"

    if offline:
        if not fixture_xml.exists() or not fixture_hdr.exists():
            raise FileNotFoundError(
                f"ENVAR_OFFLINE=1 but missing CF fixture(s) at "
                f"{fixture_xml} / {fixture_hdr}. Run online once to populate."
            )
        body = fixture_xml.read_text()
        headers = json.loads(fixture_hdr.read_text())
    else:
        r = client.get(THREDDS_DATASET_XML, timeout=HTTP_TIMEOUT_S)
        if r.status_code != 200:
            raise RuntimeError(
                f"THREDDS dataset.xml returned HTTP {r.status_code}: "
                f"{r.text[:200]}"
            )
        body = r.text
        # Filter to provenance-relevant headers (drop cookies, set-cookie, auth).
        headers = {
            k: v for k, v in r.headers.items()
            if k.lower() not in {"set-cookie", "cookie", "authorization"}
        }
        fixtures_dir.mkdir(parents=True, exist_ok=True)
        fixture_xml.write_text(body)
        fixture_hdr.write_text(json.dumps(headers, indent=2, sort_keys=True))

    # Parse the XML into a structured CF dict.
    root = ET.fromstring(body)

    cf: dict = {
        "source": {
            "endpoint": THREDDS_DATASET_XML,
            "format": "THREDDS NCSS dataset.xml (NcML-like)",
            "fetched_utc": datetime.now(timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "dataset_location": root.get("location"),
        "axes": {},
        "variables": {},
        "lat_lon_box": {},
        "time_span": {},
    }

    for axis in root.findall("axis"):
        name = axis.get("name") or "unknown"
        cf["axes"][name] = {
            "shape": axis.get("shape"),
            "type": axis.get("type"),
            "axisType": axis.get("axisType"),
            "attributes": _xml_attrs_to_dict(axis),
        }

    for gs in root.findall("gridSet"):
        for grid in gs.findall("grid"):
            gname = grid.get("name") or "unknown"
            cf["variables"][gname] = {
                "shape": grid.get("shape"),
                "type": grid.get("type"),
                "desc": grid.get("desc"),
                "attributes": _xml_attrs_to_dict(grid),
            }

    llb = root.find("LatLonBox")
    if llb is not None:
        cf["lat_lon_box"] = {c.tag: c.text for c in llb}
    ts = root.find("TimeSpan")
    if ts is not None:
        cf["time_span"] = {c.tag: c.text for c in ts}

    return cf, headers


# ------------------------------------------------------------- THREDDS call

def fetch_gridmet_tmmx_csv(
    *, lat: float, lon: float, start: str, end: str, client: httpx.Client,
    fixtures_dir: Path, offline: bool, person_loc_id: str,
) -> tuple[str, dict | None]:
    """Return ``(csv_body, response_headers_or_None)`` from THREDDS NCSS.

    Fixture filenames are ``gridmet_tmmx_{person_loc_id}_{start}_{end}.csv``.
    Headers are only returned when we actually hit the network; offline runs
    get ``None`` and fall back to a cached headers fixture saved alongside.
    """
    fixture = fixtures_dir / f"gridmet_tmmx_{person_loc_id}_{start}_{end}.csv"
    if offline:
        if not fixture.exists():
            raise FileNotFoundError(
                f"ENVAR_OFFLINE=1 but no fixture at {fixture}. "
                f"Run online once to populate fixtures/."
            )
        return fixture.read_text(), None

    params = {
        "var": "daily_maximum_temperature",
        "latitude": f"{lat}",
        "longitude": f"{lon}",
        "time_start": f"{start}T00:00:00Z",
        "time_end": f"{end}T00:00:00Z",
        "accept": "csv",
    }
    # One retry on 5xx / transient network errors.
    last_exc: Exception | None = None
    for attempt in (1, 2, 3):
        try:
            r = client.get(THREDDS_NCSS, params=params, timeout=HTTP_TIMEOUT_S)
            if r.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"THREDDS {r.status_code}", request=r.request, response=r,
                )
            if r.status_code != 200:
                raise RuntimeError(
                    f"THREDDS NCSS returned HTTP {r.status_code} for "
                    f"({lat},{lon}) {start}..{end}: {r.text[:200]}"
                )
            body = r.text
            response_headers = {
                k: v for k, v in r.headers.items()
                if k.lower() not in {"set-cookie", "cookie", "authorization"}
            }
            break
        except (httpx.HTTPError, RuntimeError) as e:
            last_exc = e
            if attempt == 3:
                raise RuntimeError(
                    f"THREDDS NCSS failed after 3 attempts for ({lat},{lon}) "
                    f"{start}..{end}: {e}"
                ) from e
            time.sleep(2 * attempt)
    else:
        raise RuntimeError(f"unreachable: {last_exc}")

    # Cache the response so future ENVAR_OFFLINE=1 runs work.
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    fixture.write_text(body)
    return body, response_headers


def parse_packed_tmmx_csv(body: str) -> list[tuple[str, float, float, float]]:
    """Parse the THREDDS NCSS CSV body. Return [(date, lat, lon, raw)].

    Header looks like:
        time,latitude[unit="degrees_north"],longitude[unit="degrees_east"],daily_maximum_temperature[unit="K"]
    Data row:
        2022-07-19T00:00:00Z,33.4485,-112.0738,958.0
    """
    rows: list[tuple[str, float, float, float]] = []
    reader = csv.reader(io.StringIO(body))
    header = next(reader, None)
    if header is None or len(header) < 4:
        raise ValueError(f"unexpected THREDDS NCSS response (no header): {body[:200]!r}")
    for rec in reader:
        if not rec or not rec[0].strip():
            continue
        ts, lat_s, lon_s, raw_s = rec[0], rec[1], rec[2], rec[3]
        date = ts.split("T", 1)[0]
        rows.append((date, float(lat_s), float(lon_s), float(raw_s)))
    return rows


# ----------------------------------------------------------------- main

def _have_envar_amadeus_image() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        out = subprocess.check_output(
            ["docker", "inspect", "--format", "{{.Id}}", ENVAR_AMADEUS_IMAGE],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return bool(out)
    except subprocess.CalledProcessError:
        return False


def try_real_r_amadeus(here: Path, inputs_csv: Path, out_dir: Path) -> dict | None:
    """Run the REAL amadeus R package inside the envar-amadeus:4.4 container.

    Returns a dict with keys {rows, attributes, session, run_meta, image_digest}
    on success, or None if the image isn't present or the run fails. The image
    is built from this folder's Dockerfile: `docker build -t envar-amadeus:4.4 .`
    """
    if not _have_envar_amadeus_image():
        print(f"  envar-amadeus image not built (run: docker build -t {ENVAR_AMADEUS_IMAGE} .)")
        return None

    script = here / R_AMADEUS_SCRIPT
    if not script.exists():
        print(f"  missing R script: {script}")
        return None

    print(f"  running {ENVAR_AMADEUS_IMAGE} → {R_AMADEUS_SCRIPT} ...")
    cmd = [
        "docker", "run", "--rm", "--platform", "linux/amd64",
        "-v", f"{here}:/work", "-w", "/work",
        ENVAR_AMADEUS_IMAGE,
        "Rscript", R_AMADEUS_SCRIPT,
        "inputs/patient_locations.csv", "outputs/",
    ]
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as e:
        print(f"  R amadeus container exited non-zero: {e}; falling back to Python.")
        return None

    raw_csv = out_dir / "_amadeus_raw.csv"
    attrs_json = out_dir / "_amadeus_attributes.json"
    session_json = out_dir / "_amadeus_session.json"
    run_meta_json = out_dir / "_amadeus_run_meta.json"
    if not raw_csv.exists():
        print(f"  expected {raw_csv} not produced; falling back.")
        return None

    rows: list[dict] = []
    with raw_csv.open() as fh:
        for r in csv.DictReader(fh):
            rows.append({
                "person_id": r["person_id"],
                "date": r["date"],
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
                "value_kelvin": float(r["value_kelvin"]),
                "value_celsius": float(r["value_celsius"]),
            })

    image_digest = ""
    try:
        image_digest = subprocess.check_output(
            ["docker", "inspect", "--format", "{{.Id}}", ENVAR_AMADEUS_IMAGE],
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        pass

    return {
        "rows": rows,
        "attributes": json.loads(attrs_json.read_text()) if attrs_json.exists() else None,
        "session": json.loads(session_json.read_text()) if session_json.exists() else None,
        "run_meta": json.loads(run_meta_json.read_text()) if run_meta_json.exists() else None,
        "image_digest": image_digest,
    }


def main() -> int:
    here = Path(__file__).resolve().parent
    inputs_csv = here / "inputs" / "patient_locations.csv"
    out_dir = here / "outputs"
    envar_dir = out_dir / "envar"
    fixtures_dir = here / "fixtures"
    out_csv = out_dir / "gridmet_tmmx.csv"
    out_attrs = out_dir / "gridmet_tmmx.attributes.json"
    out_cf = out_dir / "gridmet_tmmx.cf_metadata.json"
    out_headers = out_dir / "thredds_response_headers.json"
    out_yaml = envar_dir / "gridmet_tmmx.provenance.yaml"

    # The patient JSON lives one level up from amadeus/ in the canonical layout.
    patient_json = here.parent / "data" / "patients_example1.json"
    if not patient_json.exists():
        raise FileNotFoundError(f"missing canonical input JSON: {patient_json}")
    if not inputs_csv.exists():
        raise FileNotFoundError(
            f"missing {inputs_csv}. Run translate.py first."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    envar_dir.mkdir(parents=True, exist_ok=True)

    with patient_json.open() as fh:
        doc = json.load(fh)
    window = doc["study_window"]
    start = window["start"]
    end = window["end"]
    patients = doc["patients"]
    precision = worst_precision(patients)

    # Load the translated locations table.
    locs: list[dict] = []
    with inputs_csv.open() as fh:
        for rec in csv.DictReader(fh):
            locs.append({
                "person_loc_id": rec["person_loc_id"],
                "lat": float(rec["lat"]),
                "lon": float(rec["lon"]),
                "start_date": rec["start_date"],
                "end_date": rec["end_date"],
            })

    offline = os.environ.get("ENVAR_OFFLINE", "") == "1"
    force_python = os.environ.get("ENVAR_FORCE_PYTHON", "") == "1"

    rows_out: list[dict] = []
    first_ncss_headers: dict | None = None
    first_ncss_url: str | None = None
    cf_metadata: dict | None = None
    cf_headers: dict | None = None
    execution_mode = ""
    r_amadeus_meta: dict | None = None
    r_amadeus_digest: str = ""

    # Step 0: try the REAL R amadeus container if it's been built.
    # Skipped when offline (no NetCDF download) or ENVAR_FORCE_PYTHON=1.
    if not offline and not force_python:
        print(
            f"amadeus/run.py: trying REAL R amadeus via {ENVAR_AMADEUS_IMAGE} ..."
        )
        r_result = try_real_r_amadeus(here, inputs_csv, out_dir)
        if r_result is not None:
            rows_out = r_result["rows"]
            r_amadeus_meta = r_result
            r_amadeus_digest = r_result.get("image_digest", "")
            execution_mode = "real_amadeus_download_real_terra_extract"
            print(
                f"  REAL R amadeus produced {len(rows_out)} rows. "
                f"execution_mode={execution_mode}"
            )

    if not rows_out:
        execution_mode = "python_thredds_equivalent"
        print(
            f"amadeus/run.py: {'OFFLINE (fixtures)' if offline else 'ONLINE (Python THREDDS NCSS)'} "
            f"— {len(locs)} locations × window {start}..{end} — "
            f"execution_mode={execution_mode}"
        )

    with httpx.Client(headers={"User-Agent": "envar-heat-example/0.1"}) as client:
        # CF Conventions metadata from the THREDDS dataset.xml endpoint. This
        # is the metadata the GridMET NetCDF *already ships* — amadeus reads
        # it via terra::metags() but doesn't externalise it. Always fetch this
        # because it's small and the OMOP step / sidecar diff downstream
        # consume it.
        cf_metadata, cf_headers = fetch_cf_metadata(
            client=client, fixtures_dir=fixtures_dir, offline=offline,
        )

        # Skip the Python THREDDS extraction loop when the real R amadeus
        # already produced the rows.
        for loc in (locs if execution_mode == "python_thredds_equivalent" else []):
            body, hdrs = fetch_gridmet_tmmx_csv(
                lat=loc["lat"],
                lon=loc["lon"],
                start=loc["start_date"],
                end=loc["end_date"],
                client=client,
                fixtures_dir=fixtures_dir,
                offline=offline,
                person_loc_id=loc["person_loc_id"],
            )
            if first_ncss_headers is None and hdrs is not None:
                first_ncss_headers = hdrs
                first_ncss_url = (
                    f"{THREDDS_NCSS}?var=daily_maximum_temperature"
                    f"&latitude={loc['lat']}&longitude={loc['lon']}"
                    f"&time_start={loc['start_date']}T00:00:00Z"
                    f"&time_end={loc['end_date']}T00:00:00Z&accept=csv"
                )
            for date, lat_g, lon_g, raw in parse_packed_tmmx_csv(body):
                kelvin = raw * SCALE_FACTOR + ADD_OFFSET
                celsius = kelvin - K_TO_C
                rows_out.append({
                    "person_id": loc["person_loc_id"],
                    "date": date,
                    "lat": lat_g,
                    "lon": lon_g,
                    "value_kelvin": round(kelvin, 4),
                    "value_celsius": round(celsius, 4),
                })

    # Write data CSV.
    with out_csv.open("w", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["person_id", "date", "lat", "lon", "value_kelvin", "value_celsius"],
        )
        w.writeheader()
        for r in rows_out:
            w.writerow(r)
    print(f"wrote {out_csv} ({len(rows_out)} rows)")

    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ------------------- native artefact 1: CF metadata -------------------
    # This is the slice of the GridMET NetCDF's CF-Conventions header that
    # the THREDDS server surfaces via dataset.xml. amadeus + terra would
    # expose the same key/value pairs in-memory; we just write them down.
    with out_cf.open("w") as fh:
        json.dump(cf_metadata, fh, indent=2, sort_keys=True)
    print(f"wrote {out_cf}")

    # ------------------- native artefact 2: NCSS response headers ----------
    # Capture from one NCSS call. Cache to fixtures/ so ENVAR_OFFLINE=1 works.
    ncss_headers_fixture = fixtures_dir / "thredds_ncss_response_headers.json"
    if first_ncss_headers is None:
        # Offline run: load the cached headers from the previous online run.
        if ncss_headers_fixture.exists():
            first_ncss_headers = json.loads(ncss_headers_fixture.read_text())
            first_ncss_url = "(cached from previous online run)"
        else:
            # Fall back to the dataset.xml call's headers; same THREDDS server.
            first_ncss_headers = cf_headers or {}
            first_ncss_url = "(fallback: dataset.xml call headers)"
    else:
        fixtures_dir.mkdir(parents=True, exist_ok=True)
        ncss_headers_fixture.write_text(
            json.dumps(first_ncss_headers, indent=2, sort_keys=True)
        )
    ncss_headers_doc = {
        "captured_from_url": first_ncss_url,
        "captured_utc": run_ts,
        "thredds_server_software": (
            first_ncss_headers.get("Server")
            or first_ncss_headers.get("server")
        ),
        "headers": first_ncss_headers,
        "note": (
            "Per-request response headers from one THREDDS NCSS call. "
            "All NCSS calls against this endpoint return structurally "
            "identical headers; the per-call Date/Content-Length vary. "
            "Cookies / Set-Cookie / Authorization are stripped."
        ),
    }
    with out_headers.open("w") as fh:
        json.dump(ncss_headers_doc, fh, indent=2, sort_keys=True)
    print(f"wrote {out_headers}")

    # ------------------- native artefact 3: R-attribute-style metadata -----
    # This mimics what `attributes(amadeus_result)` would contain in R if you
    # serialised it. amadeus surfaces `call`, `package_version`, `datetime`
    # via `attr(x, ...)`; the column names + class match a data.frame return.
    r_call = (
        'amadeus::calculate_covariates("gridmet", from = rast, '
        'locs = patient_pts_sf, locs_id = "person_loc_id", '
        '.by_time = "day", geom = FALSE)'
    )
    attrs_doc = {
        "names": [
            "person_id", "date", "lat", "lon",
            "value_kelvin", "value_celsius",
        ],
        "class": ["data.frame"],
        # In R this is the integer row.names vector. We elide the middle.
        "row.names": [1, "...", len(rows_out)],
        "call": r_call,
        "package_version": f"{TOOL_NAME} {AMADEUS_VERSION}",
        "r_version": R_VERSION_STRING,
        "datetime_run_utc": run_ts,
        "thredds_url_queried": THREDDS_NCSS,
        "input_locations_n": len(locs),
        "input_dates_n": (
            len({r["date"] for r in rows_out}) if rows_out else 0
        ),
        "output_rows": len(rows_out),
    }
    with out_attrs.open("w") as fh:
        json.dump(attrs_doc, fh, indent=2, sort_keys=False)
    print(f"wrote {out_attrs}")

    # ------------------- provenance sidecar (EnVar addition) ---------------
    input_sha = sha256_file(inputs_csv)
    output_sha = sha256_file(out_csv)

    # Deterministic provenance_id: hash inputs + tool + version + run timestamp.
    pid_seed = (
        f"{TOOL_NAME}|{AMADEUS_VERSION}|gridmet|tmmx|{input_sha}|{run_ts}"
    ).encode()
    pid_core = ulid_like(pid_seed)
    provenance_id = f"{pid_core}-gridmet"

    sidecar = {
        "provenance_id": provenance_id,
        "variable": {
            "name": "tmmx",
            "cf_standard_name": "air_temperature",
            "cf_cell_methods": "time: maximum",
            "units_ucum": "Cel",
            "units": {
                "native_units_ucum": "K",
                "output_units_ucum": "Cel",
                "unit_conversion": "subtract 273.15",
            },
        },
        "spatial": {
            "native_spatial_resolution_m": 4000,
            "crs": "EPSG:4326",
            "extraction_method": "nearest_cell",
            "target_geography_type": "point_residence",
        },
        "temporal": {
            "temporal_resolution": "daily",
            "temporal_aggregation_method": "maximum",
            "day_boundary_convention": "local_midnight",
            "calendar": "gregorian",
            "extraction_window_start": start,
            "extraction_window_end": end,
        },
        "source_dataset": {
            "name": "gridMET (METDATA)",
            "short_code": "gridmet",
            "doi": "10.1002/joc.3413",
            "version": "current",
            "producer_institution": "University of Idaho Climatology Lab",
            "license_spdx": "CC0-1.0",
            "native_format": "NetCDF-4_CF",
            "access_url": "https://www.climatologylab.org/gridmet.html",
        },
        "exposure_model": {
            "type": "statistical_blend",
            "inputs": ["PRISM monthly normals", "NLDAS-2 sub-daily reanalysis"],
        },
        "linkage": {
            "strategy": "point_extraction_at_residence",
            "geocoding_precision_propagated": precision,
            "address_period_alignment": "address_history_from_emr",
        },
        "tool_run": {
            "tool_name": TOOL_NAME,
            "tool_version": (
                r_amadeus_meta["run_meta"]["amadeus_version"]
                if (r_amadeus_meta and r_amadeus_meta.get("run_meta"))
                else AMADEUS_VERSION
            ),
            "execution_mode": execution_mode,
            "_execution_mode_note": (
                (
                    "REAL amadeus R package run inside the envar-amadeus:4.4 "
                    "Docker image (extends rocker/geospatial:4.4). "
                    "amadeus::download_data('gridmet', variables='tmmx') "
                    "fetches the actual GridMET NetCDF; terra::rast + "
                    "terra::time + terra::extract performs the per-point "
                    "extraction. The single buggy glue function "
                    "amadeus::process_gridmet() is bypassed because it crashes "
                    "on current GridMET layer names — see "
                    "outputs/_amadeus_run_meta.json for details."
                )
                if execution_mode == "real_amadeus_download_real_terra_extract"
                else (
                    "Python implementation that hits the same Northwest "
                    "Knowledge Network THREDDS NCSS endpoint the amadeus R "
                    "package's download_data('gridmet') + calculate_covariates() "
                    "chain would reach. Same GridMET V4 data, same packing "
                    "convention, same extraction point. Build the "
                    f"{ENVAR_AMADEUS_IMAGE} image (see Dockerfile) to switch "
                    "to the real R/amadeus/terra path."
                )
            ),
            "container_image_repository": (
                "envar-amadeus"
                if execution_mode == "real_amadeus_download_real_terra_extract"
                else None
            ),
            "container_image_tag": (
                "4.4"
                if execution_mode == "real_amadeus_download_real_terra_extract"
                else None
            ),
            "container_image_digest": (r_amadeus_digest or None),
            "run_timestamp_utc": run_ts,
            "input_file": str(inputs_csv.relative_to(here)),
            "input_file_sha256": input_sha,
            "input_row_count": len(locs),
            "output_file": str(out_csv.relative_to(here)),
            "output_file_sha256": output_sha,
            "output_row_count": len(rows_out),
            "r_package_call": (
                'amadeus::calculate_covariates("gridmet", '
                'locs = patient_locations, variables = "tmmx", '
                f'date_start = "{start}", date_end = "{end}")'
            ),
            "data_endpoint": THREDDS_NCSS,
            "packing": {
                "scale_factor": SCALE_FACTOR,
                "add_offset": ADD_OFFSET,
                "note": (
                    "THREDDS NCSS CSV returns packed int values; header "
                    "advertises K but the value must be unpacked as "
                    "raw * scale_factor + add_offset to get Kelvin."
                ),
            },
        },
        "provenance_chain": [],
    }

    with out_yaml.open("w") as fh:
        yaml.safe_dump(sidecar, fh, sort_keys=False, default_flow_style=False)
    print(f"wrote {out_yaml}")

    # Report the demo number.
    for r in rows_out:
        if r["person_id"] == "91204" and r["date"] == "2022-07-19":
            print(
                f"person 91204 / 2022-07-19: "
                f"value_kelvin={r['value_kelvin']} K, "
                f"value_celsius={r['value_celsius']} °C"
            )
            break

    return 0


if __name__ == "__main__":
    sys.exit(main())
