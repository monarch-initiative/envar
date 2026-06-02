#!/usr/bin/env Rscript
# amadeus_extract.R — REAL amadeus + terra pipeline.
#
# Reads inputs/patient_locations.csv (person_loc_id, lat, lon, start_date,
# end_date), runs the **real** amadeus R package's download_data() to fetch
# GridMET tmmx NetCDFs, then uses **real** terra to open the raster and
# extract per-day per-point values. Writes:
#
#   outputs/_amadeus_raw.csv               raw per-day Kelvin values
#   outputs/_amadeus_attributes.json       R attr() block + SpatRaster summary
#   outputs/_amadeus_session.json          sessionInfo summary
#   outputs/_amadeus_run_meta.json         execution_mode + timestamps
#
# Honest scope note. amadeus 2.0.0's `process_gridmet()` has a layer-name
# parser (`process_parse_ncdf_day_codes`) that expects layer names ending
# `=N` — current GridMET 2022 NetCDFs from the Climatology Lab name layers
# `air_temperature_1, air_temperature_2, ...` without an `=`, so that
# function fails. We bypass that one buggy step by reading the same NetCDF
# with terra::rast() directly and using terra::time() to recover dates
# from the NetCDF's CF-compliant time axis — which is what amadeus does
# internally minus the broken parser. The download is the real amadeus
# call; the extraction is the real terra call. Recorded in the sidecar as
# `execution_mode: "real_amadeus_download_real_terra_extract"`.

suppressPackageStartupMessages({
  library(amadeus)
  library(terra)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("usage: amadeus_extract.R <inputs/patient_locations.csv> <outputs/>")
}
input_csv <- args[[1]]
out_dir   <- args[[2]]
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)

started_at <- format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
locs <- read.csv(input_csv, stringsAsFactors = FALSE)
window_start <- min(locs$start_date)
window_end   <- max(locs$end_date)
years <- seq(as.integer(format(as.Date(window_start), "%Y")),
             as.integer(format(as.Date(window_end),   "%Y")))

# 1. REAL amadeus call — download GridMET tmmx NetCDFs.
work <- file.path(tempdir(), "gridmet_data")
dir.create(work, showWarnings = FALSE, recursive = TRUE)
message("amadeus::download_data(\"gridmet\", variables=\"tmmx\") ...")
amadeus::download_data(
  dataset_name      = "gridmet",
  variables         = "tmmx",
  year              = years,
  directory_to_save = work,
  acknowledgement   = TRUE,
  download          = TRUE
)
nc_files <- list.files(file.path(work, "tmmx"), pattern = "\\.nc$",
                       full.names = TRUE)
if (length(nc_files) == 0) {
  stop("amadeus::download_data succeeded but no .nc files found in ",
       file.path(work, "tmmx"))
}

# 2. REAL terra — open the SpatRaster, recover dates from the CF time axis.
message("terra::rast(", basename(nc_files[[1]]), ") ...")
rast <- terra::rast(nc_files)
# GridMET's time axis is days since 1900-01-01 (CF). terra reads it.
all_dates <- as.Date(terra::time(rast))
# Subset to the study window.
keep <- which(all_dates >= as.Date(window_start) &
              all_dates <= as.Date(window_end))
rast_win <- rast[[keep]]
dates_win <- all_dates[keep]
message("  subsetted to ", length(dates_win), " layers (",
        as.character(dates_win[[1]]), " .. ",
        as.character(dates_win[[length(dates_win)]]), ")")

# 3. REAL terra::extract at residence points.
message("terra::extract(rast_win, points) ...")
pts <- terra::vect(
  data.frame(x = locs$lon, y = locs$lat),
  geom = c("x", "y"),
  crs = "EPSG:4326"
)
ex <- terra::extract(rast_win, pts, ID = FALSE)
# `ex` is one row per location, one column per date. Reshape long.
rows <- list()
for (i in seq_len(nrow(locs))) {
  for (j in seq_along(dates_win)) {
    rows[[length(rows) + 1L]] <- data.frame(
      person_id    = locs$person_loc_id[[i]],
      date         = as.character(dates_win[[j]]),
      lat          = locs$lat[[i]],
      lon          = locs$lon[[i]],
      value_kelvin = as.numeric(ex[i, j])
    )
  }
}
out <- do.call(rbind, rows)
out$value_celsius <- round(out$value_kelvin - 273.15, 2)
out$value_kelvin <- round(out$value_kelvin, 2)

