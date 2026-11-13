# Amadeus × EnVar coverage

Compares the 23 [amadeus](https://niehs.github.io/amadeus/) datasets (their `?download_*`, `?process_*`,
`?calculate_*` help pages) with the [EnVar micro-schema](https://monarch-initiative.github.io/linkml-microschemas-envar/overview/).

## Run

In Claude Code: `/amadeus-coverage gridmet` or `/amadeus-coverage all`

Or directly:

```
cd examples/amadeus-coverage
uv run --no-project --with pyyaml --with python-docx --with matplotlib python scripts/run.py all
```

Needs `uv` and R (base R only, no R packages). Source repos are cloned into `.cache/`.

## Outputs: `outputs/<all|dataset>/`

| File | Contents |
|---|---|
| `coverage_report_<name>.docx` | The report |
| `dataset_x_envar_slot.csv` | Each EnVar slot: full / partial / empty / n/a |
| `dataset_x_amadeus_element.csv` | Each Amadeus argument or fact: EnVar slot it maps to, or gap |
| `shared_mapping.csv`, `.md` | EnVar slot ← Amadeus source |
| `results.json` | All counts and ranked gaps |
| `amadeus_help_compendium.md` | Full help text |
