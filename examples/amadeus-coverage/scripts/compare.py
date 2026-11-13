"""Amadeus (23 datasets) vs EnVar LinkML microschema — coverage mapping.

Evidence: amadeus help pages (man/*.Rd, rendered via tools::Rd2txt) and
inst/REFERENCES.bib; EnVar schema src/linkml_microschemas_envar/schema/*.yaml.
Status per (dataset, EnVar slot):
  full     - Amadeus exposes the value explicitly (argument, documented fixed
             fact, or documented output column/attribute)
  partial  - Amadeus has it only implicitly / only in prose or references /
             in a non-conforming form (e.g. xxhash instead of SHA-256)
  envar    - EnVar slot with nothing on the Amadeus side
  na       - slot not applicable to this dataset
"""
import json, csv, collections, os

import sys
W = sys.argv[1] if len(sys.argv) > 1 else 'outputs'
fam = json.load(open(f'{W}/fam.json'))
slots_raw = json.load(open(f'{W}/envar_slots.json'))

COMPOSITE = {'variable_identity','spatial_reference','temporal_reference','exposure_model','uncertainty',
             'derived_heat_metric','data_layout','source_dataset','tool_run','provenance_chain',
             'linkage_method','health_layer_linkage','deposit_metadata','equation_inputs',
             'model_aggregate_uncertainty'}
SLOTS = [(c, s, t) for c, s, t, r, q in slots_raw
         if s not in COMPOSITE and not s.endswith('_missing_reason') and c != 'ModelAggregateUncertainty']
# de-dup keep first
seen=set(); SL=[]
for c,s,t in SLOTS:
    if s in seen: continue
    seen.add(s); SL.append((c,s,t or 'optional'))
SLOTS=SL

# slots that are the health-linkage / deposit / record envelope: outside a data-access package's job
OUT_OF_AMADEUS_SCOPE = {'subject','schema_version','provenance_id','phi_status',
    'geocoding_precision_propagated','geocoding_score_propagated','address_period_alignment',
    'clinical_date_assignment_convention','partial_day_attribution_rule','privacy_transformation',
    'privacy_transformation_note','target_concept_vocabulary','target_concept_id','concept_status',
    'health_layer_target','health_layer_link_field','cohort_size_anchored','deposit_doi',
    'deposit_repository','deposit_license_spdx','deposit_redistribution_constraints_inherited',
    'recommended_citation','dcat_distribution_url'}

# ---------------------------------------------------------------- dataset profiles
D = collections.OrderedDict()
def ds(code, name, genre, extent, formats, tres, tres_ok, mtype, mtype_ok, **kw):
    D[code] = dict(code=code, name=name, genre=genre, extent=extent, formats=formats, tres=tres,
                   tres_ok=tres_ok, model_type=mtype, model_ok=mtype_ok, **kw)

# formats_ok: does SourceNativeFormatEnum have a value for every native format?
ds('terraclimate','Climatology Lab TerraClimate','Meteorology','Global',['netCDF'],'monthly',True,'statistical_blend (climatically aided interpolation)',True,
   fmt_ok=True, res='~4 km (1/24°) — not stated in docs', res_doc=False, temp=True, static=False, daily=False, cite=True, doi=False, producer=True, version=False, coverage_doc=False)
ds('gridmet','Climatology Lab GridMET','Climate, Water','CONUS',['netCDF'],'daily (+ 5-day pentads for SPEI/EDDI)',False,'statistical_blend',True,
   fmt_ok=True, res='1/24° (~4 km) stated', res_doc=True, temp=True, static=False, daily=True, cite=True, doi=False, producer=True, version=False, coverage_doc=False)
ds('koppen_geiger','Köppen-Geiger Climate Classification','Climate Classification','Global',['GeoTIFF'],'static climatology (1980-2016) / future scenario (2071-2100)',False,'classification derived from climate-model ensemble',False,
   fmt_ok=True, res='data_resolution arg', res_doc=True, temp=False, static=True, daily=False, cite=True, doi=True, producer=False, version=False, coverage_doc=True)
ds('nlcd','MRLC NLCD','Land Use','United States',['GeoTIFF'],'annual (1985-2024)',True,'land-cover classification from satellite imagery',False,
   fmt_ok=True, res='30 m stated', res_doc=True, temp=False, static=False, daily=False, cite=True, doi=True, producer=True, version=False, coverage_doc=True)
ds('cropscape','USDA CropScape CDL','Land Use, Agriculture','United States',['GeoTIFF'],'annual (2008-)',True,'land-cover classification from satellite imagery',False,
   fmt_ok=True, res='30 m — not stated in docs', res_doc=False, temp=False, static=False, daily=False, cite=False, doi=False, producer=True, version=False, coverage_doc=True)
ds('modis','NASA MODIS (MOD/MYD/MCD products, VNP46)','Atmosphere, Meteorology, Land Use, Satellite','Global',['HDF4-EOS','HDF5'],'daily / 8-day / 16-day composites',False,'satellite_retrieval',True,
   fmt_ok=False, res='resolution / cellsize args (swath warp)', res_doc=True, temp=True, static=False, daily=True, cite=True, doi=True, producer=True, version=True, coverage_doc=False)
ds('merra2','NASA MERRA-2','Atmosphere, Meteorology','Global',['netCDF'],'hourly / 3-hourly / daily (by collection)',True,'reanalysis',True,
   fmt_ok=True, res='0.5°×0.625° — not stated in docs', res_doc=False, temp=True, static=False, daily=True, cite=False, doi=False, producer=True, version=False, coverage_doc=False)
ds('population','NASA SEDAC UN WPP-Adjusted Population Density','Population','Global',['GeoTIFF','netCDF','ASCII grid'],'5-year epochs (2000-2020)',False,'census-based dasymetric allocation',False,
   fmt_ok=False, res='data_resolution arg', res_doc=True, temp=False, static=False, daily=False, cite=True, doi=True, producer=True, version=False, coverage_doc=False)
ds('groads','NASA SEDAC gROADS','Roadways','Global',['Shapefile','File Geodatabase'],'static (1980-2010 compilation)',False,'compiled vector road network',False,
   fmt_ok=False, res='vector lines', res_doc=True, temp=False, static=True, daily=False, cite=True, doi=True, producer=True, version=False, coverage_doc=True, vector=True)
ds('huc','USGS Hydrologic Unit Codes (NHDPlus v2.1)','Hydrology','United States',['File Geodatabase','Shapefile'],'static',False,'reference boundary delineation',False,
   fmt_ok=False, res='vector polygons (HUC12)', res_doc=True, temp=False, static=True, daily=False, cite=True, doi=False, producer=True, version=True, coverage_doc=False, vector=True)
