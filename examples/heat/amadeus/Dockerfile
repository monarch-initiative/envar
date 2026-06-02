# Dockerfile — runs the REAL amadeus R package on top of rocker/geospatial.
#
# rocker/geospatial:4.4 already ships R 4.4 + sf + terra + GDAL/PROJ/GEOS.
# amadeus needs `archive` (libarchive system lib) to install on top.
#
# Build:
#   docker build --platform linux/amd64 -t envar-amadeus:4.4 .
#
# Use (from inside the amadeus/ folder):
#   docker run --rm --platform linux/amd64 -v "$PWD":/work -w /work \
#       envar-amadeus:4.4 Rscript amadeus_extract.R inputs/patient_locations.csv outputs/
FROM --platform=linux/amd64 rocker/geospatial:4.4

# libarchive needed by R's `archive` package (an amadeus dep).
RUN apt-get update -qq \
 && apt-get install -y -qq libarchive-dev \
 && rm -rf /var/lib/apt/lists/*

# Install amadeus + jsonlite (used by amadeus_extract.R).
RUN R --no-save -e 'install.packages(c("amadeus","jsonlite"), repos="https://cloud.r-project.org", Ncpus=4)' \
 && R --no-save -e 'library(amadeus); cat("amadeus version:", as.character(packageVersion("amadeus")), "\n")'

# Default working dir; user mounts the amadeus/ folder over this.
WORKDIR /work
