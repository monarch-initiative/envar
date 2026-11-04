#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "h3>=4.1", "pyyaml>=6.0"]
# ///
"""
run.py — link the heat cohort to CHEL's extreme heat days, two ways.

CHEL (CLAD Hex Environmental Linkage, cladteam/CHEL) publishes CDC/ATSDR
Environmental Justice Index variables re-expressed on the H3 resolution-3
grid. The 2024 release carries ``E_NEHD``, the annual mean number of extreme
heat days over 2018-2022 (EJI climate burden module). That window is the heat
cohort's observation window, so it is the CHEL variable this scenario needs.

The AMIA 2026 RWD workshop (rwdcollaborative/amia-2026-rwd-workshop) gives
every synthetic OMOP person an H3 res-3 hexagon through their *county*:
county FIPS -> one hexagon per county (``staging/data/h3res3_countyfips_cw.csv``).
Its hexagon notebook stops one join short of CHEL. This script makes that join
for the heat cohort, by two routes:

- ``point``  — the residence coordinate is indexed to the res-3 cell that
               contains it (``h3.latlng_to_cell``).
- ``county`` — the workshop route: residence -> county FIPS (FCC Census Area
               API) -> the hexagon the workshop crosswalk assigns that county.

Both routes then join CHEL 2024 on ``h3_id`` (not CHEL's local ``hex_id``),
map CHEL's ``-999`` sentinel to NULL, and emit:

- outputs/chel_nehd_{point,county}.csv — one row per person and route, with the
                                     hexagon, county, value and the release
                                     the CHEL README's enrollment-year rule
                                     would have picked
- outputs/external_exposure.csv    — the same values in OMOP
                                     ``external_exposure`` shape (CONTRACT.md)
- outputs/run_manifest.json        — pinned inputs, sha256s, counts, checks
- outputs/envar/chel_nehd_{point,county}.provenance.yaml — EnVar sidecars

Inputs are fetched from GitHub at pinned commits and cached under ``.cache/``
(gitignored: neither upstream repo carries a licence, so their files are not
redistributed here). ``ENVAR_OFFLINE=1`` runs from that cache only.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import h3
import httpx
import yaml


# ----------------------------------------------------------------- constants

CHEL_REPO = "cladteam/CHEL"
CHEL_COMMIT = "4dd219e256ba664a9151d4d8d7aefac65ef2ce28"
CHEL_FILE = "data/CHEL_hex3_2024.csv"
CHEL_RELEASE = "2024"

WORKSHOP_REPO = "rwdcollaborative/amia-2026-rwd-workshop"
WORKSHOP_COMMIT = "cf3a05c61c88b3724f33d5bcef04d8a5c1923cc8"
WORKSHOP_CROSSWALK = "staging/data/h3res3_countyfips_cw.csv"

FCC_AREA_API = "https://geo.fcc.gov/api/census/area"
FCC_CENSUS_YEAR = "2020"

H3_RESOLUTION = 3
VARIABLE = "E_NEHD"
PERCENTILE_VARIABLE = "EPL_NEHD"
SENTINEL_NO_DATA = -999.0

# EJI 2024 climate burden module: "the annual mean number of extreme heat
# days, using data from 2018-2022", sourced from the CDC National
# Environmental Public Health Tracking Network.
EJI_NEHD_PAGE = (
    "https://atsdr.cdc.gov/place-health/php/eji/"
    "eji-indicators-climate-burden-module.html"
)
NEHD_COVERAGE_START = "2018-01-01"
NEHD_COVERAGE_END = "2022-12-31"

UNIT_CONCEPT_ID_DAY = 8512                # UCUM "d"
EXPOSURE_TYPE_CONCEPT_ID = 32885          # "derived environmental estimate"
EXPOSURE_CONCEPT_VALUE = "proposed:annual-mean-extreme-heat-days"

TOOL_NAME = "envar-chel-linkage"
TOOL_VERSION = "0.1.0"
HTTP_TIMEOUT_S = 60.0

ROUTES = ("point", "county")

# Crockford base32 alphabet for ULID-shaped IDs (same scheme as amadeus/).
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


# ----------------------------------------------------------------- helpers

def ulid_like(seed: bytes) -> str:
    """26-char Crockford-base32 string, deterministic given ``seed``."""
    n = int.from_bytes(hashlib.sha256(seed).digest()[:17], "big")
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[n & 0x1F])
        n >>= 5
    return "".join(reversed(chars))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def raw_url(repo: str, commit: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{commit}/{path}"


def get_with_retry(client: httpx.Client, url: str, params: dict | None = None) -> httpx.Response:
    """GET with three attempts on 5xx / transport errors; fail loudly otherwise."""
    for attempt in (1, 2, 3):
        try:
            r = client.get(url, params=params, timeout=HTTP_TIMEOUT_S)
            if r.status_code >= 500:
                raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
            if r.status_code != 200:
                raise RuntimeError(f"{url} returned HTTP {r.status_code}: {r.text[:200]}")
            return r
        except httpx.HTTPError as e:
            if attempt == 3:
                raise RuntimeError(f"{url} failed after 3 attempts: {e}") from e
            time.sleep(2 * attempt)
    raise RuntimeError("unreachable")


def fetch_cached(client: httpx.Client, url: str, cache: Path, offline: bool) -> bytes:
    """Return the bytes at ``url``, caching them at ``cache``."""
    if offline:
        if not cache.exists():
            raise FileNotFoundError(f"ENVAR_OFFLINE=1 but {cache} is not cached. Run online once.")
        return cache.read_bytes()
    body = get_with_retry(client, url).content
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(body)
    return body


def county_fips(client: httpx.Client, person_id: str, lat: float, lon: float,
                cache_dir: Path, offline: bool) -> tuple[str, str]:
    """Residence point -> (county FIPS, county name) via the FCC Census Area API.

    The API returns every 2020 census block touching the point; a point on a
    block boundary returns two. They must all agree on the county.
    """
    cache = cache_dir / f"fcc_area_{person_id}.json"
    if offline:
        if not cache.exists():
            raise FileNotFoundError(f"ENVAR_OFFLINE=1 but {cache} is not cached. Run online once.")
        doc = json.loads(cache.read_text())
    else:
        params = {"lat": lat, "lon": lon, "censusYear": FCC_CENSUS_YEAR, "format": "json"}
        doc = get_with_retry(client, FCC_AREA_API, params=params).json()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(doc, indent=2, sort_keys=True))
    counties = {(b["county_fips"], b["county_name"]) for b in doc.get("results", [])}
    if len(counties) != 1:
        raise RuntimeError(f"person {person_id}: expected one county at ({lat},{lon}), got {counties}")
    return counties.pop()


# ------------------------------------------------------------- CHEL + crosswalk

def load_chel(body: bytes) -> dict[str, dict]:
    """CHEL 2024 rows keyed by ``h3_id``.

    The header starts with a UTF-8 BOM (``utf-8-sig`` strips it), and
    ``-999`` / ``-999.0`` is CHEL's no-data sentinel: both map to None.
    """
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))
    if "hex_id" not in rows[0]:
        raise RuntimeError("CHEL header has no hex_id column: BOM not stripped?")
    out: dict[str, dict] = {}
    for row in rows:
        if row["h3_id"] in out:
            raise RuntimeError(f"CHEL h3_id {row['h3_id']} is not unique")
        out[row["h3_id"]] = row
    return out


def chel_value(row: dict | None, column: str) -> float | None:
    if row is None or row.get(column) in (None, ""):
        return None
    value = float(row[column])
    return None if value == SENTINEL_NO_DATA else value


def load_crosswalk(body: bytes) -> dict[str, str]:
    """Workshop crosswalk: county FIPS -> the single H3 res-3 hexagon assigned to it.

    The workshop's ``build_location()`` takes ``ANY_VALUE(h3_id)`` per county;
    that is only safe if every county has exactly one hexagon, so check it.
    """
    by_county: dict[str, set[str]] = {}
    for row in csv.DictReader(io.StringIO(body.decode("utf-8-sig"))):
        if row["county"]:
            by_county.setdefault(row["county"], set()).add(row["h3_id"])
    ambiguous = {c: h for c, h in by_county.items() if len(h) != 1}
    if ambiguous:
        raise RuntimeError(f"crosswalk counties with more than one hexagon: {ambiguous}")
    return {c: h.pop() for c, h in by_county.items()}


def chel_readme_release(observation_start: str) -> str | None:
    """The release the CHEL README example assigns by enrollment year.

    2015-2018 -> CHEL 2022, 2019-2022 -> CHEL 2024 (README, "Linking
    Participants to Different CHEL Datasets by Year").
    """
    year = int(observation_start[:4])
    if 2015 <= year <= 2018:
        return "2022"
    if 2019 <= year <= 2022:
        return "2024"
    return None


# ----------------------------------------------------------------- sidecar

def build_sidecar(*, route: str, provenance_id: str, run_ts: str, rows: list[dict],
                  inputs: dict, precision: str, min_score: float, out_rel: str, out_sha: str,
                  patients_rel: str, patients_sha: str, n_patients: int) -> dict:
    county = route == "county"
    matched = [r for r in rows if r["value"] is not None]
    linkage = {
        "strategy": "county_assigned_h3_hexagon" if county else "area_membership_residence_in_polygon",
        "geocoding_precision_propagated": precision,
        "geocoding_score_propagated": min_score,
        "address_period_alignment": "single_static_address",
        "path": (
            "residence point -> county FIPS (FCC Census Area API, 2020 blocks) -> "
            "one H3 res-3 hexagon per county (workshop crosswalk) -> CHEL h3_id"
            if county else
            "residence point -> containing H3 res-3 cell (h3.latlng_to_cell) -> CHEL h3_id"
        ),
        "effective_spatial_resolution": "county" if county else "h3_res3_cell",
        "join_key": "h3_id",
        "match": {
            "persons": n_patients,
            "persons_with_hexagon": sum(1 for r in rows if r["h3_id"]),
            "persons_with_value": len(matched),
        },
    }
    if county:
        linkage["assignment_rule"] = (
            "undocumented: the workshop repo does not say how each county's one "
            "hexagon was chosen"
        )
        linkage["crosswalk"] = copy.deepcopy(inputs["workshop_crosswalk"])

    chain = [{
        "step": "chel_release",
        "tool_run": {
            "tool_name": "CHEL (CLAD Foundry pipeline)",
            "tool_version": f"{CHEL_RELEASE} release, {CHEL_REPO}@{CHEL_COMMIT[:7]}",
        },
    }]
    if county:
        chain.append({
            "step": "workshop_county_hexagon_crosswalk",
            "tool_run": {
                "tool_name": "amia-2026-rwd-workshop staging/augment.py build_location()",
                "tool_version": f"{WORKSHOP_REPO}@{WORKSHOP_COMMIT[:7]}",
            },
        })

    return {
        "provenance_id": provenance_id,
        "variable": {
            "name": VARIABLE,
            "label": "Annual mean number of extreme heat days, 2018-2022 (EJI 2024 via CHEL)",
            "units_ucum": "d",
            "value_data_type": "continuous_numeric",
            "concept_status": "gap",
            "definition_source": EJI_NEHD_PAGE,
            "companion_percentile_variable": PERCENTILE_VARIABLE,
        },
        "spatial": {
            "crs": "EPSG:4326",
            "native_spatial_resolution_descriptor": (
                "H3 resolution 3, about 12,000 km2 per cell (CHEL Documentation.md §1.3)"
            ),
            "extraction_method": "area_weighted_polygon_mean",
            "_extraction_method_note": (
                "CHEL's tract-to-hexagon operator, inferred: Documentation.md §2.6 "
                "says climate inputs use area-weighted or intersection-based "
                "aggregation depending on source format, and does not say which "
                "applies to extreme heat days. The person-level step is a lookup "
                "of the hexagon's value; see linkage."
            ),
            "target_geography_type": "h3_hex",
            "spatial_extent_descriptor": (
                f"United States incl. Alaska, Hawaii, Puerto Rico and island territories; "
                f"{inputs['chel']['hexagons']} H3 res-3 cells"
            ),
        },
        "exposure_model": {
            "inputs": [
                "CDC National Environmental Public Health Tracking Network extreme heat days (via EJI 2024)",
            ],
        },
        "temporal": {
            "temporal_resolution": "annual",
            "temporal_aggregation_method": "mean",
            "temporal_coverage_start": NEHD_COVERAGE_START,
            "temporal_coverage_end": NEHD_COVERAGE_END,
            "calendar": "gregorian",
        },
        "source_dataset": {
            "name": "CLAD Hex Environmental Linkage (CHEL) 2024, from CDC/ATSDR Environmental Justice Index 2024",
            "short_code": "chel_2024",
            "version": f"{CHEL_RELEASE} ({CHEL_REPO}@{CHEL_COMMIT[:7]})",
            "producer_institution": "Center for Linkage and Acquisition of Data (CLAD)",
            "license_spdx": "NOASSERTION",
            "access_url": inputs["chel"]["url"],
            "native_format": "CSV",
        },
        "linkage": linkage,
        "null_semantics": {
            "-999": (
                "no data for this hexagon; mapped to NULL. CHEL Documentation.md "
                "§4.3.3 distinguishes structural nulls, derived nulls and true "
                "zeros but does not say which one -999 encodes"
            ),
        },
        "temporal_alignment": {
            "exposure_window": f"{NEHD_COVERAGE_START}..{NEHD_COVERAGE_END}",
            "observation_windows": sorted({f"{r['observation_start']}..{r['observation_end']}" for r in rows}),
            "release_selection": (
                f"CHEL {CHEL_RELEASE} chosen per variable: {VARIABLE} exists only in "
                "the 2024 release. The CHEL README's enrollment-year rule would route "
                "persons enrolled 2015-2018 to CHEL 2022, which has no extreme heat days"
            ),
            "persons_without_value_under_readme_rule": sorted(
                r["person_id"] for r in rows if r["chel_readme_release"] != CHEL_RELEASE
            ),
        },
        "tool_run": {
            "tool_name": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "execution_mode": "real_upstream_files_real_fcc_api",
            "run_timestamp_utc": run_ts,
            "input_file": patients_rel,
            "input_file_sha256": patients_sha,
            "input_row_count": n_patients,
            "output_file": out_rel,
            "output_file_sha256": out_sha,
            "output_row_count": len(rows),
            "run_arguments": f"route={route} variable={VARIABLE} h3_resolution={H3_RESOLUTION}",
            "inputs": copy.deepcopy(inputs),
        },
        "provenance_chain": chain,
    }


# ----------------------------------------------------------------- main

def main() -> int:
    here = Path(__file__).resolve().parent
    cache_dir = here / ".cache"
    out_dir = here / "outputs"
    envar_dir = out_dir / "envar"
    patient_json = here.parent / "data" / "patients_example1.json"
    offline = os.environ.get("ENVAR_OFFLINE", "") == "1"

    out_dir.mkdir(parents=True, exist_ok=True)
    envar_dir.mkdir(parents=True, exist_ok=True)

    patients_bytes = patient_json.read_bytes()
    patients = json.loads(patients_bytes)["patients"]
    precision = sorted({p["geocoded"]["precision"] for p in patients})
    if len(precision) != 1:
        raise RuntimeError(f"mixed geocoding precision in cohort: {precision}")

    chel_url = raw_url(CHEL_REPO, CHEL_COMMIT, CHEL_FILE)
    cw_url = raw_url(WORKSHOP_REPO, WORKSHOP_COMMIT, WORKSHOP_CROSSWALK)
    print(f"chel/run.py: {'OFFLINE (cache)' if offline else 'ONLINE'} — {len(patients)} persons")

    with httpx.Client(headers={"User-Agent": "envar-heat-example/0.1"}) as client:
        chel_bytes = fetch_cached(client, chel_url, cache_dir / f"chel_{CHEL_COMMIT[:7]}_hex3_2024.csv", offline)
        cw_bytes = fetch_cached(client, cw_url, cache_dir / f"workshop_{WORKSHOP_COMMIT[:7]}_h3res3_countyfips_cw.csv", offline)
        counties = {
            str(p["person_id"]): county_fips(
                client, str(p["person_id"]), p["geocoded"]["lat"], p["geocoded"]["lon"], cache_dir, offline
            )
            for p in patients
        }

    chel = load_chel(chel_bytes)
    crosswalk = load_crosswalk(cw_bytes)
    print(f"  CHEL {CHEL_RELEASE}: {len(chel)} hexagons; crosswalk: {len(crosswalk)} counties")

    rows: list[dict] = []
    for p in patients:
        pid = str(p["person_id"])
        lat, lon = p["geocoded"]["lat"], p["geocoded"]["lon"]
        fips, county_name = counties[pid]
        hexes = {
            "point": h3.latlng_to_cell(lat, lon, H3_RESOLUTION),
            "county": crosswalk.get(fips),
        }
        for route in ROUTES:
            h3_id = hexes[route]
            row = chel.get(h3_id) if h3_id else None
            rows.append({
                "person_id": pid,
                "route": route,
                "county_fips": fips,
                "county_name": county_name,
                "h3_id": h3_id or "",
                "chel_hex_id": row["hex_id"] if row else "",
                "value": chel_value(row, VARIABLE),
                "percentile": chel_value(row, PERCENTILE_VARIABLE),
                "same_hexagon_both_routes": hexes["point"] == hexes["county"],
                "observation_start": p["observation_period"]["start"],
                "observation_end": p["observation_period"]["end"],
                "chel_readme_release": chel_readme_release(p["observation_period"]["start"]) or "",
            })

    # ---- data outputs, one file per route so each sidecar describes one file
    fields = ["person_id", "route", "county_fips", "county_name", "h3_id", "chel_hex_id",
              "value", "percentile", "same_hexagon_both_routes",
              "observation_start", "observation_end", "chel_readme_release"]
    data_csvs: dict[str, Path] = {}
    for route in ROUTES:
        data_csv = out_dir / f"chel_nehd_{route}.csv"
        route_rows = [r for r in rows if r["route"] == route]
        with data_csv.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            for r in route_rows:
                w.writerow({k: ("" if r[k] is None else r[k]) for k in fields})
        data_csvs[route] = data_csv
        print(f"wrote {data_csv.relative_to(here)} ({len(route_rows)} rows)")

    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    inputs = {
        "chel": {"url": chel_url, "commit": CHEL_COMMIT, "sha256": sha256_bytes(chel_bytes),
                 "hexagons": len(chel)},
        "workshop_crosswalk": {"url": cw_url, "commit": WORKSHOP_COMMIT,
                               "sha256": sha256_bytes(cw_bytes), "counties": len(crosswalk)},
        "county_lookup": {"service": FCC_AREA_API, "census_year": FCC_CENSUS_YEAR},
    }
    patients_rel = str(patient_json.relative_to(here.parent))
    patients_sha = sha256_bytes(patients_bytes)

    provenance_ids: dict[str, str] = {}
    sidecar_paths: dict[str, str] = {}
    for route in ROUTES:
        seed = f"{TOOL_NAME}|{TOOL_VERSION}|chel|{VARIABLE}|{route}|{patients_sha}|{run_ts}".encode()
        provenance_ids[route] = f"{ulid_like(seed)}-chel-{route}"
        route_rows = [r for r in rows if r["route"] == route]
        sidecar = build_sidecar(
            route=route, provenance_id=provenance_ids[route], run_ts=run_ts, rows=route_rows,
            inputs=inputs, precision=precision[0],
            min_score=min(p["geocoded"]["score"] for p in patients),
            out_rel=str(data_csvs[route].relative_to(here)),
            out_sha=sha256_bytes(data_csvs[route].read_bytes()),
            patients_rel=patients_rel, patients_sha=patients_sha, n_patients=len(patients),
        )
        path = envar_dir / f"chel_nehd_{route}.provenance.yaml"
        with path.open("w") as fh:
            yaml.safe_dump(sidecar, fh, sort_keys=False, default_flow_style=False, allow_unicode=True)
        sidecar_paths[route] = str(path.relative_to(here))
        print(f"wrote {path.relative_to(here)}")

    # ---- OMOP external_exposure shape (CONTRACT.md); value NULL rows are kept out
    ee_csv = out_dir / "external_exposure.csv"
    ee_fields = ["person_id", "location_id", "exposure_concept_id", "exposure_start_date",
                 "exposure_end_date", "value_as_number", "unit_concept_id",
                 "exposure_type_concept_id", "exposure_source_value", "exposure_source_concept_id"]
    ee_rows = [{
        "person_id": r["person_id"],
        "location_id": r["person_id"],
        "exposure_concept_id": EXPOSURE_CONCEPT_VALUE,
        "exposure_start_date": NEHD_COVERAGE_START,
        "exposure_end_date": NEHD_COVERAGE_END,
        "value_as_number": f"{r['value']:.4f}",
        "unit_concept_id": UNIT_CONCEPT_ID_DAY,
        "exposure_type_concept_id": EXPOSURE_TYPE_CONCEPT_ID,
        "exposure_source_value": provenance_ids[r["route"]],
        "exposure_source_concept_id": 0,
    } for r in rows if r["value"] is not None]
    with ee_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=ee_fields)
        w.writeheader()
        w.writerows(ee_rows)
    print(f"wrote {ee_csv.relative_to(here)} ({len(ee_rows)} rows)")

    # ---- run manifest (the workshop's _augment_manifest pattern)
    manifest = {
        "built_at": run_ts,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "parameters": {"variable": VARIABLE, "h3_resolution": H3_RESOLUTION,
                       "chel_release": CHEL_RELEASE, "routes": list(ROUTES)},
        "inputs": inputs | {"patients": {"path": patients_rel, "sha256": patients_sha}},
        "counts": {
            route: {
                "persons": len(patients),
                "persons_with_hexagon": sum(1 for r in rows if r["route"] == route and r["h3_id"]),
                "persons_with_value": sum(1 for r in rows if r["route"] == route and r["value"] is not None),
            } for route in ROUTES
        },
        "persons_in_a_different_hexagon_by_route": sorted(
            {r["person_id"] for r in rows if not r["same_hexagon_both_routes"]}
        ),
        "outputs": {"data": {k: str(v.relative_to(here)) for k, v in data_csvs.items()},
                    "external_exposure": str(ee_csv.relative_to(here)),
                    "sidecars": {provenance_ids[k]: v for k, v in sidecar_paths.items()}},
    }
    (out_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("wrote outputs/run_manifest.json")

    for r in rows:
        print(f"  {r['person_id']} {r['route']:<6} county={r['county_fips']} h3={r['h3_id']} "
              f"{VARIABLE}={r['value']} {PERCENTILE_VARIABLE}={r['percentile']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