ds('geos','NASA GEOS-CF','Atmosphere, Meteorology','Global',['netCDF'],'hourly (tavg / inst)',True,'chemical_transport_model',True,
   fmt_ok=True, res='0.25° (g1440x721 in collection name)', res_doc=True, temp=True, static=False, daily=True, cite=True, doi=True, producer=True, version=False, coverage_doc=False)
ds('edgar','EDGAR emissions','Emissions','Global',['netCDF','TXT'],'yearly / monthly',True,'emission inventory (activity × emission factor)',False,
   fmt_ok=False, res='0.1° — not stated in docs', res_doc=False, temp=False, static=False, daily=False, cite=False, doi=False, producer=False, version=True, coverage_doc=True)
ds('hms','NOAA HMS Fire and Smoke','Wildfire Smoke','North America',['Shapefile','KML'],'daily',True,'analyst-digitized from satellite imagery',False,
   fmt_ok=False, res='vector polygons', res_doc=True, temp=False, static=False, daily=True, cite=True, doi=False, producer=True, version=False, coverage_doc=False, vector=True)
ds('goes','NOAA GOES-16/18 ADP','Atmosphere, Satellite','Americas, Pacific',['netCDF'],'~5-minute scans (sub-hourly)',False,'satellite_retrieval',True,
   fmt_ok=True, res='2 km fixed grid — not stated', res_doc=False, temp=False, static=False, daily=True, cite=False, doi=False, producer=True, version=False, coverage_doc=False)
ds('narr','NOAA NCEP NARR','Atmosphere, Meteorology','North America',['netCDF'],'daily',True,'reanalysis',True,
   fmt_ok=True, res='32 km — not stated', res_doc=False, temp=True, static=False, daily=True, cite=True, doi=True, producer=True, version=False, coverage_doc=False)
ds('prism','PRISM Climate Group','Meteorology, Climate','CONUS',['netCDF','ASCII grid','BIL','GRIB2'],'daily/monthly/annual time series + 30-year normals',False,'statistical_blend (PRISM regression)',True,
   fmt_ok=False, res='4 km ts / 800 m normals stated', res_doc=True, temp=True, static=False, daily=True, cite=True, doi=True, producer=True, version=False, coverage_doc=False)
ds('drought','Drought indices (SPEI, EDDI, USDM)','Drought','Global / CONUS',['netCDF','ASCII grid','Shapefile'],'monthly (SPEI) / weekly (EDDI, USDM)',False,'equation_derived (SPEI/EDDI); expert consensus (USDM)',False,
   fmt_ok=False, res='0.5° SPEI, ~4 km EDDI, polygons USDM — not stated', res_doc=False, temp=False, static=False, daily=False, cite=False, doi=False, producer=True, version=False, coverage_doc=False)
ds('aqs','US EPA AQS pre-generated files','Air Pollution','United States',['CSV'],'daily',True,'direct_measurement',True,
   fmt_ok=True, res='point monitors', res_doc=True, temp=False, static=False, daily=True, cite=True, doi=False, producer=True, version=False, coverage_doc=False, station=True, vector=True)
ds('improve','IMPROVE aerosol network','Air Pollution, Aerosols','United States',['TXT (pipe-delimited)'],'daily, every-third-day schedule',False,'direct_measurement',True,
   fmt_ok=False, res='point monitors', res_doc=True, temp=False, static=False, daily=True, cite=False, doi=False, producer=True, version=False, coverage_doc=False, station=True, vector=True)
ds('ecoregion','US EPA Ecoregions (L2/L3)','Climate Regions','North America',['Shapefile'],'static',False,'expert-delineated reference regions',False,
   fmt_ok=False, res='vector polygons', res_doc=True, temp=False, static=True, daily=False, cite=True, doi=True, producer=True, version=False, coverage_doc=False, vector=True)
ds('nei','US EPA NEI (on-road)','Emissions','United States',['CSV'],'annual (triennial: 2017, 2020)',True,'emission inventory',False,
   fmt_ok=False, res='county polygons', res_doc=True, temp=False, static=False, daily=False, cite=True, doi=False, producer=True, version=False, coverage_doc=False, vector=True)
ds('tri','US EPA TRI','Chemicals, Pollution','United States',['CSV'],'annual',True,'facility self-reported inventory',False,
   fmt_ok=False, res='facility points', res_doc=True, temp=False, static=False, daily=False, cite=True, doi=False, producer=True, version=False, coverage_doc=False, vector=True)
ds('gmted','USGS GMTED2010','Elevation','Global',['ESRI ASCII Grid'],'static (2010 release)',False,'DEM aggregated from multiple source DEMs',False,
   fmt_ok=False, res='resolution arg (7.5/15/30 arc-sec)', res_doc=True, temp=False, static=True, daily=False, cite=True, doi=True, producer=True, version=True, coverage_doc=False)

for k, v in D.items():
    v['fns'] = fam[k]['fns']; v['args'] = set(fam[k]['args']); v['has_url'] = fam[k]['has_url']
    v['calc'] = any(f.startswith('calculate_') for f in v['fns'])
    v.setdefault('vector', False); v.setdefault('station', False)
    v['netcdf'] = any('netCDF' in f or 'HDF' in f for f in v['formats'])

URL_IN_CODE_ONLY = {'terraclimate','koppen_geiger','nlcd','cropscape','merra2','population','hms','prism','ecoregion','tri','gmted'}
DOC_LABELS = {'narr','gridmet','terraclimate','aqs','geos','prism','edgar','nlcd','ecoregion','improve','gmted','merra2','modis','tri','population'}
CATEGORICAL_FULL = {'koppen_geiger','ecoregion','hms'}
CATEGORICAL_PARTIAL = {'nlcd','cropscape','drought','huc','groads'}
DAILY_UTC_DOC = {'merra2','geos','goes'}
TMAX_LIKE = {'gridmet','terraclimate','prism','narr','merra2'}
EXPLICIT_CRS = {'goes','drought','modis'}

