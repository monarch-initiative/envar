"""envar_model.py — locate the pinned EnVar micro-schema.

The model is a project dependency (`linkml-microschemas-envar`), tracked at
`main` in pyproject.toml and pinned to an exact commit by uv.lock. Scripts get
the schema from here rather than from a caller-supplied path, so every run
measures against the same model.

`schema_path()` fails fast if the package is not installed, or if the installed
commit is not the one uv.lock pins — a stale environment would otherwise
produce numbers for a model nobody can identify.

Run directly to print the schema path, e.g. for `linkml-validate -s`.
"""
from __future__ import annotations

import json
import sys
import tomllib
from importlib import metadata, resources
from pathlib import Path

DIST = "linkml-microschemas-envar"
LOCKFILE = Path(__file__).resolve().parents[3] / "uv.lock"


def locked_commit() -> str:
    lock = tomllib.loads(LOCKFILE.read_text())
    for pkg in lock["package"]:
        if pkg["name"] == DIST:
            return pkg["source"]["git"].rsplit("#", 1)[1]
    raise SystemExit(f"{DIST} not found in {LOCKFILE}")


def installed_commit() -> str:
    direct_url = metadata.distribution(DIST).read_text("direct_url.json")
    return json.loads(direct_url or "{}").get("vcs_info", {}).get("commit_id", "")


def schema_path() -> Path:
    try:
        import linkml_microschemas_envar
    except ImportError:
        raise SystemExit(f"{DIST} is not installed; run `uv sync` from the repo root")

    installed, locked = installed_commit(), locked_commit()
    if installed != locked:
        raise SystemExit(
            f"{DIST} is at {installed[:7] or 'an unknown commit'}, uv.lock pins {locked[:7]}; "
            "run `uv sync`"
        )
    return Path(str(resources.files(linkml_microschemas_envar) / "schema" / "envar_record.yaml"))


if __name__ == "__main__":
    print(schema_path())
    sys.exit(0)
