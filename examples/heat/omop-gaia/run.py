#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "pyyaml>=6.0"]
# ///
"""
run.py — self-contained OMOP / OHDSI-GIS pipeline driven by the **real**
OHDSI gaia-db container.

This implementation is deliberately isolated from the sibling
``degauss/`` and ``amadeus/`` pipelines: it reads only the canonical
patient cohort (``data/patients_example1.json``) and is responsible
for every step needed to land OMOP CDM v5.4 ``person``,
``location`` and OHDSI GIS WG ``external_exposure`` rows on disk,
together with an EnVar provenance sidecar.

Stages, in order:

1. **Geocode** the cohort by running the official DeGAUSS geocoder
   container (``ghcr.io/degauss-org/geocoder:3.3.0``). We run the
   container here because gaiaDocker's ``gaia-degauss`` profile uses
   the same image — so this is the geocoder GAIA itself integrates.
   We do *not* read the sibling DeGAUSS pipeline's outputs.

2. **Extract daily Daymet tmax** at each patient's freshly-geocoded
   coordinate by calling the public ORNL Daymet single-pixel API
   directly from this script. Same Daymet V4 R1 data the sibling
   pipeline can reach when its credential path fails — but the HTTP
   call, the parsing, and the resulting provenance ID are owned by
   omop-gaia.

3. **Boot** the real ``gaia-db`` (OHDSI/gaiaDB) container with the
   gaiaCore SQL functions installed, **apply two EnVar SQL patches**
   to it (one fixes a real upstream bug in ``working.spatial_join_exposure``,
   one adds a per-day-date variant), **load** ``working.location`` and
   ``working.location_history`` from the geocoded cohort, **register**
   the Daymet dataset via ``backbone.load_jsonld_file`` (the same path
   used by gaiaCatalog), **insert** the per-(person × day) tmax values
   into ``public.daymet_tmax`` as point geometries, and **call** the
   real ``working.spatial_join_exposure`` and
   ``working.envar_spatial_join_perday`` SQL functions to produce
   ``working.external_exposure``.

4. **Export** the resulting OMOP CSVs together with EnVar's provenance
   sidecar layer and the gaiaCatalog metadata layer.

The resulting outputs live alongside, and are directly comparable
with, what the sibling ``degauss/`` and ``amadeus/`` pipelines produce
from the same canonical input, but no row, byte or provenance ID is
shared with them.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import yaml

# -----------------------------------------------------------------------------
# constants
# -----------------------------------------------------------------------------

# DeGAUSS geocoder — gaiaDocker integrates this as the `gaia-degauss` profile;
# we invoke the same image here.
GEOCODER_IMAGE = "ghcr.io/degauss-org/geocoder:3.3.0"
GEOCODER_TOOL_NAME = "geocoder"
GEOCODER_TOOL_VERSION = "3.3.0"

# Daymet single-pixel API — public, no auth, ASCII CSV per-pixel response.
DAYMET_SINGLEPIXEL_URL = (
    "https://daymet.ornl.gov/single-pixel/api/data"
    "?lat={lat}&lon={lon}&vars=tmax&start={start}&end={end}"
)
DAYMET_TOOL_NAME = "daymet-singlepixel"
DAYMET_TOOL_VERSION = "v4-r1"
DAYMET_REQUEST_DELAY_S = 1.5

# gaia-db (OHDSI/gaiaDB) — built from a local clone if not already present.
GAIA_DB_IMAGE = "gaia-db"
GAIA_DB_IMAGE_TAG = "envar-heat"
GAIA_DB_IMAGE_FULL = f"{GAIA_DB_IMAGE}:{GAIA_DB_IMAGE_TAG}"
GAIA_DB_CONTAINER = "gaia-db-envar-heat"
GAIA_DB_USER = "postgres"
GAIA_DB_NAME = "gaiacore"
DEFAULT_HOST_PORT = int(os.environ.get("ENVAR_GAIA_PORT", "55433"))

# Standards / fixed concept IDs (no live vocabulary lookup needed).
OMOP_CDM_VERSION = "5.4"
EXTERNAL_EXPOSURE_SCHEMA_VERSION = "draft"
UNIT_CONCEPT_ID_CELSIUS = 8653          # UCUM "Cel"
EXPOSURE_TYPE_CONCEPT_ID = 32885         # "derived environmental estimate"
EXPOSURE_CONCEPT_VALUE = "proposed:daily-max-air-temperature"

# Spatial join buffer: both sides of the join are the patient's geocoded
# point; any positive buffer turns the degenerate point-in-point predicate
# into a true ST_within. 100 m sits comfortably inside Daymet's 1 km cell.
GAIA_JOIN_BUFFER_M = 100

HTTP_TIMEOUT_S = 60.0

# Crockford base-32 alphabet for ULID-shaped provenance IDs.
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# -----------------------------------------------------------------------------
# paths
# -----------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
GAIA_DIR = HERE / "gaia"
GAIA_JSONLD_DIR = GAIA_DIR / "jsonld"
GAIA_SQL_DIR = GAIA_DIR / "sql"
GAIA_DB_PATCH_SQL = GAIA_SQL_DIR / "00_envar_patch_spatial_join.sql"
GAIA_DB_PERDAY_SQL = GAIA_SQL_DIR / "10_envar_per_day_spatial_join.sql"

FIXTURES_DIR = HERE / "fixtures"
FIXTURE_GEOCODER_DIR = FIXTURES_DIR / "geocoder"
FIXTURE_DAYMET_DIR = FIXTURES_DIR / "daymet"

DOCKER_WORK = HERE / "_docker_workdir"


# -----------------------------------------------------------------------------
# utilities
# -----------------------------------------------------------------------------


def die(msg: str, code: int = 2) -> None:
    print(f"omop-gaia/run.py: {msg}", file=sys.stderr)
    sys.exit(code)


def require_file(p: Path, who: str) -> None:
    if not p.exists():
        die(f"{who} not found at {p}")


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_of_text(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def ulid_like(seed: bytes) -> str:
    digest = hashlib.sha256(seed).digest()
    n = int.from_bytes(digest[:17], "big")
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[n & 0x1F])
        n >>= 5
    return "".join(reversed(chars))


def parse_iso_date(s: str) -> date:
    return date.fromisoformat(s)


def write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=False)
        fh.write("\n")


def yday_to_date(year: int, yday: int) -> date:
    return date(year, 1, 1) + timedelta(days=yday - 1)


# -----------------------------------------------------------------------------
# docker helpers (used both for the geocoder container and for gaia-db)
# -----------------------------------------------------------------------------


def _docker_available() -> bool:
    return shutil.which("docker") is not None


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
            die(f"docker pull {image} succeeded but inspect returned no digest")
    return digest


# -----------------------------------------------------------------------------
# stage 1 — geocoding via the official DeGAUSS geocoder container
# -----------------------------------------------------------------------------


def _build_geocoder_input(patients_doc: dict) -> list[dict]:
    """Build the DeGAUSS-format cohort row list from the canonical patient JSON.

    DeGAUSS's container expects an ``address`` column and only knows about
    ``id``, ``address``, ``start_date``, ``end_date``. We pass the
    canonical ``person_id`` straight through as DeGAUSS's ``id`` so the
    downstream join is unambiguous.
    """
    window = patients_doc["study_window"]
    start, end = window["start"], window["end"]
    rows: list[dict] = []
    for pat in patients_doc["patients"]:
        addr = pat["address"]
        gi = addr.get("geocoder_input") or f"{addr['street']} {addr['zip']}"
        rows.append(
            {
                "id": pat["person_id"],
                "address": gi,
                "start_date": start,
                "end_date": end,
            }
        )
    return rows


def run_geocoder(
    rows: list[dict], *, offline: bool
) -> tuple[list[dict], str, str, dict]:
    """Run the DeGAUSS geocoder container on ``rows``.

    Returns (geocoded_rows, image_digest, execution_mode, run_meta) where
    ``execution_mode`` is one of ``"real_container"`` or ``"offline_fixture"``.
    ``geocoded_rows`` carry the columns DeGAUSS emits, renamed
    ``id -> person_id`` for our convenience.
    """
    fixture_csv = FIXTURE_GEOCODER_DIR / "cohort_addresses_geocoded.csv"

    if offline:
        if not fixture_csv.exists():
            die(
                f"ENVAR_OFFLINE=1 but no geocoder fixture at {fixture_csv}. "
                "Run the script online once to populate fixtures/geocoder/."
            )
        with fixture_csv.open() as fh:
            geocoded = list(csv.DictReader(fh))
        for r in geocoded:
            if "id" in r and "person_id" not in r:
                r["person_id"] = r.pop("id")
        return (
            geocoded,
            "",
            "offline_fixture",
            {
                "fixture_path": str(fixture_csv.relative_to(HERE)),
                "fixture_sha256": sha256_of(fixture_csv),
            },
        )

    if not _docker_available():
        die(
            "docker not found in PATH. Install Docker Desktop or Colima, "
            "or set ENVAR_OFFLINE=1 to use the bundled fixtures."
        )
    digest = _ensure_image_pulled(GEOCODER_IMAGE)

    DOCKER_WORK.mkdir(parents=True, exist_ok=True)
    work = DOCKER_WORK / "geocoder"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    container_input = work / "cohort_addresses.csv"
    fields = ["id", "address", "start_date", "end_date"]
    with container_input.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"  running {GEOCODER_IMAGE} ...")
    cmd = [
        "docker", "run", "--rm", "--platform", "linux/amd64",
        "-v", f"{work}:/tmp", GEOCODER_IMAGE, "cohort_addresses.csv",
    ]
    subprocess.check_call(cmd)

    matches = sorted(work.glob("cohort_addresses_geocoder_*_score_threshold_*.csv"))
    if not matches:
        die(
            f"geocoder container produced no output CSV in {work}; "
            f"got: {sorted(work.iterdir())}"
        )
    container_csv = matches[-1]

    with container_csv.open() as fh:
        geocoded = list(csv.DictReader(fh))
    for r in geocoded:
        r["person_id"] = r.pop("id")
    geocoded.sort(key=lambda r: int(r["person_id"]))

    # Cache for offline runs.
    FIXTURE_GEOCODER_DIR.mkdir(parents=True, exist_ok=True)
    fixture_target = FIXTURE_GEOCODER_DIR / "cohort_addresses_geocoded.csv"
    shutil.copyfile(container_csv, fixture_target)

    return (
        geocoded,
        digest,
        "real_container",
        {
            "container_image_repository": "ghcr.io/degauss-org/geocoder",
            "container_image_tag": GEOCODER_TOOL_VERSION,
            "container_image_digest": digest,
            "container_native_csv": container_csv.name,
        },
    )


# -----------------------------------------------------------------------------
# stage 2 — Daymet single-pixel API extraction (per patient)
# -----------------------------------------------------------------------------


def _daymet_fixture_path(person_id: str, start: str, end: str) -> Path:
    return FIXTURE_DAYMET_DIR / f"daymet_singlepixel_{person_id}_{start}_{end}.txt"


def fetch_daymet(
    *,
    person_id: str,
    lat: float,
    lon: float,
    start: str,
    end: str,
    client: httpx.Client,
    offline: bool,
) -> tuple[str, str]:
    """Return (body, source_label) where source_label is ``"network"`` or
    ``"fixture"``."""
    fixture = _daymet_fixture_path(person_id, start, end)
    if offline:
        if not fixture.exists():
            die(
                f"ENVAR_OFFLINE=1 but no Daymet fixture at {fixture}. "
                "Run the script online once to populate fixtures/daymet/."
            )
        return fixture.read_text(), "fixture"

    url = DAYMET_SINGLEPIXEL_URL.format(lat=lat, lon=lon, start=start, end=end)
    last_err: Exception | None = None
    for attempt in (1, 2, 3):
        try:
            r = client.get(url, timeout=HTTP_TIMEOUT_S)
            if r.status_code != 200:
                raise RuntimeError(
                    f"Daymet returned HTTP {r.status_code} for ({lat},{lon}): "
                    f"{r.text[:200]}"
                )
            body = r.text
            break
        except (httpx.HTTPError, RuntimeError) as e:
            last_err = e
            if attempt == 3:
                die(
                    f"Daymet single-pixel API failed after 3 attempts "
                    f"for ({lat},{lon}): {e}"
                )
            time.sleep(2 * attempt)
    else:
        die(f"unreachable: {last_err}")

    FIXTURE_DAYMET_DIR.mkdir(parents=True, exist_ok=True)
    fixture.write_text(body)
    return body, "network"


def parse_daymet_singlepixel_body(
    body: str, *, person_id: str, lat: float, lon: float
) -> list[dict]:
    """Parse a Daymet single-pixel API response.

    The response is an ASCII text body with a small free-form header
    followed by ``year,yday,tmax (deg c)``. We locate the header row by
    name and treat everything after it as CSV.
    """
    lines = body.splitlines()
    hdr_idx = next(
        (i for i, ln in enumerate(lines) if ln.strip().startswith("year,")),
        None,
    )
    if hdr_idx is None:
        die(f"Daymet response missing 'year,...' header for person {person_id}")
    out: list[dict] = []
    reader = csv.reader(lines[hdr_idx + 1:])
    for rec in reader:
        if not rec or not rec[0].strip():
            continue
        year = int(rec[0])
        yday = int(rec[1])
        tmax = float(rec[2])
        out.append(
            {
                "person_id": person_id,
                "date": yday_to_date(year, yday).isoformat(),
                "lat": lat,
                "lon": lon,
                "tmax": tmax,
            }
        )
    return out


def run_daymet_extraction(
    geocoded: list[dict],
    *,
    start: str,
    end: str,
    obs_periods: dict[int, tuple[date | None, date | None]],
    offline: bool,
) -> tuple[list[dict], list[tuple[str, list[str]]], str, dict]:
    """Pull Daymet single-pixel responses for each patient.

    Returns (per_day_rows, per_patient_headers, execution_mode, run_meta).
    """
    rows_out: list[dict] = []
    headers_captured: list[tuple[str, list[str]]] = []
    mode = "offline_fixture" if offline else "real_singlepixel_api"
    requests_made = 0
    fixture_hits = 0

    with httpx.Client(
        headers={"User-Agent": "envar-omop-gaia/0.1"},
        follow_redirects=True,
    ) as client:
        for i, g in enumerate(geocoded):
            pid_str = str(g["person_id"])
            lat = float(g["lat"])
            lon = float(g["lon"])
            if not offline and i > 0:
                time.sleep(DAYMET_REQUEST_DELAY_S)
            body, source = fetch_daymet(
                person_id=pid_str,
                lat=lat, lon=lon,
                start=start, end=end,
                client=client, offline=offline,
            )
            if source == "fixture":
                fixture_hits += 1
            else:
                requests_made += 1
            # Capture the free-form header for reporting.
            hdr_lines: list[str] = []
            for ln in body.splitlines():
                if ln.strip().startswith("year,"):
                    break
                hdr_lines.append(ln)
            headers_captured.append((pid_str, hdr_lines))

            per_day = parse_daymet_singlepixel_body(
                body, person_id=pid_str, lat=lat, lon=lon,
            )
            # Clip to the requested window (Daymet returns full-year for tmax
            # in some cases; we narrow to the study window only).
            win_start = parse_iso_date(start)
            win_end = parse_iso_date(end)
            for r in per_day:
                d = parse_iso_date(r["date"])
                if d < win_start or d > win_end:
                    continue
                # Also respect per-patient observation period if defined.
                obs_start, obs_end = obs_periods.get(int(pid_str), (None, None))
                if obs_start and d < obs_start:
                    continue
                if obs_end and d > obs_end:
                    continue
                rows_out.append(r)

    run_meta = {
        "endpoint": DAYMET_SINGLEPIXEL_URL.split("?", 1)[0],
        "requests_made": requests_made,
        "fixture_hits": fixture_hits,
        "request_delay_s": DAYMET_REQUEST_DELAY_S if not offline else 0,
    }
    return rows_out, headers_captured, mode, run_meta


# -----------------------------------------------------------------------------
# stage 3 — gaia-db: build/find, boot, exec
# -----------------------------------------------------------------------------


def find_gaia_db_repo(arg_path: Path | None) -> Path | None:
    candidates: list[Path] = []
    if arg_path is not None:
        candidates.append(arg_path)
    env = os.environ.get("ENVAR_GAIA_DB_REPO")
    if env:
        candidates.append(Path(env))
    candidates.extend(
        [
            Path.home() / "ws" / "notes" / "niehs_standards" / "tmp" / "git" / "gaiaDB",
            Path.home() / "ws" / "git" / "OHDSI" / "gaiaDB",
            Path.home() / "ws" / "git" / "gaiaDB",
            Path.home() / "code" / "gaiaDB",
            Path.cwd() / "gaiaDB",
        ]
    )
    for c in candidates:
        if c.is_dir() and (c / "Dockerfile").exists() and (c / "sql").is_dir():
            return c
    return None


def build_gaia_db_image(repo: Path) -> str:
    print(f"  building {GAIA_DB_IMAGE_FULL} from {repo} ...")
    subprocess.check_call([
        "docker", "build",
        "--platform", "linux/amd64",
        "-t", GAIA_DB_IMAGE_FULL,
        "-t", GAIA_DB_IMAGE,
        str(repo),
    ])
    digest = _docker_image_digest(GAIA_DB_IMAGE_FULL)
    if not digest:
        die(f"docker build of {GAIA_DB_IMAGE_FULL} returned no digest")
    return digest


def ensure_gaia_db_image(
    repo_path: Path | None,
) -> tuple[str, str, Path | None]:
    if not _docker_available():
        die(
            "docker not found in PATH. This script runs the real OHDSI "
            "gaia-db container — there is no no-docker fallback."
        )
    digest = _docker_image_digest(GAIA_DB_IMAGE_FULL)
    if digest:
        print(f"  using existing {GAIA_DB_IMAGE_FULL} ({digest[:19]}...)")
        return GAIA_DB_IMAGE_FULL, digest, None
    digest = _docker_image_digest(GAIA_DB_IMAGE)
    if digest:
        print(f"  using existing {GAIA_DB_IMAGE} ({digest[:19]}...)")
        return GAIA_DB_IMAGE, digest, None
    repo = find_gaia_db_repo(repo_path)
    if repo is None:
        die(
            "No `gaia-db` image found and no local clone of OHDSI/gaiaDB to "
            "build from. Run `docker build -t gaia-db https://github.com/"
            "OHDSI/gaiaDB.git` first, or pass --gaia-db-repo /path/to/gaiaDB."
        )
    return GAIA_DB_IMAGE_FULL, build_gaia_db_image(repo), repo


def _stop_gaia_container() -> None:
    subprocess.run(
        ["docker", "rm", "-f", GAIA_DB_CONTAINER],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _write_secret_files(dir_: Path) -> tuple[Path, Path]:
    dir_.mkdir(parents=True, exist_ok=True)
    pg = dir_ / "pg_password"
    auth = dir_ / "auth_password"
    pg.write_text(secrets.token_urlsafe(24))
    auth.write_text(secrets.token_urlsafe(24))
    pg.chmod(0o600)
    auth.chmod(0o600)
    return pg, auth


def start_gaia_db(image_ref: str, host_port: int, secrets_dir: Path) -> str:
    _stop_gaia_container()
    pg_pw_file, auth_pw_file = _write_secret_files(secrets_dir)
    cid = subprocess.check_output(
        [
            "docker", "run", "-d", "--rm",
            "--name", GAIA_DB_CONTAINER,
            "--platform", "linux/amd64",
            "-p", f"{host_port}:5432",
            "-v", f"{pg_pw_file}:/run/secrets/pg_pw:ro",
            "-v", f"{auth_pw_file}:/run/secrets/auth_pw:ro",
            "-e", f"POSTGRES_USER={GAIA_DB_USER}",
            "-e", f"POSTGRES_DB={GAIA_DB_NAME}",
            "-e", "POSTGRES_PASSWORD_FILE=/run/secrets/pg_pw",
            "-e", "PG_PASSWORD_FILE=/run/secrets/pg_pw",
            "-e", "AUTHENTICATOR_PASSWORD_FILE=/run/secrets/auth_pw",
            "-e", "INIT_WITH_DATASOURCE_MOUNT=FALSE",
            "-e", "POSTGRES_PORT=5432",
            "--user", "postgres:postgres",
            image_ref,
        ],
        text=True,
    ).strip()
    return cid


def wait_for_gaia_db(timeout_s: float = 120.0) -> None:
    deadline = time.time() + timeout_s
    last_err = ""
    while time.time() < deadline:
        r = subprocess.run(
            ["docker", "exec", GAIA_DB_CONTAINER, "pg_isready",
             "-U", GAIA_DB_USER, "-d", GAIA_DB_NAME],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        if r.returncode == 0 and "accepting connections" in r.stdout:
            check = subprocess.run(
                ["docker", "exec", GAIA_DB_CONTAINER, "psql",
                 "-U", GAIA_DB_USER, "-d", GAIA_DB_NAME, "-tAc",
                 "SELECT count(*) FROM pg_proc p "
                 "JOIN pg_namespace n ON n.oid = p.pronamespace "
                 "WHERE n.nspname='working' AND p.proname='spatial_join_exposure'"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            if (check.returncode == 0 and check.stdout.strip().isdigit()
                    and int(check.stdout.strip()) >= 1):
                return
            last_err = check.stderr.strip() or check.stdout.strip()
        else:
            last_err = (r.stderr or r.stdout).strip()
        time.sleep(2)
    die(f"gaia-db did not become ready within {timeout_s:.0f}s; last: {last_err}")


def psql_exec(sql: str) -> str:
    r = subprocess.run(
        ["docker", "exec", "-i", GAIA_DB_CONTAINER, "psql",
         "-U", GAIA_DB_USER, "-d", GAIA_DB_NAME, "-v", "ON_ERROR_STOP=1"],
        input=sql, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if r.returncode != 0:
        die(
            f"psql failed (rc={r.returncode}):\n"
            f"  STDOUT: {r.stdout}\n  STDERR: {r.stderr}"
        )
    return r.stdout


def psql_query_tab(sql: str) -> list[list[str]]:
    r = subprocess.run(
        ["docker", "exec", "-i", GAIA_DB_CONTAINER, "psql",
         "-U", GAIA_DB_USER, "-d", GAIA_DB_NAME,
         "-tAc", sql, "-F", "\t"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if r.returncode != 0:
        die(f"psql query failed: {r.stderr.strip()}")
    rows: list[list[str]] = []
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        rows.append(line.split("\t"))
    return rows


def docker_cp_into(src: Path, dst: str) -> None:
    subprocess.check_call(
        ["docker", "cp", str(src), f"{GAIA_DB_CONTAINER}:{dst}"]
    )


def docker_cp_from(src: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        ["docker", "cp", f"{GAIA_DB_CONTAINER}:{src}", str(dst)]
    )


# -----------------------------------------------------------------------------
# gaia-db schema operations
# -----------------------------------------------------------------------------


def apply_envar_patches() -> None:
    print("  applying EnVar SQL patches inside gaia-db ...")
    for p in (GAIA_DB_PATCH_SQL, GAIA_DB_PERDAY_SQL):
        require_file(p, str(p.relative_to(HERE)))
        docker_cp_into(p, f"/tmp/{p.name}")
        psql_exec(f"\\i /tmp/{p.name}")


def load_locations(
    persons: dict[int, dict],
    locations: dict[int, dict],
    obs_periods: dict[int, tuple[date | None, date | None]],
) -> None:
    print(
        f"  loading {len(locations)} working.location + "
        f"{len(persons)} working.location_history rows ..."
    )
    rows_loc = []
    for pid, loc in locations.items():
        addr1 = (loc.get("address_1") or "").replace("'", "''")
        city = (loc.get("city") or "").replace("'", "''")
        state = (loc.get("state") or "").replace("'", "''")
        zip_ = (loc.get("zip") or "").replace("'", "''")
        country = (loc.get("country_source_value") or "").replace("'", "''")
        lat = loc["latitude"]
        lon = loc["longitude"]
        rows_loc.append(
            f"({pid}, '{addr1}', '{city}', '{state}', '{zip_}', '{country}', "
            f"{lat}, {lon}, ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326))"
        )
    psql_exec(
        "INSERT INTO working.location "
        "(location_id, address_1, city, state, zip, country_source_value, "
        " latitude, longitude, geom) VALUES\n  "
        + ",\n  ".join(rows_loc) + ";\n"
        "SELECT setval(pg_get_serial_sequence('working.location','location_id'), "
        "(SELECT GREATEST(MAX(location_id), 1) FROM working.location));"
    )

    rows_hist = []
    for pid, pat in persons.items():
        loc_id = int(pat["location_id"])
        start, end = obs_periods.get(pid, (date(1970, 1, 1), date(2099, 12, 31)))
        if start is None:
            start = date(1970, 1, 1)
        if end is None:
            end = date(2099, 12, 31)
        rows_hist.append(
            f"({loc_id}, 32848, 1147314, {pid}, "
            f"'{start.isoformat()}', '{end.isoformat()}')"
        )
    psql_exec(
        "INSERT INTO working.location_history "
        "(location_id, relationship_type_concept_id, domain_id, entity_id, "
        " start_date, end_date) VALUES\n  "
        + ",\n  ".join(rows_hist) + ";"
    )


def register_dataset(jsonld_path: Path) -> str:
    print(f"  registering Daymet dataset from {jsonld_path.name} ...")
    docker_cp_into(jsonld_path, f"/tmp/{jsonld_path.name}")
    rows = psql_query_tab(
        "SELECT data_source_uuid FROM backbone.load_jsonld_file("
        f"pg_read_file('/tmp/{jsonld_path.name}'));"
    )
    if not rows:
        die(f"backbone.load_jsonld_file({jsonld_path.name}) returned no row")
    return rows[0][0]


def load_data_table_daymet(rows: list[dict]) -> None:
    print(f"  loading {len(rows)} rows into public.daymet_tmax ...")
    psql_exec(
        "DROP TABLE IF EXISTS public.daymet_tmax CASCADE;\n"
        "CREATE TABLE public.daymet_tmax (\n"
        "    gid SERIAL PRIMARY KEY,\n"
        "    person_id INTEGER NOT NULL,\n"
        "    source_date DATE NOT NULL,\n"
        "    tmax NUMERIC NOT NULL,\n"
        "    wgs_geom GEOMETRY(POINT, 4326) NOT NULL\n"
        ");\n"
        "CREATE INDEX idx_daymet_tmax_geom "
        "ON public.daymet_tmax USING GIST(wgs_geom);"
    )
    insert_rows = []
    for r in rows:
        insert_rows.append(
            f"({int(r['person_id'])}, '{r['date']}', {float(r['tmax'])}, "
            f"ST_SetSRID(ST_MakePoint({float(r['lon'])}, {float(r['lat'])}), 4326))"
        )
    psql_exec(
        "INSERT INTO public.daymet_tmax "
        "(person_id, source_date, tmax, wgs_geom) VALUES\n  "
        + ",\n  ".join(insert_rows) + ";"
    )


def export_table_to_csv(
    table_fqn: str, host_dst: Path,
) -> int:
    container_path = f"/tmp/{host_dst.name}"
    psql_exec(
        f"COPY (SELECT * FROM {table_fqn}) TO '{container_path}' "
        f"WITH (FORMAT csv, HEADER true);"
    )
    docker_cp_from(container_path, host_dst)
    with host_dst.open() as fh:
        return max(0, sum(1 for _ in fh) - 1)


# -----------------------------------------------------------------------------
# OMOP CDM v5.4 person / location materialisation (replaces translate.py)
# -----------------------------------------------------------------------------


PERSON_COLUMNS = [
    "person_id", "gender_concept_id", "year_of_birth", "month_of_birth",
    "day_of_birth", "birth_datetime", "race_concept_id", "ethnicity_concept_id",
    "location_id", "provider_id", "care_site_id", "person_source_value",
    "gender_source_value", "gender_source_concept_id", "race_source_value",
    "race_source_concept_id", "ethnicity_source_value",
    "ethnicity_source_concept_id",
]

LOCATION_COLUMNS = [
    "location_id", "address_1", "address_2", "city", "state", "zip", "county",
    "location_source_value", "country_concept_id", "country_source_value",
    "latitude", "longitude",
]

GENDER_CONCEPT = {"F": 8532, "M": 8507}


def build_person_rows(patients_doc: dict) -> list[dict]:
    out = []
    for pat in patients_doc["patients"]:
        sex = pat["sex"]
        out.append(
            {
                "person_id": pat["person_id"],
                "gender_concept_id": GENDER_CONCEPT.get(sex, 0),
                "year_of_birth": pat["year_of_birth"],
                "month_of_birth": "",
                "day_of_birth": "",
                "birth_datetime": "",
                "race_concept_id": 0,
                "ethnicity_concept_id": 0,
                "location_id": pat["person_id"],
                "provider_id": "",
                "care_site_id": "",
                "person_source_value": "",
                "gender_source_value": sex,
                "gender_source_concept_id": 0,
                "race_source_value": "",
                "race_source_concept_id": 0,
                "ethnicity_source_value": "",
                "ethnicity_source_concept_id": 0,
            }
        )
    return out


def build_location_rows(
    patients_doc: dict, geocoded: list[dict],
) -> list[dict]:
    """Build OMOP location rows using the *freshly geocoded* lat/lon from
    DeGAUSS, not the pre-resolved coordinates baked into the canonical JSON.

    This is what makes omop-gaia self-contained: its `location` table
    reflects this pipeline's own geocoder run.
    """
    by_pid: dict[int, dict] = {int(r["person_id"]): r for r in geocoded}
    out = []
    for pat in patients_doc["patients"]:
        pid = int(pat["person_id"])
        addr = pat["address"]
        g = by_pid.get(pid)
        if g is None:
            die(f"no geocoder result for person_id={pid}")
        lat = float(g.get("lat") or 0)
        lon = float(g.get("lon") or 0)
        out.append(
            {
                "location_id": pid,
                "address_1": addr["street"],
                "address_2": "",
                "city": addr["city"],
                "state": addr["state"],
                "zip": addr["zip"],
                "county": "",
                "location_source_value": addr.get("geocoder_input", ""),
                "country_concept_id": 0,
                "country_source_value": "US",
                "latitude": lat,
                "longitude": lon,
            }
        )
    return out


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns)
        w.writeheader()
        for r in rows:
            w.writerow(r)


# -----------------------------------------------------------------------------
# external_exposure post-processing (contract column order, provenance id)
# -----------------------------------------------------------------------------


EXTERNAL_EXPOSURE_CONTRACT_COLUMNS = [
    "person_id", "location_id", "exposure_concept_id",
    "exposure_start_date", "exposure_end_date",
    "value_as_number", "unit_concept_id", "exposure_type_concept_id",
    "exposure_source_value", "exposure_source_concept_id",
]


def project_exposure_rows(
    raw_csv: Path,
    *,
    daymet_provenance_id: str,
    persons: dict[int, dict],
    obs_periods: dict[int, tuple[date | None, date | None]],
) -> list[dict]:
    rows_out: list[dict] = []
    with raw_csv.open() as fh:
        for r in csv.DictReader(fh):
            pid = int(r["person_id"])
            if pid not in persons:
                continue
            d = parse_iso_date(r["exposure_start_date"])
            obs_start, obs_end = obs_periods.get(pid, (None, None))
            if obs_start and d < obs_start:
                continue
            if obs_end and d > obs_end:
                continue
            rows_out.append(
                {
                    "person_id": pid,
                    "location_id": int(r["location_id"]),
                    "exposure_concept_id": EXPOSURE_CONCEPT_VALUE,
                    "exposure_start_date": r["exposure_start_date"],
                    "exposure_end_date": r["exposure_end_date"],
                    "value_as_number": f"{float(r['value_as_number']):.4f}",
                    "unit_concept_id": UNIT_CONCEPT_ID_CELSIUS,
                    "exposure_type_concept_id": EXPOSURE_TYPE_CONCEPT_ID,
                    "exposure_source_value": daymet_provenance_id,
                    "exposure_source_concept_id": 0,
                }
            )
    rows_out.sort(
        key=lambda r: (r["person_id"], r["exposure_start_date"])
    )
    return rows_out


def write_contract_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=EXTERNAL_EXPOSURE_CONTRACT_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(r)


# -----------------------------------------------------------------------------
# gaiaCatalog metadata layer (Daymet only)
# -----------------------------------------------------------------------------


def _attr_line(
    name: str, description: str, source_field: str, datatype: str,
    units: str, nodata: str, vmin: str, vmax: str,
    start_date: str, end_date: str,
    concept_id_1: str = "0", concept_id_2: str = "0",
) -> str:
    return ";".join(
        [name, description, source_field, datatype, units, nodata, vmin, vmax,
         start_date, end_date, concept_id_1, concept_id_2]
    )


def build_meta_etl_daymet() -> dict:
    return {
        "rights": "Public Domain (U.S. Government Work)",
        "structure": "raster",
        "geometry": "raster",
        "epsg": "EPSG:4326",
        "local_epsg": "EPSG:5070",
        "source": "https://daymet.ornl.gov/single-pixel/",
        "file": ["daymet_v4_daily_tmax", "daymet_v4_daily_na_tmax_*.nc"],
        "extension": "nc",
        "download": "wget",
        "format": "netcdf",
        "table": "daymet_v4_daily_tmax_north_america",
        "derive": [],
        "up": "false",
        "podID": "gaia-db",
        "nodata": ["float4", "-9999"],
        "attributes": [
            _attr_line(
                name="tmax",
                description="Daily maximum 2m air temperature",
                source_field="tmax",
                datatype="float4",
                units="deg C",
                nodata="-9999",
                vmin="-50", vmax="60",
                start_date="2018-01-01", end_date="2022-12-31",
            ),
        ],
        "extent": "POLYGON((-178 14, -52 14, -52 83, -178 83, -178 14))",
        "update_frequency": "Annual",
        "_gap_note": (
            "gaiaCatalog's etl() generator targets ogr2ogr for vector inputs; "
            "no raster ingest pipeline exists today. omop-gaia therefore "
            "extracts Daymet values at point geometries via the public "
            "single-pixel API before handing rows to gaia-db's spatial join."
        ),
    }


def _spdx_to_url(spdx: str) -> str:
    return {
        "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
        "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
        "public-domain-us-gov": "https://www.usa.gov/government-works",
    }.get(spdx, f"https://spdx.org/licenses/{spdx}.html")


def build_meta_dcat_daymet() -> dict:
    return {
        "@context": {
            "dcat": "http://www.w3.org/ns/dcat#",
            "dct": "http://purl.org/dc/terms/",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
        },
        "@type": "dcat:Dataset",
        "dct:title":
            "Daymet V4 R1: Daily Surface Weather Data on a 1-km Grid "
            "for North America",
        "dct:description": (
            "Daymet provides long-term, continuous, gridded estimates of "
            "daily weather variables by interpolating GHCN-Daily station "
            "observations through statistical modeling techniques."
        ),
        "dct:publisher": {
            "@type": "dct:Agent",
            "foaf:name": "NASA ORNL DAAC",
            "@id": "https://daac.ornl.gov/",
        },
        "dct:issued": "2022-09-15",
        "dct:license": _spdx_to_url("public-domain-us-gov"),
        "dct:identifier": "https://doi.org/10.3334/ORNLDAAC/2129",
        "dct:temporal": {
            "@type": "dct:PeriodOfTime",
            "dcat:startDate": "1980-01-01",
            "dcat:endDate": "2023-12-31",
        },
        "dcat:keyword": [
            "temperature", "daily maximum", "1km grid", "north america",
            "extreme heat", "daymet", "GHCN-Daily",
        ],
    }


# -----------------------------------------------------------------------------
# Static docs
# -----------------------------------------------------------------------------


NATIVE_METADATA_MD = """\
# omop-gaia outputs — what's native vs what EnVar adds