def status(d, c, s):
    a = d['args']; calc = d['calc']; k = d['code']
    if c in ('DerivedHeatMetric', 'EquationInput'):
        if s == 'heat_metric_family' and k in TMAX_LIKE: return 'partial'
        return 'na'
    if c in ('HealthLayerLinkage', 'DepositMetadata'): return 'envar'
    if c == 'EnvironmentalExposureRecord': return 'envar'
    # ---- VariableIdentity
    if s == 'variable_name': return 'full'
    if s == 'variable_label': return 'partial' if k in DOC_LABELS else 'envar'
    if s == 'cf_cell_methods': return 'partial' if k == 'gmted' else 'envar'
    if s in ('units_ucum','units_display'): return 'partial' if k in ('groads','improve') else 'envar'
    if s == 'native_units_ucum': return 'partial' if k == 'improve' else 'envar'
    if s in ('native_value_scale_factor','native_value_offset','unit_conversion_formula'):
        if k == 'modis': return 'partial'
        return 'envar' if d['netcdf'] else 'na'
    if s == 'concept_mappings': return 'partial' if k in ('tri','aqs') else 'envar'
    if s in ('target_concept_vocabulary','target_concept_id','concept_status'): return 'envar'
    if s == 'value_data_type':
        return 'full' if k in CATEGORICAL_FULL else 'partial' if k in CATEGORICAL_PARTIAL else 'envar'
    if s in ('value_range_plausible_min','value_range_plausible_max'): return 'partial' if k == 'drought' else 'envar'
    if s == 'standard_name': return 'envar'
    # ---- DataLayout
    if s == 'table_orientation': return 'full' if calc else 'partial'
    if s == 'value_column': return 'full' if calc else 'partial'
    if s in ('variable_column','variable_key'): return 'full' if k == 'improve' else 'na'
    if s == 'subject_column': return 'full' if calc else 'partial'
    if s == 'time_column':
        if k in ('huc','ecoregion'): return 'na'
        return 'full' if calc else 'partial'
    if s == 'native_value_column': return 'na'
    if s == 'value_uncertainty_column': return 'partial' if k == 'nlcd' else 'envar'
    if s == 'quality_flag_column': return 'partial' if k in ('improve','aqs','modis') else 'envar'
    if s == 'null_semantics_column': return 'partial' if k in ('hms','groads','aqs','nlcd','ecoregion') else 'envar'
    # ---- SpatialReference
    if s == 'native_spatial_resolution_m':
        if d['vector']: return 'na'
        return 'full' if d['res_doc'] else 'envar'
    if s == 'native_spatial_resolution_descriptor': return 'full' if d['res_doc'] else 'envar'
    if s == 'crs': return 'full' if k in EXPLICIT_CRS else 'partial'
    if s == 'spatial_extent_bbox': return 'full' if 'extent' in a else 'envar'
    if s == 'spatial_extent_descriptor': return 'full'
    if s == 'extraction_method':
        if not calc: return 'na'
        return 'partial' if k in ('tri','koppen_geiger','ecoregion','huc','hms','nei') else 'full'
    if s == 'extraction_buffer_m':
        if not calc or k in ('huc','nei'): return 'na'
        return 'full'
    if s == 'population_weighting_source': return 'partial' if calc else 'na'
    if s == 'target_geography_type': return 'partial' if calc else 'na'
    if s == 'spatial_aggregation_preserves': return 'envar' if calc else 'na'
    # ---- TemporalReference
    if s == 'temporal_resolution': return 'full' if d['tres_ok'] else 'partial'
    if s == 'temporal_aggregation_method':
        if 'daily_agg' in a or '.by_time' in a: return 'full'
        return 'na' if d['static'] else 'envar'
    if s == 'temporal_aggregation_window_seconds':
        if 'daily_agg' in a or '.by_time' in a: return 'partial'
        return 'na' if d['static'] else 'envar'
    if s == 'day_boundary_convention':
        if k in DAILY_UTC_DOC: return 'full'
        return 'envar' if d['daily'] else 'na'
    if s in ('temporal_coverage_start','temporal_coverage_end'):
        return 'partial' if d['coverage_doc'] else 'envar'
    if s in ('extraction_window_start','extraction_window_end'):
        if k in ('gmted','huc','ecoregion','groads'): return 'na'
        if k == 'koppen_geiger': return 'partial'
        return 'full'
    if s == 'calendar': return 'envar' if d['netcdf'] else 'na'
    # ---- ExposureModel
    if s == 'exposure_model_type': return 'envar'
    if s == 'exposure_model_inputs': return 'partial' if k == 'modis' else 'envar'
    if s == 'exposure_model_paper_doi': return 'partial' if k in ('narr','geos','koppen_geiger','prism','ecoregion') else 'envar'
    if s == 'exposure_model_ensemble_member_count': return 'na'
    if s in ('exposure_model_cross_validation_r2','exposure_model_known_biases','bias_correction_applied'): return 'na' if d['station'] else 'envar'
    # ---- Uncertainty
    if s == 'quality_flag_vocabulary': return 'partial' if k in ('improve','aqs','modis') else 'envar'
    if s == 'missing_data_handling_method':
        if k == 'gridmet': return 'full'
        return 'partial' if k == 'aqs' else 'envar'
    if s == 'data_completeness_pct': return 'partial' if k in ('modis','improve') else 'envar'
    if s in ('per_value_uncertainty_type','per_value_uncertainty_units_ucum'): return 'partial' if k == 'nlcd' else 'envar'
    if s in ('model_aggregate_uncertainty','missing_value_sentinel'): return 'envar'
    # ---- SourceDataset
    if s in ('source_dataset_name','source_dataset_short_code','source_dataset_spatial_extent'): return 'full'
    if s == 'source_dataset_doi': return 'partial' if k in ('groads','population','nlcd','modis','gmted') else 'envar'
    if s == 'source_dataset_version': return 'full' if d['version'] else 'envar'
    if s == 'source_dataset_temporal_coverage': return 'partial' if d['coverage_doc'] else 'envar'
    if s == 'source_producer_institution': return 'full' if d['producer'] else 'partial'
    if s in ('source_citation_apa','source_citation_bibtex'): return 'partial' if d['cite'] else 'envar'
    if s == 'source_license_spdx': return 'envar'
    if s == 'source_access_url': return 'partial' if k in URL_IN_CODE_ONLY else 'full'
    if s == 'source_native_format': return 'full' if d['fmt_ok'] else 'partial'
    if s == 'source_homogenisation_status': return 'envar' if d['station'] else 'na'
    if s == 'source_acdd_attributes': return 'envar' if d['netcdf'] else 'na'
    # ---- ToolRun / ProvenanceChain
    if s in ('tool_name','tool_version','tool_description','run_arguments','input_file_sha256'): return 'partial'
    if s in ('container_image_repository','container_image_digest','run_timestamp_utc','run_duration_seconds',
             'run_environment','input_row_count','output_file_sha256','output_row_count','run_log_excerpt'): return 'envar'
    if s == 'provenance_chain_terminus_type': return 'partial'
    if s == 'provenance_chain_steps': return 'partial' if k == 'ecoregion' else 'envar'
    if s == 'chain_compatibility_assertions': return 'envar'
    # ---- LinkageMethod
    if s == 'linkage_strategy': return 'full' if calc else 'na'
    if s == 'linkage_buffer_radius_m':
        if not calc or k in ('huc','nei'): return 'na'
        return 'full'
    if s == 'linkage_buffer_aggregation_method':
        if not calc or k in ('huc','nei'): return 'na'
        return 'full' if ('fun' in a or 'fun_summary' in a) else 'partial'
    if s == 'linkage_max_distance_to_station_m': return 'na'
    if s == 'linkage_working_crs': return 'partial' if calc else 'na'
    if s in ('lag_alignment_applied','lag_alignment_specifier'):
        if not calc or d['static']: return 'na'
        return 'partial'
    if s in OUT_OF_AMADEUS_SCOPE: return 'envar'
    raise KeyError((c, s))

