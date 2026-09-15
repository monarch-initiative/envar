#!/usr/bin/env Rscript
# amadeus_extract.R -- EPA AQS, real amadeus download + MANUAL point join
#
# LOWEST-CONFIDENCE of the 3 R scripts, and deliberately so -- read this
# header before running.
#
# amadeus's own CRAN documentation states: "AQS measurements are
# generally intended for use as dependent variables, so the package
# supports download and processing for AQS but does not expose AQS
# through calculate_covariates()." (see
# curator/known-issues.md item 4). So unlike PRISM/NARR, this
# script can only confirm the DOWNLOAD half of the pipeline against
# amadeus's real API; the point-in-time nearest-monitor extraction below
# is hand-written against EPA's own PUBLIC daily-summary file format
# (State Code, County Code, Site Num, Latitude, Longitude, Date Local,
# Arithmetic Mean, 1st Max Value, ... -- this column layout is publicly
# documented by EPA, e.g. https://aqs.epa.gov/aqsweb/airdata/FileFormats.html,
# not amadeus-specific), NOT verified against amadeus's actual
# download_data(dataset_name="aqs", ...) output file structure in this
# session. If amadeus post-processes the file differently, the column
# names below may not match -- inspect the downloaded file first.
#
# No NASA Earthdata token needed: setup_nasa_token() is only required for
# modis/merra2/geos/population in amadeus. AQS is not in that list.
#
# Requirements (install once):
#   install.packages(c("amadeus", "jsonlite", "digest"))
#
# Usage:
#   Rscript amadeus_extract.R
#
# Writes:
#   outputs/aqs_all_params.csv   -- same shape as the Python run.py's offline output
#   outputs/run_manifest.json    -- execution_mode = "real_amadeus", real hashes,
#                                    with the manual-join caveat recorded explicitly

library(amadeus)
library(jsonlite)
library(digest)

HERE <- dirname(sys.frame(1)$ofile %||% normalizePath("."))
if (is.null(HERE) || HERE == "") HERE <- getwd()

# Parameter codes confirmed against EPA's own AQS documentation (AQS
# Concepts / AQS Basics), not amadeus-specific.
PARAMS <- c(pm25 = 88101L, pm10 = 81102L, co = 42101L, no2 = 42602L, so2 = 42401L)
YEAR <- 2022L
DATE_START <- "2022-07-15"
DATE_END <- "2022-07-22"
MAX_DISTANCE_M <- 50000  # matches linkage_max_distance_to_station_m in the sidecars

# ---- 1. Load the one shared, static cohort file (see ../../README.md) ----
input_path <- file.path(HERE, "..", "..", "input", "patient_locations.csv")
input_df <- read.csv(input_path, stringsAsFactors = FALSE)
locs <- data.frame(id = as.character(input_df$person_id), lon = input_df$lon, lat = input_df$lat)

download_dir <- file.path(tempdir(), "amadeus_aqs")
dir.create(download_dir, showWarnings = FALSE, recursive = TRUE)

# Haversine distance in meters -- no extra package dependency for this
haversine_m <- function(lon1, lat1, lon2, lat2) {
  R <- 6371000
  to_rad <- pi / 180
  dlat <- (lat2 - lat1) * to_rad
  dlon <- (lon2 - lon1) * to_rad
  a <- sin(dlat / 2)^2 + cos(lat1 * to_rad) * cos(lat2 * to_rad) * sin(dlon / 2)^2
  2 * R * asin(sqrt(a))
}

# ---- 2. Download each parameter (CONFIRMED amadeus step) ----
downloaded_files <- list()
for (col_name in names(PARAMS)) {
  p <- PARAMS[[col_name]]
  message(sprintf("AQS %s (param %d): downloading...", col_name, p))
  download_data(
    dataset_name = "aqs",
    year = YEAR,
    parameter_code = p,
    directory_to_save = download_dir,
    acknowledgement = TRUE,
    download = TRUE,
    hash = TRUE
  )
  # UNCONFIRMED: exact output filename/path amadeus writes to. EPA's own
  # public daily-summary files are named daily_<param>_<year>.csv once
  # unzipped -- assumed here, not verified against amadeus's actual
  # directory_to_save behavior in this session.
  candidate <- list.files(download_dir, pattern = sprintf("daily_%d_%d.*\\.csv$", p, YEAR),
                           recursive = TRUE, full.names = TRUE)
  if (length(candidate) == 0) {
    stop(sprintf(
      "Could not find a downloaded daily summary CSV for parameter %d under %s. ",
      p, download_dir
    ), "List the directory manually (list.files(download_dir, recursive=TRUE)) ",
    "and fix the `candidate` pattern above to match what amadeus actually wrote.")
  }
  downloaded_files[[col_name]] <- candidate[1]
}

