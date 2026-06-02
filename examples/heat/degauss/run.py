#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
run.py — DeGAUSS pipeline, running the **real** containers end-to-end.

Two stages, both required:

  step 1: geocoder    `ghcr.io/degauss-org/geocoder:3.3.0`
                      No credentials required. Writes the DeGAUSS-native
                      geocoded CSV.

  step 2: daymet      `ghcr.io/degauss-org/daymet:1.0.0`
                      Requires NASA EarthData credentials (free, sign up at
                      https://urs.earthdata.nasa.gov/users/new) AND
                      AppEEARS authorization on that account (the container
                      uses NASA's AppEEARS API to download Daymet NetCDF
                      tiles). Set env vars DAYMET_USERNAME and
                      DAYMET_PASSWORD before invoking.

There is no Python fallback. If credentials are missing or the container
fails, this script exits non-zero.

The daymet container's native output is cached at `_cache/daymet/<key>/`
keyed by (input CSV sha256, image tag, --vars). Subsequent runs with the
same input reuse the cached CSV and skip the AppEEARS round-trip. Set
env var ENVAR_NO_CACHE=1 to force a re-fetch.

Native artefacts are written verbatim to outputs/:

  outputs/cohort_addresses_geocoder_3.3.0_score_threshold_0.5.csv
      Byte-identical copy of the geocoder container's joined CSV.

  outputs/cohort_addresses_geocoded_daymet_1.0.0.csv
      Byte-identical copy of the daymet container's joined CSV.

EnVar-friendly aliases (column rename id -> person_id, stable sort) are
also written so the downstream omop-gaia step and scripts/verify.py keep
working without having to know the native column names:

  outputs/cohort_addresses_geocoded.csv
  outputs/cohort_addresses_geocoded_daymet.csv

The EnVar provenance sidecar lives under outputs/envar/. It records the
sha256 of BOTH the native and the EnVar-aliased CSV so the relationship is
verifiable.

Run from inside the degauss/ folder:

    DAYMET_USERNAME=... DAYMET_PASSWORD=... uv run --script run.py
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------- constants

HERE = Path(__file__).parent
INPUT_CSV = HERE / "inputs" / "cohort_addresses.csv"
OUT_DIR = HERE / "outputs"
OUT_GEO_NATIVE = OUT_DIR / "cohort_addresses_geocoder_3.3.0_score_threshold_0.5.csv"
OUT_GEO_ENVAR = OUT_DIR / "cohort_addresses_geocoded.csv"
OUT_DAYMET_NATIVE = OUT_DIR / "cohort_addresses_geocoded_daymet_1.0.0.csv"
OUT_DAYMET_ENVAR = OUT_DIR / "cohort_addresses_geocoded_daymet.csv"
OUT_CENSUS_JSON = OUT_DIR / "census_geocoder_responses.json"
OUT_ENVAR_DIR = OUT_DIR / "envar"
OUT_SIDECAR = OUT_ENVAR_DIR / "cohort_addresses_geocoded_daymet.provenance.json"
DOCKER_WORK = HERE / "_docker_workdir"
CACHE_DIR = HERE / "_cache" / "daymet"

GEOCODER_IMAGE = "ghcr.io/degauss-org/geocoder:3.3.0"
DAYMET_IMAGE = "ghcr.io/degauss-org/daymet:1.0.0"

TOOL_NAME = "daymet"
TOOL_VERSION = "1.0.0"
GEOCODER_TOOL_NAME = "geocoder"
GEOCODER_TOOL_VERSION = "3.3.0"


# ------------------------------------------------------------------- ULID

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_crockford(value: int, width: int) -> str:
    out = []
    for _ in range(width):
        out.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(out))