This directory holds what the OHDSI GIS Working Group's gaiaDB +
gaiaCatalog stack produces when you run a real spatial-join exposure
pipeline against the patient cohort in `data/patients_example1.json`.

> Everything in `outputs/` was produced by this folder's `run.py`
> on its own — no row, byte or provenance ID was read from the
> sibling `degauss/` or `amadeus/` pipelines. The geocoding was
> done by the official DeGAUSS geocoder container, Daymet tmax was
> pulled from the public ORNL single-pixel API, and the spatial
> join was the real `working.spatial_join_exposure()` SQL function
> inside the running gaia-db container.

## What's here

| Path | What it is |
|---|---|
| `person.csv`        | OMOP CDM v5.4 person — produced by this run |
| `location.csv`      | OMOP CDM v5.4 location — coordinates from the DeGAUSS geocoder run we did, not from the canonical JSON's pre-resolved geocode |
| `daymet_tmax.csv`   | Per-(person × day) Daymet tmax values fetched by this run from the ORNL single-pixel API |
| `external_exposure.csv` | OHDSI GIS WG external_exposure (per-day dates) emitted by `working.envar_spatial_join_perday` inside gaia-db |
| `external_exposure_gaia_native.csv` | What gaia-db's own `spatial_join_exposure()` produced (window-wide dates — a real-GAIA limitation kept for comparison) |
| `gaia_catalog/`     | The native OHDSI GIS WG metadata catalog files for the Daymet dataset (meta_etl, meta_dcat, meta_json-ld) |
| `gaia_db/`          | Live snapshots dumped out of the running gaia-db schemas: backbone.data_source, backbone.variable_source, working.location, working.location_history, and the spatial-join log |
| `envar/`            | EnVar add-on: sidecar carrying full provenance for this run, README, MANIFEST |