# ---------------------------------------------------------------- Amadeus-side elements
# Operational arguments are excluded from the comparison universe (download/runtime plumbing).
OPERATIONAL = {'directory_to_save','acknowledgement','download','remove_command','show_progress','max_tries',
    'rate_limit','unzip','remove_zip','geom','include_file','return_format','return_type','max_cells',
    'package_list_add','export_list_add','ignore_case','include_na','suffix','string','invert','data',
    'epa_certificate_path','certificate_url','layer_name','path','...','from','preprocess','date_start','date_end',
    'name_extracted','nasa_earth_data_token'}
# semantic argument -> EnVar slot it lands on (None => no EnVar home)
ARG_MAP = {
 'variables':'variable_name','variable':'variable_name','element':'variable_name','species':'variable_name',
 'parameter_code':'variable_name','subdataset':'variable_name','data_field':'value_column','voc':'variable_name',
 'chemical':'concept_mappings','year':'extraction_window_start','date':'extraction_window_start','time':'extraction_window_start',
 'year_range':'extraction_window_start','extent':'spatial_extent_bbox','version':'source_dataset_version',
 'data_resolution':'native_spatial_resolution_descriptor','resolution':'native_spatial_resolution_descriptor',
 'data_format':'source_native_format','format':'source_native_format','radius':'linkage_buffer_radius_m',
 'decay_range':'linkage_buffer_radius_m','fun':'linkage_buffer_aggregation_method','fun_summary':'linkage_buffer_aggregation_method',
 'weights':'population_weighting_source','.by_time':'temporal_aggregation_method','daily_agg':'temporal_aggregation_method',
 'frac':'value_data_type','class_names':'value_column','colnames':'value_column','name_covariates':'value_column',
 'drop':'null_semantics_column','scale':'native_value_scale_factor','crs':'linkage_working_crs','locs':'target_geography_type',
 'locs_id':'subject_column','region':'spatial_extent_descriptor','data_region':'spatial_extent_descriptor',
 'jurisdiction':'spatial_extent_descriptor','type':'variable_name','resolution_temporal':'temporal_resolution',
 'temp_res':'temporal_resolution','url_aqs_download':'source_access_url','url_improve':'source_access_url',
 'statistic':'cf_cell_methods','output':'units_ucum','county':'native_spatial_resolution_descriptor',
 'hash':'input_file_sha256','mode':None,'product':None,'collection':None,'time_period':None,'source':'source_dataset_name',
 'timescale':None,'huc_level':None,'huc_header':None,'satellite':None,'sector_yearly':None,'sector_monthly':None,
 'sector_voc':None,'industry_group':None,'C0':None,'use_threshold':None,'path_secondary':None,'from_secondary':None,
 'fusion_method':None,'fun_agg':None,'cellsize':None,'threshold':None,'sites_file':None,'data_type':None,
}
# per-dataset overrides for args whose meaning differs by source
ARG_OVERRIDE = {
 ('nlcd','product'):'variable_name', ('improve','product'):'variable_name', ('cropscape','source'):'source_producer_institution',
 ('aqs','mode'):'missing_data_handling_method', ('huc','type'):'variable_name', ('tri','type'):'variable_name',
}

# Amadeus elements with NO EnVar home -> gap concept id
GAPS = collections.OrderedDict()
def gap(gid, title, proposal, rank, why, kind='slot'):
    GAPS[gid] = dict(id=gid, title=title, proposal=proposal, rank=rank, why=why, kind=kind, datasets=[] , evidence=[])
gap('vertical_level','Vertical level / layer of the variable (pressure level, soil layer, surface vs 2 m vs hybrid level)',
    'VariableIdentity.vertical_level (value + UCUM units, e.g. 850 hPa; 0–10 cm) and vertical_coordinate_type enum (surface, height_above_ground, pressure, soil_depth, model_level, column_integrated)',
    'High','The same variable name (air, shum, T) exists at 29 pressure levels / several soil layers; Amadeus encodes the level only in layer names. Without a slot a sidecar cannot say whether a value is surface or 500 hPa — a silent, large-magnitude error.')
gap('time_stamp_anchor','Where the time stamp sits inside its period (period start, mid, end; scan start)',
    'TemporalReference.time_stamp_position enum (period_start, period_midpoint, period_end, instant) + optional CF-style time_bounds',
    'High','Amadeus documents that monthly TerraClimate values are stamped on day 1, daily-aggregated MERRA-2/GEOS-CF/GOES at 00:00 UTC, GOES files at scan start. Lag and window joins against daily health events shift by up to a full period if this is unknown.')
gap('record_selection_rule','Source-record filtering / QA screening rule applied during processing',
    'Uncertainty.record_selection_rule (free text + optional enum: exceptional_events_included, exceptional_events_excluded, validity_flag_filtered, qa_mask_applied, none)',
    'High','process_aqs keeps "Included" rows where exceptional-event duplicates exist; process_improve does NOT filter by Status; MODIS QA layers are not applied unless the user does. Which rows survived changes the values, and EnVar can only name the flag column, not the rule.')
gap('regridding','Reprojection / regridding / swath-warping method and target grid',
    'SpatialReference.regridding_method enum (none, nearest, bilinear, warp_with_gap_fill, mosaic) + regridded_resolution_m + gap_fill_threshold',
    'High','process_modis_swath / process_modis_warp warp curvilinear swaths to a user cellsize with a gap-fill threshold; process_goes reprojects the geostationary grid to EPSG:4326. EnVar records the native resolution and the extraction step but not the resampling in between.')
