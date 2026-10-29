# EnVar project commands

# Serve the mkdocs site locally
serve:
    uv run mkdocs serve

# --- R / amadeus setup (NOT managed by uv/pyproject.toml -- R is a
# separate runtime, not a Python package. Install R itself first:
# macOS: brew install r | Linux: see cran.r-project.org | verify: R --version ---

# Install the R packages examples/amadeus's amadeus_extract.R scripts need
install-r-deps:
    Rscript -e 'install.packages(c("amadeus", "jsonlite", "digest", "sf"))'

# Run real amadeus extraction for one dataset: just extract-r prism_tmax
extract-r dataset:
    cd examples/amadeus/datasets/{{dataset}} && Rscript amadeus_extract.R