## Limitations of the real GAIA pipeline this run hits

1. **`working.spatial_join_exposure` column-ambiguity bug.** Upstream
   builds the inner `att` subquery as `SELECT *, '...'::date AS
   attr_start_date, ... FROM backbone.variable_source`. Once
   `variable_source.attr_start_date` is populated (any JSON-LD-registered
   variable), the subquery has two columns named `attr_start_date` and
   PostgreSQL aborts the join. Patched in `gaia/sql/00_envar_patch_spatial_join.sql`.

2. **Per-day exposure date collapsed to the variable's window.** Gaia
   uses the variable_source row's `attr_start_date / attr_end_date` for
   *every* exposure row regardless of the per-row data date.
   `external_exposure_gaia_native.csv` shows the consequence. The
   per-day variant we add (`gaia/sql/10_envar_per_day_spatial_join.sql`)
   reads the date from the data row's `source_date` column.

3. **Raster ingest gap.** gaiaCatalog's ETL generator targets ogr2ogr
   for vector inputs; there is no raster ingest pipeline today. omop-gaia
   side-steps that by extracting Daymet values per-point via the
   single-pixel API *before* handing them to gaia-db.
"""

ENVAR_README_MD = """\
# EnVar add-on to the omop-gaia export

This directory holds the EnVar additions on top of what the real
gaia-db pipeline produced.

