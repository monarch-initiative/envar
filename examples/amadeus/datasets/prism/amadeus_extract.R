#!/usr/bin/env Rscript
# amadeus_extract.R -- PRISM, real amadeus (no Docker, no credentials needed)
#
# Uses amadeus's actual 3-function API, confirmed against the package's
# own download_data vignette (a NARR weasd example was shared during this
# project, showing the real call shape -- this script follows the same
# pattern for PRISM by analogy; PRISM's exact download_data() argument
# names were NOT independently confirmed the way NARR's were, so if
# anything below errors, check ?amadeus::download_data first).
#
# No NASA Earthdata token needed: setup_nasa_token() is only required for
# modis/merra2/geos/population in amadeus. PRISM is not in that list.
#
# Requirements (install once):
#   install.packages(c("amadeus", "jsonlite", "digest", "sf"))
#
# Usage:
#   Rscript amadeus_extract.R
#
# Writes:
#   outputs/prism_all_vars.csv   -- same shape as the Python run.py's offline output
#   outputs/run_manifest.json    -- execution_mode = "real_amadeus", real hashes

library(amadeus)
library(jsonlite)
library(digest)

HERE <- dirname(sys.frame(1)$ofile %||% normalizePath("."))
if (is.null(HERE) || HERE == "") HERE <- getwd()

PRISM_VARS <- c("tmax", "tmin", "tmean", "tdmean", "ppt", "vpdmin", "vpdmax")
YEAR <- 2022L
DATE_START <- "2022-07-15"
DATE_END <- "2022-07-22"

# ---- 1. Load the one shared, static cohort file (see ../../README.md) ----
input_path <- file.path(HERE, "..", "..", "input", "patient_locations.csv")
input_df <- read.csv(input_path, stringsAsFactors = FALSE)
locs <- data.frame(id = as.character(input_df$person_id), lon = input_df$lon, lat = input_df$lat)

download_dir <- file.path(tempdir(), "amadeus_prism")
dir.create(download_dir, showWarnings = FALSE, recursive = TRUE)

# ---- 2. For each variable: download -> process -> extract at points ----
results <- list()
for (v in PRISM_VARS) {
  message(sprintf("PRISM %s: downloading...", v))
  download_data(
    dataset_name = "prism",
    year = YEAR,
    variable = v,
    directory_to_save = download_dir,
    acknowledgement = TRUE,
    download = TRUE,
    hash = TRUE
  )

  message(sprintf("PRISM %s: processing...", v))
  proc <- process_covariates(
    covariate = "prism",
    date = c(DATE_START, DATE_END),
    variable = v,
    path = file.path(download_dir, v),
    extent = NULL
  )

  message(sprintf("PRISM %s: extracting at %d locations...", v, nrow(locs)))
  covar <- calculate_covariates(
    covariate = "prism",
    from = proc,
    locs = locs,
    locs_id = "id",
    radius = 0,
    geom = "sf"
  )

  # calculate_covariates()'s value column naming was shown in the shared
  # example as "<variable>_0" (radius=0 suffix, e.g. "weasd_0"). Matched
  # here by pattern rather than hardcoded, since PRISM's exact suffix
  # wasn't independently confirmed -- if this grep finds nothing, inspect
  # names(covar) and fix the pattern.
  value_col <- grep(paste0("^", v, "(_|$)"), names(covar), value = TRUE)[1]
  if (is.na(value_col)) stop(sprintf("Could not find value column for '%s' in calculate_covariates() output -- inspect names(covar) and fix the grep pattern above.", v))

  df <- sf::st_drop_geometry(covar)[, c("id", "time", value_col)]
  names(df) <- c("person_id", "date", v)
  results[[v]] <- df
}

# ---- 3. Merge all variables into one wide table ----
wide <- Reduce(function(a, b) merge(a, b, by = c("person_id", "date"), all = TRUE), results)
wide <- merge(wide, data.frame(person_id = locs$id, lat = locs$lat, lon = locs$lon), by = "person_id")
wide <- wide[, c("person_id", "date", "lat", "lon", PRISM_VARS)]

# ---- 4. Write companion CSV (same shape as the Python offline output) ----
outputs_dir <- file.path(HERE, "outputs", "real")
dir.create(file.path(outputs_dir, "envar"), showWarnings = FALSE, recursive = TRUE)
out_csv <- file.path(outputs_dir, "prism_all_vars.csv")
write.csv(wide, out_csv, row.names = FALSE)

# ---- 5. Write run_manifest.json with REAL facts about this run ----

manifest <- list(
  dataset_short_code = "prism",
  variable_name = as.list(PRISM_VARS),
  tool_name = "amadeus",
  tool_version = as.character(packageVersion("amadeus")),
  r_version = R.version.string,
  execution_mode = "real_amadeus",
  run_timestamp_utc = format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
  r_call = paste(
    "for (v in c(", paste(sprintf("'%s'", PRISM_VARS), collapse = ", "), ")) {",
    "download_data(dataset_name='prism', year=2022, variable=v, ...); ",
    "proc <- process_covariates(covariate='prism', date=c('2022-07-15','2022-07-22'), variable=v, ...); ",
    "calculate_covariates(covariate='prism', from=proc, locs=locs, locs_id='id', radius=0, geom='sf') }"
  ),
  input_file = "../../input/patient_locations.csv",
  input_file_sha256 = digest(input_path, algo = "sha256", file = TRUE),
  input_row_count = nrow(locs),
  output_file = "outputs/real/prism_all_vars.csv",
  output_file_sha256 = digest(out_csv, algo = "sha256", file = TRUE),
  output_row_count = nrow(wide),
  output_columns = as.list(names(wide)),
  extraction_window_start = DATE_START,
  extraction_window_end = DATE_END,
  raster_reported = list(resolution_m = NULL, crs = NULL, native_units_as_stored = NULL),
  "_honesty_note" = paste(
    "execution_mode=real_amadeus: this manifest describes an ACTUAL amadeus",
    "run, not a synthetic fixture. raster_reported fields left null because",
    "this script does not currently inspect proc's terra::res()/terra::crs()",
    "-- add that if you need it recorded (see prism's Python run.py",
    "for the shape those fields should take)."
  )
)
write(toJSON(manifest, auto_unbox = TRUE, pretty = TRUE, null = "null"),
      file.path(outputs_dir, "run_manifest.json"))

message(sprintf("Wrote %s (%d rows)", out_csv, nrow(wide)))
message(sprintf("Wrote %s", file.path(outputs_dir, "run_manifest.json")))
message("Next: curate/validate exactly as with the Python offline path -- ")
message("the manifest shape is identical, so SKILL.md's procedure and")
message("curator/validate.py both work unchanged against this real output.")