write.csv(out, file.path(out_dir, "_amadeus_raw.csv"), row.names = FALSE)

# 4. Persist R attributes (the metadata amadeus + terra leave in object attrs).
attrs <- list(
  names                = names(out),
  class                = class(out),
  row.names            = c(1, nrow(out)),
  call_download        = "amadeus::download_data(\"gridmet\", variables = \"tmmx\", year = years, directory_to_save = work, acknowledgement = TRUE, download = TRUE)",
  call_process         = "terra::rast(nc_files)  # bypassing amadeus::process_gridmet due to its layer-name parser bug on current GridMET files",
  call_extract         = "terra::extract(rast_win, terra::vect(locs, geom=c('lon','lat'), crs='EPSG:4326'), ID=FALSE)",
  amadeus_version      = as.character(packageVersion("amadeus")),
  terra_version        = as.character(packageVersion("terra")),
  r_version            = R.version.string,
  datetime_started_utc = started_at,
  datetime_done_utc    = format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
  input_locations_n    = nrow(locs),
  input_dates_n        = length(dates_win),
  output_rows          = nrow(out),
  spatraster_summary   = list(
    crs        = terra::crs(rast_win, describe = TRUE)$code,
    resolution = as.numeric(terra::res(rast_win)),
    extent     = as.numeric(as.vector(terra::ext(rast_win))),
    nlyr       = terra::nlyr(rast_win),
    varname    = terra::varnames(rast_win),
    longname   = terra::longnames(rast_win),
    time_axis  = list(
      first = as.character(dates_win[[1]]),
      last  = as.character(dates_win[[length(dates_win)]])
    )
  )
)
writeLines(jsonlite::toJSON(attrs, auto_unbox = TRUE, pretty = TRUE),
           file.path(out_dir, "_amadeus_attributes.json"))

# 5. Persist sessionInfo.
si <- sessionInfo()
session_summary <- list(
  R_version       = R.version.string,
  platform        = R.version$platform,
  amadeus_version = as.character(packageVersion("amadeus")),
  terra_version   = as.character(packageVersion("terra")),
  attached_pkgs   = if (length(si$otherPkgs)) names(si$otherPkgs) else character(),
  locale          = Sys.getlocale()
)
writeLines(jsonlite::toJSON(session_summary, auto_unbox = TRUE, pretty = TRUE),
           file.path(out_dir, "_amadeus_session.json"))

# 6. Persist run metadata.
run_meta <- list(
  execution_mode    = "real_amadeus_download_real_terra_extract",
  notes             = paste(
    "amadeus 2.0.0's process_gridmet() expects NetCDF layer names ending '=N'",
    "but the current GridMET files have plain 'air_temperature_1..365' layer",
    "names, so we bypass amadeus::process_gridmet (which crashes on these",
    "files) and use terra::rast + terra::time + terra::extract directly.",
    "The download and the extraction kernel are still the real amadeus +",
    "terra stack; only the buggy process_gridmet glue function is bypassed."
  ),
  amadeus_version   = as.character(packageVersion("amadeus")),
  terra_version     = as.character(packageVersion("terra")),
  r_version         = R.version.string,
  rocker_image      = "rocker/geospatial:4.4",
  envar_image       = "envar-amadeus:4.4",
  started_at_utc    = started_at,
  completed_at_utc  = format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
)
writeLines(jsonlite::toJSON(run_meta, auto_unbox = TRUE, pretty = TRUE),
           file.path(out_dir, "_amadeus_run_meta.json"))

cat("done. wrote", nrow(out), "rows to", out_dir, "\n")
