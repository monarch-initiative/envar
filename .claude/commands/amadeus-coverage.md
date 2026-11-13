---
description: Amadeus × EnVar coverage report for one dataset or all (CSV, JSON, Markdown, Word)
argument-hint: <all | gridmet | narr | modis | ... >
---

Generate the Amadeus × EnVar coverage outputs for: **$ARGUMENTS** (use `all` if empty).

1. From `examples/amadeus-coverage/`, run:
   `uv run --no-project --with pyyaml --with python-docx --with matplotlib python scripts/run.py $ARGUMENTS`
   It clones NIEHS/amadeus and monarch-initiative/linkml-microschemas-envar into `.cache/` if needed.
   It needs `Rscript` with `jsonlite`; if missing, tell me how to install it for my OS and stop.
2. If `compare.py` raises `KeyError` (amadeus or the schema added a new argument, dataset or slot),
   show me what is unmapped and propose where it belongs in `compare.py`; don't guess silently.
3. Reply with the output folder, the totals from `results.json` (EnVar slots shared / EnVar-only;
   Amadeus elements mapped / no EnVar home) and the High items in both directions. Keep it short.

Valid datasets: terraclimate, gridmet, koppen_geiger, nlcd, cropscape, modis, merra2, population,
groads, huc, geos, edgar, hms, goes, narr, prism, drought, aqs, improve, ecoregion, nei, tri, gmted.