gap('product_collection','Sub-product / collection / file-stream selector inside a dataset',
    'SourceDataset.source_product_code (e.g. MOD11A1, M2T1NXSLV, aqc_tavg_1hr_g1440x721_v1, ADP-C, IMPAER, normals_800)',
    'Medium','MODIS product, MERRA-2 & GEOS-CF collection, GOES scan sector, PRISM data_type, IMPROVE product and NLCD product each pick a different file family with different resolution/cadence. Today it can only be smuggled into source_dataset_name or variable_name.')
gap('accumulation_period','Accumulation / look-back timescale that defines an index',
    'TemporalReference.accumulation_period (ISO-8601 duration, e.g. P30D, P3M, P1Y)',
    'Medium','SPEI/EDDI timescales (1–48 months; 14d–5y in gridMET) are part of the variable definition. temporal_aggregation_window_seconds is the native grain, not a multi-month accumulation.')
gap('emission_sector','Emission / release sector, industry group and release medium',
    'VariableIdentity.emission_sector (+ sector_vocabulary, e.g. IPCC 1996, EDGAR, NAICS) and release_medium enum (stack_air, fugitive_air, water, land, offsite)',
    'Medium','EDGAR sector_yearly/monthly/voc, TRI industry_group and release variables, NEI on-road sector. Sector totals vs sector subsets differ by orders of magnitude and cannot be told apart in the schema.')
gap('platform_sensor','Satellite platform / sensor and multi-platform fusion',
    'SourceDataset.platform (Terra, Aqua, Suomi-NPP, GOES-16, GOES-18) + ExposureModel.fusion_method enum (mean, primary_first, secondary_first)',
    'Medium','MODIS Terra/Aqua fusion (path_secondary, fusion_method) and GOES-16 vs GOES-18 change coverage and overpass time; EnVar only has free-text exposure_model_inputs.')
gap('scenario_period','Climate scenario / projection period',
    'TemporalReference.climate_scenario (e.g. historical, SSP2-4.5, RCP8.5) + period label',
    'Medium','Köppen-Geiger time_period "Future (2071-2100)" is a projection, not an observation; EnVar has no way to flag projected vs observed values.')
gap('spatial_unit_level','Hierarchical level of a reference spatial unit',
    'SpatialReference.spatial_unit_level (HUC2…HUC12; ecoregion L1/L2/L3)',
    'Medium','calculate_huc returns IDs at a chosen huc_level; calculate_ecoregion returns L2 and L3 classes. TargetGeographyTypeEnum covers census units only.')
gap('sampling_schedule','Measurement sampling schedule / duty cycle',
    'TemporalReference.sampling_schedule (e.g. every_day, every_3rd_day, every_6th_day) or ISO-8601 recurrence',
    'Medium','IMPROVE samples every third day (gaps are by design, not missing data); AQS monitors run 1-in-1/3/6 schedules. Without it, completeness and null semantics are misread.')
gap('overlap_rule','Rule for resolving overlapping source features / tiles',
    'SpatialReference.overlap_resolution_rule enum (max_class, first, mean, sum)',
    'Low','process_hms keeps the highest smoke-density class where polygons overlap; process_modis_* use fun_agg to mosaic overlapping tiles.')
gap('distance_decay','Distance-decay weighting parameters for point-source aggregation',
    'ExtractionMethodEnum value exponential_distance_decay_sum + LinkageMethod.decay_range_m and decay_threshold_multiplier',
    'Medium','calculate_tri uses sum_edc (exponential decay, decay_range, 5×range threshold, C0 source column). None of EnVar\'s extraction methods describe this, so TRI covariates would be mislabelled as buffer sums.')
gap('access_requirement','Access/authentication requirement of the source',
    'SourceDataset.access_requirement enum (open, registration_token, restricted)',
    'Low','NASA Earthdata token needed for MODIS, MERRA-2, GEOS-CF, gROADS, population. Affects reproducibility logistics, not values.')
gap('station_metadata','Station / site metadata table used to locate measurements',
    'SourceDataset.site_metadata_source (URI + version)',
    'Low','process_improve joins an embedded IMPROVE site table (or a user sites_file) to give coordinates; process_aqs uses site columns. The coordinates used are a provenance fact.')
gap('climate_normal','Climatological-normal products as a temporal resolution',
    'TemporalResolutionEnum value climatological_normal (+ reference period in temporal_coverage_start/end)',
    'Medium','PRISM normals (data_type normals/normals_800) and Köppen present-day climatology are period statistics, not a time series; no TemporalResolutionEnum value fits.', kind='enum')
gap('cell_count_mode','Cell-count vs exact-area class fractions',
    'ExtractionMethodEnum value cell_count_proportion (alongside intersection_area_proportion)',
    'Low','calculate_nlcd mode "terra" counts intersecting cells, "exact" weights partial coverage; results differ, and EnVar has one value for both.', kind='enum')

ARG_GAP = {'timescale':'accumulation_period','huc_level':'spatial_unit_level','huc_header':'spatial_unit_level',
           'satellite':'platform_sensor','sector_yearly':'emission_sector','sector_monthly':'emission_sector',
           'sector_voc':'emission_sector','industry_group':'emission_sector','C0':'distance_decay','use_threshold':'distance_decay',
           'path_secondary':'platform_sensor','from_secondary':'platform_sensor','fusion_method':'platform_sensor',
           'fun_agg':'overlap_rule','cellsize':'regridding','threshold':'regridding','sites_file':'station_metadata',
           'collection':'product_collection','product':'product_collection','time_period':'scenario_period',
           'data_type':'product_collection','mode':'cell_count_mode'}
ARG_GAP_OVERRIDE = {('aqs','mode'):None}  # aqs mode is absorbed (mapped)