def make_ulid(seed: bytes, when: dt.datetime) -> str:
    ms = int(when.replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    ms &= (1 << 48) - 1
    time_part = _encode_crockford(ms, 10)
    digest = hashlib.sha256(seed).digest()
    rand_int = int.from_bytes(digest[:10], "big") & ((1 << 80) - 1)
    rand_part = _encode_crockford(rand_int, 16)
    return time_part + rand_part


# -------------------------------------------------------------- docker helpers


def _require_docker() -> None:
    if shutil.which("docker") is None:
        sys.exit(
            "docker not found in PATH. Install Docker Desktop, then re-run."
        )


def _docker_image_digest(image: str) -> str | None:
    try:
        out = subprocess.check_output(
            ["docker", "inspect", "--format", "{{.Id}}", image],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.strip() or None
    except subprocess.CalledProcessError:
        return None


def _ensure_image_pulled(image: str) -> str:
    digest = _docker_image_digest(image)
    if digest is None:
        print(f"  pulling {image} ...")
        subprocess.check_call(["docker", "pull", image])
        digest = _docker_image_digest(image)
        if digest is None:
            sys.exit(f"docker pull {image} succeeded but inspect returned no digest")
    return digest


def _require_daymet_credentials() -> tuple[str, str]:
    u = os.environ.get("DAYMET_USERNAME") or os.environ.get("daymet_username")
    p = os.environ.get("DAYMET_PASSWORD") or os.environ.get("daymet_password")
    if not u or not p:
        sys.exit(
            "Missing NASA EarthData credentials.\n"
            "  Set env vars DAYMET_USERNAME and DAYMET_PASSWORD before running.\n"
            "  Free signup: https://urs.earthdata.nasa.gov/users/new\n"
            "  The account must also be authorized for AppEEARS:\n"
            "      https://appeears.earthdatacloud.nasa.gov/  (sign in once to grant access)\n"
        )
    return u, p


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# -------------------------------------------------------------- daymet cache
#
# The AppEEARS round-trip is the dominant cost of running this pipeline
# (10-60 min). The DeGAUSS daymet container has no built-in cache, but
# its joined CSV output is deterministic given (input cohort CSV, container
# version, --vars). We therefore cache the native joined CSV under a
# content-addressed key. Set ENVAR_NO_CACHE=1 to force a re-fetch.


def _daymet_cache_key(geocoded_native_csv: Path, vars_arg: str) -> str:
    """Cache key = sha256(input CSV bytes | image tag | vars)."""
    h = hashlib.sha256()
    h.update(sha256_file(geocoded_native_csv).encode())
    h.update(b"|")
    h.update(DAYMET_IMAGE.encode())
    h.update(b"|")
    h.update(vars_arg.encode())
    return h.hexdigest()


def _cache_paths(key: str) -> tuple[Path, Path, Path]:
    cache_dir = CACHE_DIR / key
    return (
        cache_dir,
        cache_dir / "cohort_addresses_geocoded_daymet_1.0.0.csv",
        cache_dir / "_cache_meta.json",
    )


def lookup_daymet_cache(key: str) -> Path | None:
    """Return the cached native CSV path if a usable entry exists, else None."""
    if os.environ.get("ENVAR_NO_CACHE"):
        return None
    _, csv_path, meta_path = _cache_paths(key)
    if csv_path.exists() and meta_path.exists():
        return csv_path
    return None


def store_daymet_cache(
    key: str,
    input_csv: Path,
    native_csv: Path,
    image_digest: str,
    vars_arg: str,
) -> None:
    cache_dir, cached_csv, meta_path = _cache_paths(key)
    cache_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(native_csv, cached_csv)
    meta = {
        "cache_key": key,
        "image_tag": DAYMET_IMAGE,
        "image_digest": image_digest,
        "vars": vars_arg,
        "input_csv_sha256": sha256_file(input_csv),
        "native_csv_sha256": sha256_file(cached_csv),
        "stored_at_utc": dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        + "Z",
    }
    with meta_path.open("w") as fh:
        json.dump(meta, fh, indent=2)
        fh.write("\n")


# -------------------------------------------------------------- step 1: geocode


def run_real_geocoder(
    input_rows: list[dict],
) -> tuple[list[dict], str, Path]:
    """Run the real DeGAUSS geocoder container.

    Returns (rows_with_person_id, image_digest, native_csv_path).
    `native_csv_path` is the byte-identical container output (uses `id`).
    """
    _require_docker()
    digest = _ensure_image_pulled(GEOCODER_IMAGE)

    DOCKER_WORK.mkdir(parents=True, exist_ok=True)
    work = DOCKER_WORK / "geocoder"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    # DeGAUSS expects `id`, not `person_id`. Build the container input CSV.
    container_input = work / "cohort_addresses.csv"
    fields = ["id", "address", "start_date", "end_date"]
    with container_input.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in input_rows:
            w.writerow(
                {
                    "id": r["person_id"],
                    "address": r["address"],
                    "start_date": r["start_date"],
                    "end_date": r["end_date"],
                }
            )

    print(f"  running {GEOCODER_IMAGE} ...")
    cmd = [
        "docker",
        "run",
        "--rm",
        "--platform",
        "linux/amd64",
        "-v",
        f"{work}:/work",
        "-w",
        "/work",
        GEOCODER_IMAGE,
        "cohort_addresses.csv",
    ]
    subprocess.check_call(cmd)

    matches = sorted(work.glob("cohort_addresses_geocoder_*_score_threshold_*.csv"))
    if not matches:
        sys.exit(
            f"geocoder container produced no output CSV in {work}; "
            f"got: {sorted(work.iterdir())}"
        )
    container_csv = matches[-1]

    # Read native, build EnVar-friendly view (id -> person_id, stable sort).
    with container_csv.open() as fh:
        rows = list(csv.DictReader(fh))
    envar_rows = []
    for r in rows:
        nr = dict(r)
        nr["person_id"] = nr.pop("id")
        envar_rows.append(nr)
    envar_rows.sort(key=lambda r: int(r["person_id"]))
    return envar_rows, digest, container_csv


# -------------------------------------------------------------- step 2: daymet


def _parse_daymet_native_csv(container_csv: Path) -> list[dict]:
    with container_csv.open() as fh:
        rows = list(csv.DictReader(fh))
    envar_rows: list[dict] = []
    for r in rows:
        nr = dict(r)
        nr["person_id"] = nr.pop("id")
        if "tmax" in nr and nr["tmax"] not in (None, ""):
            nr["tmax"] = float(nr["tmax"])
        for k in ("lat", "lon"):
            if k in nr and nr[k] not in (None, ""):
                nr[k] = float(nr[k])
        envar_rows.append(nr)
    envar_rows.sort(key=lambda r: (int(r["person_id"]), r["date"]))
    return envar_rows


def run_real_daymet_container(
    geocoded_native_csv: Path,
    vars_arg: str = "tmax",
) -> tuple[list[dict], str, Path, str]:
    """Run `ghcr.io/degauss-org/daymet:1.0.0` (or serve from cache).

    Cache lookup is content-addressed by (input CSV sha256, image tag,
    vars). On a hit, the container is skipped and the cached native CSV
    is reused. Set env var ENVAR_NO_CACHE=1 to force a re-fetch.

    Returns (envar_rows, image_digest, native_csv_path, cache_status).
    `cache_status` is one of: "hit", "miss_stored", "miss_no_store",
    "disabled".
    """
    _require_docker()

    key = _daymet_cache_key(geocoded_native_csv, vars_arg)
    cached_csv = lookup_daymet_cache(key)
    if cached_csv is not None:
        print(f"  daymet cache HIT  key={key[:12]}...  ({cached_csv.parent.name})")
        envar_rows = _parse_daymet_native_csv(cached_csv)
        meta_path = cached_csv.parent / "_cache_meta.json"
        digest = ""
        if meta_path.exists():
            try:
                digest = json.loads(meta_path.read_text()).get("image_digest", "") or ""
            except json.JSONDecodeError:
                digest = ""
        return envar_rows, digest, cached_csv, "hit"

    cache_status = "disabled" if os.environ.get("ENVAR_NO_CACHE") else "miss"
    if cache_status == "miss":
        print(f"  daymet cache MISS key={key[:12]}...  (will populate after run)")
    else:
        print("  daymet cache disabled (ENVAR_NO_CACHE set)")

    user, password = _require_daymet_credentials()
    digest = _ensure_image_pulled(DAYMET_IMAGE)

    work = DOCKER_WORK / "daymet"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    # Don't bind-mount /work or /tmp into the daymet container. The R
    # `appeears` package downloads NetCDF tiles to R's session tempdir
    # via `curl`, then `file.rename`s them to its `path` argument. On
    # macOS Docker Desktop, those two paths land on different
    # filesystems (one in ephemeral overlay, the other on the host
    # bind mount). curl can fail to open files inside a mode-700 R
    # session dir on a bind mount; `file.rename` across filesystems
    # silently returns FALSE and the appeears "moved temporary files
    # to" message prints anyway. Either way, the downloaded files
    # never reach the host.
    #
    # The robust workaround is to keep everything on the container's
    # ephemeral filesystem during the run, then `docker cp /tmp/.` out
    # after it exits cleanly. Container WORKDIR is already /tmp, so
    # the entrypoint reads its input, writes `Daymet_Data/`, and writes
    # the joined CSV all in one place.
    print(f"  running {DAYMET_IMAGE} (NASA AppEEARS, may take 10-60 min) ...")
    cid = subprocess.check_output(
        [
            "docker",
            "create",
            "--platform",
            "linux/amd64",
            "-e",
            f"USER={user}",
            "-e",
            f"PASSWORD={password}",
            DAYMET_IMAGE,
            "cohort_addresses_geocoded.csv",
            f"--vars={vars_arg}",
        ],
        text=True,
    ).strip()
    try:
        subprocess.check_call(
            [
                "docker",
                "cp",
                str(geocoded_native_csv),
                f"{cid}:/tmp/cohort_addresses_geocoded.csv",
            ]
        )
        subprocess.run(["docker", "start", "-a", cid], check=False)
        exit_code = int(
            subprocess.check_output(["docker", "wait", cid], text=True).strip()
        )
        if exit_code != 0:
            sys.exit(f"daymet container exited {exit_code}")
        subprocess.check_call(
            ["docker", "cp", f"{cid}:/tmp/.", str(work)]
        )
    finally:
        subprocess.run(
            ["docker", "rm", "-f", cid],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    matches = sorted(work.glob("cohort_addresses_geocoded_daymet*.csv"))
    if not matches:
        sys.exit(
            f"daymet container produced no output CSV in {work}; "
            f"got: {sorted(work.iterdir())}"
        )
    container_csv = matches[-1]
    envar_rows = _parse_daymet_native_csv(container_csv)

    if cache_status == "miss":
        store_daymet_cache(key, geocoded_native_csv, container_csv, digest, vars_arg)
        print(f"  daymet cache stored at {(CACHE_DIR / key).relative_to(HERE)}/")
        cache_status = "miss_stored"
    else:
        cache_status = "miss_no_store"
    return envar_rows, digest, container_csv, cache_status


# -------------------------------------------------------------- CSV writers


def write_envar_geocoded_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["person_id"]
    seen = {"person_id"}
    for r in rows:
        for k in r.keys():
            if k not in seen:
                cols.append(k)
                seen.add(k)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_envar_daymet_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Slim downstream-friendly columns expected by scripts/verify.py and
    # omop-gaia/run.py. The full native columns are preserved verbatim in
    # OUT_DAYMET_NATIVE.
    fields = ["person_id", "date", "lat", "lon", "precision", "score", "tmax"]
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_census_responses(path: Path) -> None:
    """The real DeGAUSS geocoder embeds match data in the CSV; write a stub
    here documenting that (see outputs/NATIVE_METADATA.md)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    stub = {
        "_note": (
            "The real DeGAUSS geocoder container does not expose the underlying "
            "Census/TIGER match JSON. Its match data is embedded directly in "
            "cohort_addresses_geocoder_3.3.0_score_threshold_0.5.csv as "
            "matched_street, matched_zip, matched_city, matched_state, score, "
            "precision, geocode_result. See outputs/NATIVE_METADATA.md."
        )
    }
    with path.open("w") as fh:
        json.dump(stub, fh, indent=2)
        fh.write("\n")


# ------------------------------------------------------------- sidecar


_PRECISION_RANK = {
    "rooftop": 0,
    "range": 1,
    "street": 2,
    "zip": 3,
    "centroid": 4,
    "no_match": 9,
}


def worst_precision(rows: list[dict]) -> str:
    if not rows:
        return "no_match"
    return max(rows, key=lambda r: _PRECISION_RANK.get(r.get("precision", ""), 99))[
        "precision"
    ]


def build_sidecar(
    *,
    input_csv: Path,
    geocoded_native_csv: Path,
    geocoded_envar_csv: Path,
    daymet_native_csv: Path,
    daymet_envar_csv: Path,
    geocoded_rows: list[dict],
    daymet_rows: list[dict],
    window_start: str,
    window_end: str,
    now_utc: dt.datetime,
    geocoder_image_digest: str,
    daymet_image_digest: str,
    daymet_cache_status: str = "miss_stored",
) -> dict:
    input_sha = sha256_file(input_csv)
    geocoded_native_sha = sha256_file(geocoded_native_csv)
    geocoded_envar_sha = sha256_file(geocoded_envar_csv)
    daymet_native_sha = sha256_file(daymet_native_csv)
    daymet_envar_sha = sha256_file(daymet_envar_csv)

    seed = f"{TOOL_NAME}|{TOOL_VERSION}|{input_sha}".encode()
    ulid = make_ulid(seed, now_utc)
    provenance_id = f"{ulid}-daymet"

    geocoder_seed = (
        f"{GEOCODER_TOOL_NAME}|{GEOCODER_TOOL_VERSION}|{input_sha}".encode()
    )
    geocoder_ulid = make_ulid(geocoder_seed, now_utc)
    geocoder_provenance_id = f"{geocoder_ulid}-geocoder"

    return {
        "provenance_id": provenance_id,
        "variable": {
            "name": "tmax",
            "cf_standard_name": "air_temperature",
            "cf_cell_methods": "time: maximum",
            "units_ucum": "Cel",
        },
        "spatial": {
            "native_spatial_resolution_m": 1000,
            "crs": "EPSG:4326",
            "extraction_method": "inverse_distance_weighted_4_nearest_cells",
            "target_geography_type": "point_residence",
        },
        "temporal": {
            "temporal_resolution": "daily",
            "temporal_aggregation_method": "maximum",
            "day_boundary_convention": "local_midnight",
            "calendar": "gregorian",
            "extraction_window_start": window_start,
            "extraction_window_end": window_end,
        },
        "source_dataset": {
            "name": "Daymet V4 Daily Surface Weather Data",
            "short_code": "daymet_v4",
            "doi": "10.3334/ORNLDAAC/2129",
            "version": "V4 R1",
            "producer_institution": "NASA ORNL DAAC",
            "license_spdx": "public-domain-us-gov",
            "native_format": "NetCDF-4_CF",
            "access_url": "https://daymet.ornl.gov/",
        },
        "exposure_model": {
            "type": "spatial_interpolation",
            "inputs": ["GHCN-Daily station observations"],
        },
        "linkage": {
            "strategy": "point_extraction_at_residence",
            "geocoding_precision_propagated": worst_precision(geocoded_rows),
            "address_period_alignment": "address_history_from_emr",
        },
        "tool_run": {
            "tool_name": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "execution_mode": "real_container",
            "cache_status": daymet_cache_status,
            "container_image_repository": "ghcr.io/degauss-org/daymet",
            "container_image_tag": TOOL_VERSION,
            "container_image_digest": daymet_image_digest,
            "run_timestamp_utc": now_utc.replace(microsecond=0).isoformat() + "Z",
            "native_output_file": daymet_native_csv.name,
            "native_output_file_sha256": daymet_native_sha,
            "envar_aliased_output_file": daymet_envar_csv.name,
            "envar_aliased_output_file_sha256": daymet_envar_sha,
            "input_file_sha256": geocoded_native_sha,
            "input_row_count": len(geocoded_rows),
            "output_row_count": len(daymet_rows),
        },
        "provenance_chain": [
            {
                "provenance_id": geocoder_provenance_id,
                "tool_run": {
                    "tool_name": GEOCODER_TOOL_NAME,
                    "tool_version": GEOCODER_TOOL_VERSION,
                    "execution_mode": "real_container",
                    "container_image_repository": "ghcr.io/degauss-org/geocoder",
                    "container_image_tag": GEOCODER_TOOL_VERSION,
                    "container_image_digest": geocoder_image_digest,
                    "run_timestamp_utc": now_utc.replace(microsecond=0).isoformat()
                    + "Z",
                    "native_output_file": geocoded_native_csv.name,
                    "native_output_file_sha256": geocoded_native_sha,
                    "envar_aliased_output_file": geocoded_envar_csv.name,
                    "envar_aliased_output_file_sha256": geocoded_envar_sha,
                    "input_file_sha256": input_sha,
                    "input_row_count": len(geocoded_rows),
                    "output_row_count": len(geocoded_rows),
                },
                "source_dataset": {
                    "name": "DeGAUSS geocoder reference data (US Census TIGER/Line + ZCTA)",
                    "short_code": "degauss_geocoder",
                    "version": GEOCODER_TOOL_VERSION,
                    "producer_institution": (
                        "Cincinnati Children's Hospital Medical Center "
                        "(DeGAUSS); reference data: U.S. Census Bureau"
                    ),
                    "license_spdx": "public-domain-us-gov",
                    "access_url": "https://degauss.org/geocoder/",
                },
                "linkage": {
                    "strategy": "address_to_point_geocode",
                },
            }
        ],
    }


# ----------------------------------------------------------------- main


def read_input_csv(path: Path) -> list[dict]:
    with path.open() as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    if not INPUT_CSV.exists():
        print(f"missing {INPUT_CSV}; run translate.py first", file=sys.stderr)
        return 2

    rows = read_input_csv(INPUT_CSV)
    print(f"loaded {len(rows)} cohort rows from {INPUT_CSV}")
    _require_daymet_credentials()  # fail fast before the slow geocoder step

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("step 1: REAL DeGAUSS geocoder container ...")
    geocoded_envar, geocoder_digest, geocoder_native_csv = run_real_geocoder(rows)
    shutil.copyfile(geocoder_native_csv, OUT_GEO_NATIVE)
    print(f"  wrote {OUT_GEO_NATIVE.name} (native, verbatim)")
    write_envar_geocoded_csv(geocoded_envar, OUT_GEO_ENVAR)
    print(f"  wrote {OUT_GEO_ENVAR.name} (EnVar-aliased, id->person_id)")
    write_census_responses(OUT_CENSUS_JSON)

    print("step 2: REAL DeGAUSS daymet container ...")
    window_start = rows[0]["start_date"]
    window_end = rows[0]["end_date"]
    daymet_envar, daymet_digest, daymet_native_csv, daymet_cache_status = (
        run_real_daymet_container(OUT_GEO_NATIVE)
    )
    shutil.copyfile(daymet_native_csv, OUT_DAYMET_NATIVE)
    print(f"  wrote {OUT_DAYMET_NATIVE.name} (native, verbatim)")
    write_envar_daymet_csv(daymet_envar, OUT_DAYMET_ENVAR)
    print(f"  wrote {OUT_DAYMET_ENVAR.name} (EnVar-aliased)")

    print("step 3: EnVar provenance sidecar (outputs/envar/) ...")
    now_utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    sidecar = build_sidecar(
        input_csv=INPUT_CSV,
        geocoded_native_csv=OUT_GEO_NATIVE,
        geocoded_envar_csv=OUT_GEO_ENVAR,
        daymet_native_csv=OUT_DAYMET_NATIVE,
        daymet_envar_csv=OUT_DAYMET_ENVAR,
        geocoded_rows=geocoded_envar,
        daymet_rows=daymet_envar,
        window_start=window_start,
        window_end=window_end,
        now_utc=now_utc,
        geocoder_image_digest=geocoder_digest,
        daymet_image_digest=daymet_digest,
        daymet_cache_status=daymet_cache_status,
    )
    OUT_SIDECAR.parent.mkdir(parents=True, exist_ok=True)
    with OUT_SIDECAR.open("w") as fh:
        json.dump(sidecar, fh, indent=2)
        fh.write("\n")
    print(f"  wrote {OUT_SIDECAR.name}")
    print(f"  provenance_id = {sidecar['provenance_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