## Files

| Path | What it is |
|---|---|
| `MANIFEST.json` | Export index: file list, row counts per OMOP table, the per-run provenance map and a `gaia_pipeline` block recording the container image, SQL functions invoked, and SQL patches applied. |
| `daymet.provenance.json` | Provenance sidecar for this run's Daymet single-pixel extraction (variable, spatial, temporal, source_dataset, exposure_model, linkage, tool_run blocks). |
| `geocoder.provenance.json` | Provenance sidecar for this run's DeGAUSS geocoder invocation. |

## Resolving an OMOP row to its sidecar

Every row in `outputs/external_exposure.csv` carries an
`exposure_source_value` column. That column holds this run's Daymet
`provenance_id`. To inspect the provenance: look the ID up under
`provenance_index` in `MANIFEST.json` — the value is the path to the
corresponding sidecar in this directory.
"""


# -----------------------------------------------------------------------------
# main
# -----------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "patients_json",
        type=Path,
        nargs="?",
        default=Path("../data/patients_example1.json"),
        help="Path to canonical patients JSON (default: ../data/patients_example1.json)",
    )
    p.add_argument("--out-dir", type=Path, default=Path("outputs"))
    p.add_argument(
        "--gaia-db-repo", type=Path, default=None,
        help="Path to a local clone of OHDSI/gaiaDB to build from if the "
        "gaia-db image isn't already on the local Docker daemon.",
    )
    p.add_argument(
        "--host-port", type=int, default=DEFAULT_HOST_PORT,
        help=f"Host port to bind gaia-db's PostgreSQL on (default {DEFAULT_HOST_PORT}).",
    )
    args = p.parse_args()

    require_file(args.patients_json, "patients_example1.json")
    require_file(GAIA_DB_PATCH_SQL, "gaia/sql/00_envar_patch_spatial_join.sql")
    require_file(GAIA_DB_PERDAY_SQL, "gaia/sql/10_envar_per_day_spatial_join.sql")
    daymet_jsonld_src = GAIA_JSONLD_DIR / "daymet_v4_r1.jsonld.json"
    require_file(daymet_jsonld_src, "gaia/jsonld/daymet_v4_r1.jsonld.json")

    offline = os.environ.get("ENVAR_OFFLINE", "") == "1"

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    gaia_catalog_dir = out_dir / "gaia_catalog"
    gaia_db_dir = out_dir / "gaia_db"
    envar_dir = out_dir / "envar"

    with args.patients_json.open() as fh:
        patients_doc = json.load(fh)
    window = patients_doc["study_window"]
    win_start, win_end = window["start"], window["end"]
    obs_periods: dict[int, tuple[date | None, date | None]] = {}
    for pat in patients_doc["patients"]:
        op = pat.get("observation_period") or {}
        s = parse_iso_date(op["start"]) if op.get("start") else None
        e = parse_iso_date(op["end"]) if op.get("end") else None
        obs_periods[int(pat["person_id"])] = (s, e)

    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ------------ stage 1: geocode via DeGAUSS container ------------------

    print(
        f"omop-gaia/run.py: stage 1 — geocoding "
        f"({'OFFLINE (fixture)' if offline else 'ONLINE (DeGAUSS container)'}) ..."
    )
    geocoder_input_rows = _build_geocoder_input(patients_doc)
    geocoded, geocoder_digest, geocoder_mode, geocoder_run_meta = run_geocoder(
        geocoder_input_rows, offline=offline,
    )
    print(f"  geocoded {len(geocoded)} rows (mode={geocoder_mode})")

    # ------------ stage 2: Daymet single-pixel extraction -----------------

    print(
        f"omop-gaia/run.py: stage 2 — Daymet single-pixel extraction "
        f"({'OFFLINE (fixtures)' if offline else 'ONLINE (ORNL API)'}) ..."
    )
    daymet_rows, daymet_headers, daymet_mode, daymet_run_meta = run_daymet_extraction(
        geocoded,
        start=win_start, end=win_end,
        obs_periods=obs_periods, offline=offline,
    )
    print(f"  Daymet returned {len(daymet_rows)} per-(person × day) rows")

    # ------------ stage 3: OMOP person + location materialisation ---------

    print("omop-gaia/run.py: stage 3 — OMOP person + location ...")
    person_rows = build_person_rows(patients_doc)
    location_rows = build_location_rows(patients_doc, geocoded)
    person_csv = out_dir / "person.csv"
    location_csv = out_dir / "location.csv"
    write_csv(person_csv, PERSON_COLUMNS, person_rows)
    write_csv(location_csv, LOCATION_COLUMNS, location_rows)

    daymet_csv = out_dir / "daymet_tmax.csv"
    write_csv(
        daymet_csv,
        ["person_id", "date", "lat", "lon", "tmax"],
        daymet_rows,
    )
    print(f"  wrote {person_csv} ({len(person_rows)} rows)")
    print(f"  wrote {location_csv} ({len(location_rows)} rows)")
    print(f"  wrote {daymet_csv} ({len(daymet_rows)} rows)")

    # ------------ stage 4: real gaia-db pipeline --------------------------

    print("omop-gaia/run.py: stage 4 — real OHDSI gaia-db pipeline ...")
    image_ref, image_digest, image_repo = ensure_gaia_db_image(args.gaia_db_repo)
    secrets_dir = HERE / "_gaia_secrets"
    start_gaia_db(image_ref, args.host_port, secrets_dir)
    print(f"  started {GAIA_DB_CONTAINER} (port {args.host_port})")

    keep = os.environ.get("ENVAR_GAIA_KEEP", "") == "1"
    persons_map: dict[int, dict] = {int(r["person_id"]): r for r in person_rows}
    locations_map: dict[int, dict] = {int(r["location_id"]): r for r in location_rows}

    try:
        wait_for_gaia_db()
        print("  gaia-db is ready, applying EnVar SQL patches ...")
        apply_envar_patches()

        load_locations(persons_map, locations_map, obs_periods)
        daymet_uuid = register_dataset(daymet_jsonld_src)
        print(f"  registered Daymet: data_source_uuid = {daymet_uuid}")
        load_data_table_daymet(daymet_rows)

        spatial_join_log: list[str] = []

        def _run(label: str, sql: str) -> None:
            print(f"  {label} ...")
            spatial_join_log.append(f"--- {label} ---\n{psql_exec(sql)}")

        _run(
            "gaia-native spatial_join_exposure('tmax', 'public.daymet_tmax')",
            "SELECT working.spatial_join_exposure("
            "'tmax', 'public.daymet_tmax', NULL, NULL, NULL, "
            f"'st_within', {GAIA_JOIN_BUFFER_M});",
        )
        _run(
            "EnVar per-day envar_spatial_join_perday('tmax', 'public.daymet_tmax')",
            "SELECT working.envar_spatial_join_perday("
            f"'tmax', 'public.daymet_tmax', 'st_within', {GAIA_JOIN_BUFFER_M});",
        )

        gaia_native_raw = out_dir / "_gaia_native_raw.csv"
        gaia_perday_raw = out_dir / "_gaia_perday_raw.csv"
        gaia_native_rowcount = export_table_to_csv(
            "working.external_exposure", gaia_native_raw,
        )
        gaia_perday_rowcount = export_table_to_csv(
            "working.external_exposure_perday", gaia_perday_raw,
        )

        gaia_db_dir.mkdir(parents=True, exist_ok=True)
        for table, fname in [
            ("backbone.data_source", "data_source.csv"),
            ("backbone.variable_source", "variable_source.csv"),
            ("working.location", "location.csv"),
            ("working.location_history", "location_history.csv"),
        ]:
            export_table_to_csv(table, gaia_db_dir / fname)
        (gaia_db_dir / "spatial_join_log.txt").write_text(
            "\n\n".join(spatial_join_log)
        )

    finally:
        if keep:
            print(
                f"  ENVAR_GAIA_KEEP=1 — leaving {GAIA_DB_CONTAINER} running on "
                f"localhost:{args.host_port}"
            )
        else:
            print(f"  stopping {GAIA_DB_CONTAINER} ...")
            _stop_gaia_container()
            shutil.rmtree(secrets_dir, ignore_errors=True)
            shutil.rmtree(DOCKER_WORK, ignore_errors=True)

    # ------------ stage 5: build provenance IDs ---------------------------

    daymet_input_sha = sha256_of(daymet_csv)
    daymet_pid_seed = (
        f"{DAYMET_TOOL_NAME}|{DAYMET_TOOL_VERSION}|"
        f"{daymet_input_sha}|{run_ts}"
    ).encode()
    daymet_pid = f"{ulid_like(daymet_pid_seed)}-omop-gaia-daymet"

    geocoder_input_sha = sha256_of_text(json.dumps(geocoder_input_rows, sort_keys=True))
    geocoder_pid_seed = (
        f"{GEOCODER_TOOL_NAME}|{GEOCODER_TOOL_VERSION}|"
        f"{geocoder_input_sha}|{run_ts}"
    ).encode()
    geocoder_pid = f"{ulid_like(geocoder_pid_seed)}-omop-gaia-geocoder"

    # ------------ stage 6: post-process exports into contract shape -------

    native_rows = project_exposure_rows(
        gaia_native_raw,
        daymet_provenance_id=daymet_pid,
        persons=persons_map, obs_periods=obs_periods,
    )
    perday_rows = project_exposure_rows(
        gaia_perday_raw,
        daymet_provenance_id=daymet_pid,
        persons=persons_map, obs_periods=obs_periods,
    )
    write_contract_csv(out_dir / "external_exposure.csv", perday_rows)
    write_contract_csv(
        out_dir / "external_exposure_gaia_native.csv", native_rows,
    )
    gaia_native_raw.unlink(missing_ok=True)
    gaia_perday_raw.unlink(missing_ok=True)

    # ------------ stage 7: gaiaCatalog metadata layer --------------------

    gaia_catalog_dir.mkdir(parents=True, exist_ok=True)
    write_json(gaia_catalog_dir / "meta_etl_daymet_tmax.json", build_meta_etl_daymet())
    write_json(gaia_catalog_dir / "meta_dcat_daymet_tmax.json", build_meta_dcat_daymet())
    shutil.copyfile(
        daymet_jsonld_src,
        gaia_catalog_dir / "meta_json-ld_daymet_tmax.json",
    )

    # ------------ stage 8: EnVar provenance sidecars + manifest ----------

    envar_dir.mkdir(parents=True, exist_ok=True)

    geocoder_sidecar = {
        "provenance_id": geocoder_pid,
        "tool_run": {
            "tool_name": GEOCODER_TOOL_NAME,
            "tool_version": GEOCODER_TOOL_VERSION,
            "execution_mode": geocoder_mode,
            "container_image_repository": "ghcr.io/degauss-org/geocoder",
            "container_image_tag": GEOCODER_TOOL_VERSION,
            "container_image_digest": geocoder_digest or None,
            "run_timestamp_utc": run_ts,
            "input_file_sha256": geocoder_input_sha,
            "input_row_count": len(geocoder_input_rows),
            "output_row_count": len(geocoded),
            "run_meta": geocoder_run_meta,
        },
        "source_dataset": {
            "name": "DeGAUSS geocoder reference data (US Census TIGER/Line + ZCTA)",
            "short_code": "degauss_geocoder",
            "version": GEOCODER_TOOL_VERSION,
            "producer_institution": (
                "Cincinnati Children's Hospital Medical Center (DeGAUSS); "
                "reference data: U.S. Census Bureau"
            ),
            "license_spdx": "public-domain-us-gov",
            "access_url": "https://degauss.org/geocoder/",
        },
        "linkage": {"strategy": "address_to_point_geocode"},
        "_note": (
            "Run by omop-gaia/run.py on its own — independent of the "
            "sibling degauss/ pipeline."
        ),
    }
    geocoder_sidecar_path = envar_dir / "geocoder.provenance.json"
    write_json(geocoder_sidecar_path, geocoder_sidecar)

    daymet_sidecar = {
        "provenance_id": daymet_pid,
        "variable": {
            "name": "tmax",
            "cf_standard_name": "air_temperature",
            "cf_cell_methods": "time: maximum",
            "units_ucum": "Cel",
        },
        "spatial": {
            "native_spatial_resolution_m": 1000,
            "crs": "EPSG:4326",
            "extraction_method": "single_pixel_api",
            "target_geography_type": "point_residence",
        },
        "temporal": {
            "temporal_resolution": "daily",
            "temporal_aggregation_method": "maximum",
            "day_boundary_convention": "local_midnight",
            "calendar": "gregorian",
            "extraction_window_start": win_start,
            "extraction_window_end": win_end,
        },
        "source_dataset": {
            "name": "Daymet V4 Daily Surface Weather Data",
            "short_code": "daymet_v4",
            "doi": "10.3334/ORNLDAAC/2129",
            "version": "V4 R1",
            "producer_institution": "NASA ORNL DAAC",
            "license_spdx": "public-domain-us-gov",
            "native_format": "NetCDF-4_CF",
            "access_url": "https://daymet.ornl.gov/single-pixel/",
        },
        "exposure_model": {
            "type": "spatial_interpolation",
            "inputs": ["GHCN-Daily station observations"],
        },
        "linkage": {
            "strategy": "point_extraction_at_residence",
            "geocoding_precision_propagated": "unknown",
            "address_period_alignment": "address_history_from_emr",
        },
        "tool_run": {
            "tool_name": DAYMET_TOOL_NAME,
            "tool_version": DAYMET_TOOL_VERSION,
            "execution_mode": daymet_mode,
            "run_timestamp_utc": run_ts,
            "input_file_sha256": daymet_input_sha,
            "input_row_count": len(geocoded),
            "output_row_count": len(daymet_rows),
            "run_meta": daymet_run_meta,
        },
        "provenance_chain": [
            {
                "provenance_id": geocoder_pid,
                "role": "geocoding",
                "sidecar_path": geocoder_sidecar_path.name,
            }
        ],
    }
    daymet_sidecar_path = envar_dir / "daymet.provenance.json"
    write_json(daymet_sidecar_path, daymet_sidecar)

    daymet_count = sum(1 for r in perday_rows if r["exposure_source_value"] == daymet_pid)
    manifest = {
        "export_format": "omop-cdm-csv",
        "omop_cdm_version": OMOP_CDM_VERSION,
        "external_exposure_schema_version": EXTERNAL_EXPOSURE_SCHEMA_VERSION,
        "omop_gaia_run_id": daymet_pid.replace("-omop-gaia-daymet", "-omop-gaia"),
        "run_timestamp_utc": run_ts,
        "input_patients_json": str(args.patients_json),
        "input_patients_json_sha256": sha256_of(args.patients_json),
        "study_window": {"start": win_start, "end": win_end},
        "isolation_note": (
            "This pipeline ran end-to-end from patients_example1.json alone. "
            "It did NOT read sibling outputs from degauss/ or amadeus/. "
            "Geocoding ran via the DeGAUSS geocoder container; Daymet tmax "
            "was pulled from the public ORNL single-pixel API; the spatial "
            "join was the real working.spatial_join_exposure inside gaia-db."
        ),
        "files": [
            {"path": "../person.csv", "table": "person", "rows": len(person_rows)},
            {"path": "../location.csv", "table": "location",
             "rows": len(location_rows)},
            {"path": "../daymet_tmax.csv", "table": None,
             "rows": len(daymet_rows),
             "note": "Pre-spatial-join per-(person × day) Daymet values."},
            {"path": "../external_exposure.csv",
             "table": "external_exposure",
             "rows": len(perday_rows),
             "rows_by_source": {daymet_pid: daymet_count},
             "produced_by_sql_function": "working.envar_spatial_join_perday"},
            {"path": "../external_exposure_gaia_native.csv",
             "table": "external_exposure",
             "rows": len(native_rows),
             "produced_by_sql_function": "working.spatial_join_exposure",
             "note": (
                 "Real-GAIA output kept for comparison; dates collapsed to "
                 "the variable's window (gaia limitation)."
             )},
        ],
        "native_metadata_layer": {
            "description": (
                "The three OHDSI GIS Working Group metadata files for the "
                "Daymet dataset. meta_json-ld is the exact file fed into "
                "the real backbone.load_jsonld_file() inside gaia-db."
            ),
            "files": [
                "../gaia_catalog/meta_etl_daymet_tmax.json",
                "../gaia_catalog/meta_dcat_daymet_tmax.json",
                "../gaia_catalog/meta_json-ld_daymet_tmax.json",
            ],
        },
        "gaia_pipeline": {
            "execution_mode": "real_gaiaDB_container",
            "container_image_repository": GAIA_DB_IMAGE,
            "container_image_tag": GAIA_DB_IMAGE_TAG,
            "container_image_ref": image_ref,
            "container_image_digest": image_digest,
            "container_image_source_repo": str(image_repo) if image_repo else None,
            "container_name_used": GAIA_DB_CONTAINER,
            "host_port_used": args.host_port,
            "sql_functions_invoked": [
                "backbone.load_jsonld_file",
                "working.spatial_join_exposure",
                "working.envar_spatial_join_perday",
            ],
            "spatial_join_buffer_meters": GAIA_JOIN_BUFFER_M,
            "spatial_operator": "st_within",
            "envar_sql_patches_applied": [
                {
                    "file": "gaia/sql/00_envar_patch_spatial_join.sql",
                    "fixes": (
                        "SELECT * + overlay column-ambiguity bug in "
                        "the upstream working.spatial_join_exposure"
                    ),
                },
                {
                    "file": "gaia/sql/10_envar_per_day_spatial_join.sql",
                    "fixes": (
                        "Adds working.envar_spatial_join_perday which "
                        "reads per-row exposure dates from the data row's "
                        "source_date column."
                    ),
                },
            ],
            "registered_datasets": [
                {
                    "data_source_uuid": daymet_uuid,
                    "variable_name": "tmax",
                    "data_table": "public.daymet_tmax",
                    "jsonld_file": "gaia/jsonld/daymet_v4_r1.jsonld.json",
                    "envar_provenance_id": daymet_pid,
                },
            ],
            "gaia_native_row_count": gaia_native_rowcount,
            "gaia_perday_row_count": gaia_perday_rowcount,
        },
        "provenance_index": {
            geocoder_pid: f"geocoder.provenance.json",
            daymet_pid: f"daymet.provenance.json",
        },
        "omop_assembly": {
            "value_as_number_unit_ucum": "Cel",
            "value_as_number_unit_concept_id": UNIT_CONCEPT_ID_CELSIUS,
            "exposure_concept_placeholder": EXPOSURE_CONCEPT_VALUE,
            "exposure_type_concept_id": EXPOSURE_TYPE_CONCEPT_ID,
            "observation_period_filter_applied": bool(obs_periods),
        },
    }
    manifest_path = envar_dir / "MANIFEST.json"
    write_json(manifest_path, manifest)

    (out_dir / "NATIVE_METADATA.md").write_text(NATIVE_METADATA_MD)
    (envar_dir / "README.md").write_text(ENVAR_README_MD)

    print()
    print("done. Wrote:")
    out_root = out_dir.resolve()
    for f in sorted(out_root.iterdir()):
        if f.is_dir():
            for g in sorted(f.rglob("*")):
                if g.is_file():
                    print(f"  {g.relative_to(HERE)}")
        else:
            print(f"  {f.relative_to(HERE)}")
    print()
    print(
        f"  external_exposure.csv: {len(perday_rows)} rows; "
        f"per-day dates from working.envar_spatial_join_perday."
    )
    print(
        f"  external_exposure_gaia_native.csv: {len(native_rows)} rows; "
        f"window-wide dates from working.spatial_join_exposure (kept for contrast)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