# documented (non-argument) facts with no EnVar home, per dataset
DOC_GAPS = {
 'narr':['vertical_level'], 'merra2':['vertical_level','time_stamp_anchor','access_requirement'],
 'geos':['vertical_level','time_stamp_anchor','access_requirement'], 'goes':['time_stamp_anchor','regridding'],
 'terraclimate':['time_stamp_anchor'], 'modis':['regridding','record_selection_rule','access_requirement'],
 'aqs':['record_selection_rule','sampling_schedule','station_metadata'], 'improve':['record_selection_rule','sampling_schedule'],
 'hms':['overlap_rule'], 'prism':['climate_normal'], 'koppen_geiger':['climate_normal'],
 'groads':['access_requirement'], 'population':['access_requirement'], 'gridmet':['accumulation_period'],
 'nei':['emission_sector'], 'tri':['emission_sector'], 'ecoregion':['spatial_unit_level'],
}
GAP_EVIDENCE = {
 'vertical_level':{'narr':'process_narr: layer names carry pressure level; 29 levels 1000–100 hPa + 4 soil layers','merra2':'process_merra2: layer names contain variable, pressure level, date, hour','geos':'process_geos: p23 collections on 23 pressure levels; layer names carry level'},
 'time_stamp_anchor':{'terraclimate':'process_terraclimate: first day of month used as placeholder','merra2':'daily_agg=TRUE: terra::time() set to midnight UTC','geos':'daily_agg=TRUE: terra::time() set to midnight UTC','goes':'goes_parse_start_datetime: scan START time; daily_agg midnight UTC'},
 'record_selection_rule':{'aqs':'process_aqs keeps "Included" where multiple event types per site-time','improve':'process_improve: values not filtered by Status (V0 = valid)','modis':'QA subdatasets not applied automatically; scale left to the user'},
}

# ---------------------------------------------------------------- enum fit checks
ENUM_GAPS = collections.OrderedDict()
def eg(enum, value, datasets, rank, why): ENUM_GAPS[(enum, value)] = dict(enum=enum, value=value, datasets=datasets, rank=rank, why=why)
eg('SourceNativeFormatEnum','hdf4_eos',['modis'],'High','MODIS L2/L3 HDF4-EOS; hdf5 is a different container')
eg('SourceNativeFormatEnum','esri_shapefile',['groads','huc','hms','drought','ecoregion'],'High','Five vector sources; no vector format exists in the enum at all')
eg('SourceNativeFormatEnum','file_geodatabase',['groads','huc'],'Medium','NHDPlus / gROADS ship as Esri FGDB')
eg('SourceNativeFormatEnum','kml',['hms'],'Low','HMS alternative format')
eg('SourceNativeFormatEnum','esri_ascii_grid',['gmted','population','drought','prism'],'Medium','GMTED, GPW ASCII, EDDI .asc, PRISM ASCII')
eg('SourceNativeFormatEnum','bil',['prism'],'Low','PRISM normals .bil')
eg('SourceNativeFormatEnum','delimited_text (csv_tabular / pipe-delimited)',['improve','tri','nei','edgar'],'Medium','csv_station_observations does not fit facility/county inventory tables or pipe-delimited IMPROVE')
eg('TemporalResolutionEnum','sub_hourly (with cadence)',['goes'],'Medium','GOES ADP ~5-min scans; instantaneous loses the cadence')
eg('TemporalResolutionEnum','pentad (5-day)',['gridmet'],'Medium','gridMET SPEI/EDDI native five-day observation dates')
eg('TemporalResolutionEnum','weekly',['drought'],'High','EDDI and USDM weekly (Tuesday) releases')
eg('TemporalResolutionEnum','eight_day / sixteen_day composite',['modis'],'High','MOD13 16-day phased composites; MCD/MOD 8-day products')
eg('TemporalResolutionEnum','multi_year_epoch (e.g. 5-year)',['population'],'Medium','GPWv4 2000/2005/2010/2015/2020')
eg('TemporalResolutionEnum','static / time_invariant',['groads','huc','ecoregion','gmted','koppen_geiger'],'High','Five sources have no time axis; forcing "annual" is wrong')
eg('ExposureModelTypeEnum','emission_inventory',['edgar','nei','tri'],'High','Three emission/release inventories have no matching model type')
eg('ExposureModelTypeEnum','land_cover_classification',['nlcd','cropscape'],'Medium','Classified imagery differs from a geophysical satellite_retrieval')
eg('ExposureModelTypeEnum','analyst_digitized / expert_assessment',['hms','drought'],'Medium','HMS smoke analysts; USDM expert consensus')
eg('ExposureModelTypeEnum','reference_delineation / classification',['huc','ecoregion','koppen_geiger'],'Low','Boundary/zone products')
eg('ExposureModelTypeEnum','dasymetric_population_model',['population'],'Low','UN WPP-adjusted GPW')
eg('ExposureModelTypeEnum','digital_elevation_model / vector_compilation',['gmted','groads'],'Low','Terrain and road-network compilations')
eg('ExtractionMethodEnum','point_in_polygon_membership',['koppen_geiger','ecoregion','huc','hms','nei','drought'],'High','Binary/ID membership extraction (frac=FALSE, calculate_huc, NEI county join) has no value; area_membership exists only in LinkageStrategyEnum')
eg('ExtractionMethodEnum','buffer_coverage_weighted_mean (exactextractr)',['terraclimate','gridmet','merra2','geos','narr','prism','modis','population','edgar','goes','gmted','drought'],'Medium','area_weighted_polygon_mean is close but is defined for polygon targets, not circular buffers around points')
eg('BufferAggregationEnum','sum, min, sd, user_function',['groads','modis','merra2','geos','goes','narr','gridmet','terraclimate','population','gmted','drought'],'Medium','Amadeus fun/fun_summary accepts any summary (groads defaults to sum)')
eg('DataTypeEnum','proportion / fraction',['nlcd','cropscape','koppen_geiger','ecoregion','hms','drought'],'Medium','frac=TRUE outputs and NLCD/CDL class ratios are bounded [0,1]')
eg('DataTypeEnum','ordinal',['hms','drought'],'Low','HMS Light/Medium/Heavy; USDM D0–D4 are ordered classes')
eg('TargetGeographyTypeEnum','point_site (generic) / arbitrary_polygon',['ALL_CALC'],'Medium','Amadeus locs are any sites (monitors, grid centroids, polygons); EnVar assumes residence/census units')

