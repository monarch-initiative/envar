# Empty until amadeus_extract.R actually runs

This folder holds real (non-synthetic) amadeus output once someone runs
`Rscript amadeus_extract.R` from this dataset's folder. It mirrors
`outputs/synthetic/`'s shape exactly (companion CSV, run_manifest.json,
envar/sidecar_*.yaml) so curation/validate.py work unchanged against
either tree -- see curator/generate_prism_variants.py's SOURCE_MODE
variable to point curation at this tree instead of synthetic/.

This file is a git placeholder (empty directories aren't tracked); delete
it once real content exists here.