# ---- 3. MANUAL nearest-monitor join -- NOT part of amadeus's confirmed
#         API (see header). Column names below assume EPA's public
#         daily-summary layout; verify against the real downloaded file
#         if this errors. ----
extract_nearest <- function(csv_path, target_lon, target_lat, date_start, date_end) {
  daily <- read.csv(csv_path, stringsAsFactors = FALSE)
  # Expected columns (EPA public format): Latitude, Longitude, Date.Local,
  # Arithmetic.Mean (R's read.csv mangles "Date Local" -> "Date.Local" etc.)
  daily <- daily[daily$Date.Local >= date_start & daily$Date.Local <= date_end, ]
  if (nrow(daily) == 0) return(NULL)

  monitors <- unique(daily[, c("Latitude", "Longitude")])
  monitors$dist_m <- haversine_m(target_lon, target_lat, monitors$Longitude, monitors$Latitude)
  monitors <- monitors[order(monitors$dist_m), ]
  nearest <- monitors[1, ]
  if (nearest$dist_m > MAX_DISTANCE_M) {
    warning(sprintf("Nearest monitor is %.0fm away, beyond MAX_DISTANCE_M=%d", nearest$dist_m, MAX_DISTANCE_M))
  }

  sub <- daily[daily$Latitude == nearest$Latitude & daily$Longitude == nearest$Longitude, ]
  data.frame(date = sub$Date.Local, value = sub$Arithmetic.Mean, monitor_distance_m = nearest$dist_m)
}

results <- list()
monitor_distances <- list()
for (col_name in names(PARAMS)) {
  per_patient <- list()
  for (i in seq_len(nrow(locs))) {
    r <- extract_nearest(downloaded_files[[col_name]], locs$lon[i], locs$lat[i], DATE_START, DATE_END)
    if (!is.null(r)) {
      r$person_id <- locs$id[i]
      per_patient[[i]] <- r
    }
  }
  combined <- do.call(rbind, per_patient)
  names(combined)[names(combined) == "value"] <- col_name
  results[[col_name]] <- combined[, c("person_id", "date", col_name, "monitor_distance_m")]
}

# ---- 4. Merge into one wide table (pm25's monitor_distance_m kept as
#         THE representative one, matching the Python offline output's
#         single monitor_distance_m column -- each pollutant may in
#         reality have a different nearest monitor; not modeled here) ----
wide <- results[["pm25"]]
names(wide)[names(wide) == "pm25"] <- "value"
for (col_name in setdiff(names(PARAMS), "pm25")) {
  other <- results[[col_name]][, c("person_id", "date", col_name)]
  wide <- merge(wide, other, by = c("person_id", "date"), all = TRUE)
}
wide <- merge(wide, data.frame(person_id = locs$id, lat = locs$lat, lon = locs$lon), by = "person_id")
wide <- wide[, c("person_id", "date", "lat", "lon", "value", "monitor_distance_m",
                  setdiff(names(PARAMS), "pm25"))]

# ---- 5. Write companion CSV (same shape as the Python offline output) ----
outputs_dir <- file.path(HERE, "outputs", "real")
dir.create(file.path(outputs_dir, "envar"), showWarnings = FALSE, recursive = TRUE)
out_csv <- file.path(outputs_dir, "aqs_all_params.csv")
write.csv(wide, out_csv, row.names = FALSE)

# ---- 6. Write run_manifest.json, with the manual-join caveat explicit ----

manifest <- list(
  dataset_short_code = "aqs",
  variable_name = as.list(paste0(names(PARAMS), "_", unname(PARAMS))),
  tool_name = "amadeus",
  tool_version = as.character(packageVersion("amadeus")),
  r_version = R.version.string,
  execution_mode = "real_amadeus",
  run_timestamp_utc = format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
  r_call = paste(
    "for (p in c(", paste(unname(PARAMS), collapse = ", "), ")) {",
    "download_data(dataset_name='aqs', year=2022, parameter_code=p, ...) }; ",
    "<point extraction below is MANUAL R code, NOT amadeus -- see script header>"
  ),
  input_file = "../../input/patient_locations.csv",
  input_file_sha256 = digest(input_path, algo = "sha256", file = TRUE),
  input_row_count = nrow(locs),
  output_file = "outputs/real/aqs_all_params.csv",
  output_file_sha256 = digest(out_csv, algo = "sha256", file = TRUE),
  output_row_count = nrow(wide),
  output_columns = as.list(names(wide)),
  extraction_window_start = DATE_START,
  extraction_window_end = DATE_END,
  raster_reported = list(resolution_m = NULL, crs = NULL, native_units_as_stored = NULL),
  "_honesty_note" = paste(
    "execution_mode=real_amadeus, but ONLY the download step used amadeus's",
    "confirmed API. The nearest-monitor point extraction is hand-written R",
    "code against EPA's public daily-summary file format, assumed (not",
    "verified against amadeus's actual output) to match what download_data()",
    "wrote. See this script's header comment and known-issues.md item 4."
  )
)
write(toJSON(manifest, auto_unbox = TRUE, pretty = TRUE, null = "null"),
      file.path(outputs_dir, "run_manifest.json"))

message(sprintf("Wrote %s (%d rows)", out_csv, nrow(wide)))
message(sprintf("Wrote %s", file.path(outputs_dir, "run_manifest.json")))
message("NOTE: verify downloaded_files' column names against the real file")
message("before trusting extract_nearest()'s output -- see script header.")