# ---------------------------------------------------------------- EnVar -> Amadeus priority
ENV2AMA_RANK = {
 'units_ucum':('High','Amadeus outputs carry no units; e.g. MERRA-2 K vs gridMET K vs PRISM °C, TRI lb/yr, EDGAR kg m-2 s-1 vs t/yr'),
 'standard_name':('Medium','CF standard name disambiguates tmmx/T2M/air.2m across five met sources'),
 'source_dataset_version':('High','Only MODIS, EDGAR, GMTED, NHDPlus versions are pinned; gridMET/NARR/PRISM "current" values get revised'),
 'day_boundary_convention':('High','Undocumented for gridMET, NARR, PRISM, MODIS, HMS, AQS, IMPROVE daily values'),
 'crs':('High','Native CRS is carried by the terra object but never written to output'),
 'native_spatial_resolution_m':('Medium','Not stated for TerraClimate, MERRA-2, NARR, GOES, EDGAR, CDL'),
 'extraction_method':('High','Implicit in radius/frac/mode; should be emitted with every calculate_* output'),
 'exposure_model_type':('High','Core EnVar slot; trivially fixed per dataset'),
 'temporal_resolution':('High','Documented in prose only'),
 'missing_value_sentinel':('High','Decoding is silent inside terra; fill values never surfaced'),
 'native_value_scale_factor':('High','Packed netCDF/HDF decoding is silent; MODIS needs user scale'),
 'native_value_offset':('High','see scale factor'),
 'unit_conversion_formula':('High','see scale factor'),
 'calendar':('Medium','netCDF calendars (noleap in some reanalyses) not surfaced'),
 'source_dataset_doi':('Medium','DOIs exist in REFERENCES.bib for some sources but never reach outputs'),
 'source_license_spdx':('Medium','No source has a license recorded'),
 'source_citation_apa':('Medium','Citations live in help pages only'),
 'source_citation_bibtex':('Low','Same as APA'),
 'quality_flag_column':('High','MODIS/GOES QA, AQS event type, IMPROVE Status not propagated'),
 'quality_flag_vocabulary':('High','see quality_flag_column'),
 'tool_version':('High','package version not written into outputs'),
 'run_arguments':('High','function call not serialised with outputs'),
 'run_timestamp_utc':('Medium','needed to pin "current" source versions'),
 'run_environment':('Low','R + terra versions'),
 'output_file_sha256':('Medium','no output hashing'),
 'input_file_sha256':('Medium','hash=TRUE gives rlang (xxhash128) of downloads, not SHA-256'),
 'input_row_count':('Low',''), 'output_row_count':('Low',''),
 'container_image_repository':('Low','deployment concern'), 'container_image_digest':('Low',''),
 'run_duration_seconds':('Low',''), 'run_log_excerpt':('Low',''),
 'spatial_aggregation_preserves':('Medium','density vs mean vs fraction outputs (groads, NLCD) need it'),
 'exposure_model_inputs':('Low',''), 'exposure_model_paper_doi':('Low',''),
 'exposure_model_cross_validation_r2':('Low','not provided by most producers'),
 'exposure_model_known_biases':('Low',''), 'bias_correction_applied':('Low',''),
 'per_value_uncertainty_type':('Medium','NLCD confidence, MERRA-2/GEOS ensemble spread not offered'),
 'per_value_uncertainty_units_ucum':('Low',''), 'model_aggregate_uncertainty':('Low',''),
 'data_completeness_pct':('Medium','MODIS dates_dropped exists as an attribute only'),
 'missing_data_handling_method':('Medium',''), 'value_uncertainty_column':('Low',''),
 'null_semantics_column':('Medium','HMS no-plume vs missing, groads zero-road drop'),
 'variable_label':('Low',''), 'cf_cell_methods':('Medium','daily max vs mean of hourly'),
 'value_data_type':('Medium',''), 'value_range_plausible_min':('Low',''), 'value_range_plausible_max':('Low',''),
 'native_units_ucum':('High','paired with scale/offset'), 'units_display':('Low',''), 'concept_mappings':('Low',''),
 'source_homogenisation_status':('Medium','conditionally core for station data (AQS, IMPROVE)'),
 'source_acdd_attributes':('Low','netCDF global attrs passthrough'),
 'temporal_coverage_start':('Low',''), 'temporal_coverage_end':('Low',''), 'source_dataset_temporal_coverage':('Low',''),
 'source_producer_institution':('Low',''), 'source_access_url':('Low',''), 'source_native_format':('Low',''),
 'native_spatial_resolution_descriptor':('Low',''), 'temporal_aggregation_method':('Medium',''),
 'temporal_aggregation_window_seconds':('Low',''), 'provenance_chain_steps':('Medium','download→process→calculate is a 3-step chain never recorded'),
 'chain_compatibility_assertions':('Low',''), 'provenance_chain_terminus_type':('Low',''),
 'linkage_working_crs':('Medium','extraction runs in source CRS; not recorded'),
 'lag_alignment_applied':('Low',''), 'lag_alignment_specifier':('Low',''), 'population_weighting_source':('Medium','weights= raster identity not recorded'),
 'target_geography_type':('Low',''), 'tool_name':('Low',''), 'tool_description':('Low',''),
 'spatial_extent_bbox':('Low',''), 'table_orientation':('Low',''), 'value_column':('Low',''), 'subject_column':('Low',''),
 'time_column':('Low',''), 'extraction_window_start':('Low',''), 'extraction_window_end':('Low',''),
 'heat_metric_family':('Low','only if Amadeus wants to self-describe tmax/tmin outputs'),
}

# ---------------------------------------------------------------- compute
rows = []   # per dataset x slot
for k, d in D.items():
    for c, s, t in SLOTS:
        rows.append(dict(dataset=k, cls=c, slot=s, tier=t, status=status(d, c, s), in_scope=s not in OUT_OF_AMADEUS_SCOPE))

ama_rows = []  # per dataset x amadeus element
for k, d in D.items():
    for a in sorted(d['args']):
        if a in OPERATIONAL:
            ama_rows.append(dict(dataset=k, element=f'arg:{a}', kind='argument', maps_to='', gap='', status='operational')); continue
        tgt = ARG_OVERRIDE.get((k, a), ARG_MAP.get(a, 'UNMAPPED'))
        if tgt == 'UNMAPPED': raise KeyError((k, a))
        if tgt:
            ama_rows.append(dict(dataset=k, element=f'arg:{a}', kind='argument', maps_to=tgt, gap='', status='shared'))
        else:
            g = ARG_GAP_OVERRIDE.get((k, a), ARG_GAP.get(a))
            if (k, a) == ('nlcd','mode'): g = 'cell_count_mode'
            ama_rows.append(dict(dataset=k, element=f'arg:{a}', kind='argument', maps_to='', gap=g, status='amadeus_only'))
    for g in DOC_GAPS.get(k, []):
        ama_rows.append(dict(dataset=k, element=f'doc:{g}', kind='documented fact', maps_to='', gap=g, status='amadeus_only'))
    # documented facts that DO land in EnVar (counted as shared elements)
    for fact, slot in [('file type','source_native_format'),('spatial extent','spatial_extent_descriptor'),
                       ('temporal resolution','temporal_resolution'),('producer','source_producer_institution'),
                       ('output columns','value_column')]:
        ama_rows.append(dict(dataset=k, element=f'doc:{fact}', kind='documented fact', maps_to=slot, gap='', status='shared'))
    if d['cite']: ama_rows.append(dict(dataset=k, element='doc:reference', kind='documented fact', maps_to='source_citation_apa', gap='', status='shared'))
    if d['has_url']: ama_rows.append(dict(dataset=k, element='doc:source URL', kind='documented fact', maps_to='source_access_url', gap='', status='shared'))

