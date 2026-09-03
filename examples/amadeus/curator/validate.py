#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["linkml-runtime>=1.9.4", "pyyaml>=6.0"]
# ///
"""validate.py — score one or more EnVar sidecars with the REAL checker.

This does not reimplement any validation logic. It locates (and, if
missing, clones) the sibling `linkml-microschemas-envar` repo, installs it
if its `checker` module isn't already importable, and shells out to the
exact same `envar-check` tool that scores every example on the schema's
own docs site (see linkml-microschemas-envar/src/linkml_microschemas_envar
/checker.py). This is deliberate: the whole point of the agentic curation
approach is to never let this repo's tooling disagree with the schema's
own authoritative scorer.

Usage:
    python validate.py <sidecar.yaml> [<sidecar2.yaml> ...]
    python validate.py --schema-repo ../../linkml-microschemas-envar sidecar.yaml
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

SCHEMA_REPO_URL = "https://github.com/monarch-initiative/linkml-microschemas-envar.git"


def ensure_schema_repo(path: Path, *, offline: bool) -> Path:
    """Clone or refresh the sibling schema repo; install it if needed."""
    if not path.exists():
        if offline:
            raise FileNotFoundError(
                f"ENVAR_OFFLINE=1 and no schema repo checkout at {path}. "
                "Run once online, or point --schema-repo at an existing checkout."
            )
        print(f"cloning {SCHEMA_REPO_URL} -> {path}")
        subprocess.run(
            ["git", "clone", "--depth", "1", SCHEMA_REPO_URL, str(path)], check=True
        )
    elif not offline:
        subprocess.run(["git", "-C", str(path), "pull", "--ff-only"], check=False)

    try:
        import linkml_microschemas_envar.checker  # noqa: F401
    except ImportError:
        print(f"installing linkml_microschemas_envar from {path}")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--break-system-packages",
             "-e", str(path), "-q"],
            check=True,
        )
    return path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("sidecars", nargs="+", help="sidecar YAML file(s) to score")
    p.add_argument(
        "--schema-repo",
        type=Path,
        default=Path(__file__).resolve().parents[4] / "linkml-microschemas-envar",
        help="path to the sibling linkml-microschemas-envar checkout "
             "(default: a checkout named 'linkml-microschemas-envar' living "
             "next to the envar repo root, i.e. ../linkml-microschemas-envar "
             "relative to the envar repo, matching the SKILL.md instructions)",
    )
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    offline = shutil.os.environ.get("ENVAR_OFFLINE") == "1"
    ensure_schema_repo(args.schema_repo, offline=offline)

    from linkml_microschemas_envar.checker import main as checker_main

    checker_argv = list(args.sidecars)
    if args.json:
        checker_argv = ["--json"] + checker_argv
    return checker_main(checker_argv)


if __name__ == "__main__":
    sys.exit(main())