for r in ama_rows:
    if r['gap']:
        GAPS[r['gap']]['datasets'].append(r['dataset']) if r['dataset'] not in GAPS[r['gap']]['datasets'] else None
        GAPS[r['gap']]['evidence'].append(f"{r['dataset']}:{r['element']}")

# per dataset venn
venn = collections.OrderedDict()
for k in D:
    R = [r for r in rows if r['dataset'] == k]
    A = [r for r in ama_rows if r['dataset'] == k]
    shared_slots_full = sorted({r['slot'] for r in R if r['status'] == 'full'})
    shared_slots_part = sorted({r['slot'] for r in R if r['status'] == 'partial'})
    envar_only = [r for r in R if r['status'] == 'envar']
    venn[k] = dict(
        both_full=len(shared_slots_full), both_partial=len(shared_slots_part),
        envar_only=len(envar_only), envar_only_in_scope=sum(r['in_scope'] for r in envar_only),
        envar_only_core=sum(r['tier'] in ('core','conditionally_core') and r['in_scope'] for r in envar_only),
        na=sum(r['status'] == 'na' for r in R),
        amadeus_only=len({r['gap'] for r in A if r['status'] == 'amadeus_only'}),
        enum_gap_n=sum(1 for e in ENUM_GAPS.values() if k in e['datasets'] or (e['datasets']==['ALL_CALC'] and d['calc'])),
        amadeus_only_elements=sum(r['status'] == 'amadeus_only' for r in A),
        amadeus_shared_elements=sum(r['status'] == 'shared' for r in A),
        operational=sum(r['status'] == 'operational' for r in A),
        applicable=sum(r['status'] != 'na' for r in R),
        core_applicable=sum(r['status'] != 'na' and r['tier'] in ('core','conditionally_core') for r in R),
        core_covered=sum(r['status'] in ('full','partial') and r['tier'] in ('core','conditionally_core') for r in R),
        core_full=sum(r['status'] == 'full' and r['tier'] in ('core','conditionally_core') for r in R),
        amadeus_gaps=sorted({r['gap'] for r in A if r['status'] == 'amadeus_only'}),
        enum_gaps=[f"{e['enum']}:{e['value']}" for e in ENUM_GAPS.values() if k in e['datasets'] or e['datasets']==['ALL_CALC'] and d['calc']],
    )

# overall (union across datasets)
slot_status_any = collections.defaultdict(set)
for r in rows: slot_status_any[r['slot']].add(r['status'])
def agg(s):
    st = slot_status_any[s]
    if 'full' in st: return 'full'
    if 'partial' in st: return 'partial'
    if 'envar' in st: return 'envar'
    return 'na'
overall = collections.Counter(agg(s) for _, s, _ in SLOTS)
overall_scope = collections.Counter(agg(s) for _, s, _ in SLOTS if s not in OUT_OF_AMADEUS_SCOPE)
# slots full for ALL applicable datasets
slot_ds = {}
for _, s, t in SLOTS:
    R = [r for r in rows if r['slot'] == s]
    slot_ds[s] = dict(tier=t, full=sum(r['status']=='full' for r in R), partial=sum(r['status']=='partial' for r in R),
                      envar=sum(r['status']=='envar' for r in R), na=sum(r['status']=='na' for r in R), in_scope=s not in OUT_OF_AMADEUS_SCOPE,
                      rank=ENV2AMA_RANK.get(s, ('Low',''))[0] if s not in OUT_OF_AMADEUS_SCOPE else 'Out of scope',
                      why=ENV2AMA_RANK.get(s, ('',''))[1])

# expand ALL_CALC
for v in ENUM_GAPS.values():
    if v['datasets'] == ['ALL_CALC']: v['datasets'] = [k for k, d in D.items() if d['calc']]

# dataset-level venn: which sources each side knows
envar_sources = {'daymet_v4':'Daymet V4','era5':'ERA5 single levels','acag_pm25_v5gl':'ACAG PM2.5 V5.GL','di_pm25_ensemble':'Di et al. PM2.5 ensemble','envar_heat_index':'EnVar-derived heat index','gridmet':'gridMET','epa_aqs':'EPA AQS'}
ds_venn = dict(both=['gridmet (EnVar: amadeus_gridmet_tmmx scenario)','aqs (EnVar: PM2.5 gradient epa_aqs)'],
               amadeus_only=[k for k in D if k not in ('gridmet','aqs')],
               envar_only=['Daymet V4','ERA5','ACAG PM2.5 V5.GL','Di et al. PM2.5 ensemble','EnVar-derived heat index'])

out = dict(n_slots=len(SLOTS), n_in_scope=sum(s not in OUT_OF_AMADEUS_SCOPE for _, s, _ in SLOTS),
           tiers=collections.Counter(t for _, _, t in SLOTS), overall=overall, overall_scope=overall_scope,
           venn=venn, gaps=list(GAPS.values()), enum_gaps=list(ENUM_GAPS.values()), slot_ds=slot_ds,
           ds_venn=ds_venn, datasets={k: {kk: (sorted(vv) if isinstance(vv, set) else vv) for kk, vv in d.items()} for k, d in D.items()})
json.dump(out, open(f'{W}/results.json', 'w'), indent=1, default=list)
with open(f'{W}/dataset_x_envar_slot.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
with open(f'{W}/dataset_x_amadeus_element.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(ama_rows[0])); w.writeheader(); w.writerows(ama_rows)

if __name__ == '__main__':
    print('EnVar leaf slots:', out['n_slots'], 'in Amadeus scope:', out['n_in_scope'], dict(out['tiers']))
    print('overall:', dict(overall), 'in-scope:', dict(overall_scope))
    print(f"{'dataset':14s} full part envO envO_scope envO_core na | amaO_concepts amaO_el shared_el oper | core cov/app")
    for k, v in venn.items():
        print(f"{k:14s} {v['both_full']:4d} {v['both_partial']:4d} {v['envar_only']:4d} {v['envar_only_in_scope']:9d} {v['envar_only_core']:9d} {v['na']:3d} | {v['amadeus_only']:9d}+{v['enum_gap_n']:<3d} {v['amadeus_only_elements']:7d} {v['amadeus_shared_elements']:9d} {v['operational']:4d} | {v['core_covered']}/{v['core_applicable']}")
    for g in GAPS.values(): print(g['rank'], g['id'], g['datasets'])
