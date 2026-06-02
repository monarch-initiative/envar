# High-Priority Environmental Variables

Deliverable 3.2.

!!! warning "Preliminary"
    This survey is a working document. Variable specifications, OMOP status assessments, and tier assignments have not been fully vetted by all stakeholders and may be revised as the project progresses.

---

## Executive Summary

This survey specifies **38 environmental variables** across five NIEHS priority use case domains, each with spatial/temporal resolution requirements, best-available data sources, OMOP vocabulary status, and recommended exposure assignment methods.

Variables were ranked using a five-criterion framework: epidemiological evidence strength (P-ExWAS replication, GBD burden), NIEHS/HEW alignment, data availability, OMOP readiness, and community demand across 50+ surveyed projects. The result: **14 Tier 1** (immediate standardization), **14 Tier 2** (next phase), **10 Tier 3** (future development).

**The most critical finding: 30 of 38 variables lack OMOP concept IDs.** Only 8 have existing or near-ready concepts. The vocabulary gap -- not data availability or schema design -- is the primary blocker.

---

## NIEHS Priority Use Cases

### Wildfire Smoke Exposure

Acute and sub-chronic exposure to wildfire-generated air pollutants. Top HEW priority; NIEHS funds 40+ research groups. Key challenge: separating smoke-attributable PM2.5 from ambient PM2.5 and characterizing smoke composition.

### Heat Stress / Extreme Heat

Multiple thermal metrics beyond simple temperature. Research favors composite indices (WBGT, UTCI) over simple temperature because they better predict physiological stress. No single heat metric is optimal for all populations.

### Chronic Air Quality

The most mature domain. Multiple validated exposure surfaces, strong causal evidence (GBD: ~4.2M deaths/year from ambient PM2.5). Key challenge: multi-pollutant mixtures and unstandardized metadata for mixture analyses.

### Water Contaminants

PFAS, arsenic, nitrate, lead, disinfection byproducts. NIEHS designated PFAS as top priority; EPA announced first enforceable PFAS limits in April 2024. Key challenge: SDWIS reports violations (binary), not concentrations; service-area boundaries were historically a major gap, partially closed by EPA's October 2024 national CWS service-area boundaries release covering ~99% of CWS-served population, but residual gaps remain for small systems; private wells (~15% of households) are unmonitored.

### Socio-Economic / Environmental Justice

Area-level indices (SVI, ADI, EJScreen, CalEnviroScreen) used as exposures and effect modifiers. Key challenge: composite indices mask individual effects; no standardization across indices.

---

## Priority Variable Summary

| Variable | Use Case | Min Spatial | Min Temporal | Best Source | OMOP Status | Tier |
|----------|----------|-------------|-------------|-------------|-------------|------|
| PM2.5 (annual) | Air quality | 1 km | Annual | ACAG/van Donkelaar | Proposed | **1** |
| PM2.5 (daily) | Air quality | 1 km | Daily | Di et al. ensemble | Proposed | **1** |
| NO2 | Air quality | Block group | Annual | CACES | Missing | **1** |
| O3 (seasonal) | Air quality | Block group | Seasonal | CACES | Proposed | **1** |
| Smoke-specific PM2.5 | Wildfire | 10 km | Daily | HMS + PM2.5 surfaces | Missing | **1** |
| HMS smoke plume density | Wildfire | Polygon | Daily | NOAA HMS (polygons from 2005) | Missing | **1** |
| Daily Tmax | Heat | 4 km | Daily | PRISM / Daymet | Proposed (partial) | **1** |
| WBGT | Heat | 4 km | Daily | gridMET-derived | Missing | **1** |
| UTCI | Heat | 31 km | Hourly | ERA5-HEAT | Missing | **1** |
| Heat Index | Heat | 12 km | Daily | NLDAS-2 / CDC WONDER (NLDAS heat-index covers 1979–2011) | Proposed (partial) | **1** |
| PFOA | Water | Water system | Quarterly | SDWIS / UCMR 5 | Missing | **1** |
| PFOS | Water | Water system | Quarterly | SDWIS / UCMR 5 | Missing | **1** |
| SVI | EJ/SES | Census tract | Biennial | CDC/ATSDR | Exists | **1** |
| ADI | EJ/SES | Block group | Annual | UW Neighborhood Atlas | Exists | **1** |
| SO2 | Air quality | Block group | Annual | CACES | Missing | **2** |
| Black carbon | Air quality | Block group | Annual | CACES | Missing | **2** |
| PM10 | Air quality | Block group | Annual | CACES | Missing | **2** |
| Smoke wave duration | Wildfire | 10 km | Event | Derived from HMS + PM2.5 surfaces | Missing | **2** |
| AOD | Wildfire | 1 km | Daily | MODIS MAIAC | Missing | **2** |
| Smoke plume extent | Wildfire | Polygon | Daily | NOAA HMS (polygons from 2005) | Missing | **2** |
| Apparent temperature | Heat | 31 km | Hourly | ERA5 | Missing | **2** |
| Consecutive heat days | Heat | County/Tract | Event | Derived from PRISM | Missing | **2** |
| Nighttime Tmin | Heat | 4 km | Daily | PRISM / Daymet | Missing | **2** |
| PFAS mixture (HI) | Water | Water system | Quarterly | SDWIS | Missing | **2** |
| Nitrate | Water | Water system | Event-based | USGS NWIS / SDWIS | Missing | **2** |
| Arsenic | Water | Water system | Event-based | USGS NWIS / SDWIS | Proposed (partial) | **2** |
| EJScreen indices | EJ/SES | Block group | Annual | EPA (archived) | Proposed | **2** |
| EJI | EJ/SES | Census tract | Periodic | CDC/ATSDR | Proposed | **2** |
| CO | Air quality | Block group | Annual | CACES | Missing | **3** |
| Fire Radiative Power | Wildfire | 375 m | Overpass | NASA FIRMS | Missing | **3** |
| Wildfire PM2.5 composition | Wildfire | 12 km | Daily | CMAQ w/ fire emissions | Missing | **3** |
| UHI effect | Heat | 70 m | Variable | ECOSTRESS / MODIS LST | Missing | **3** |
| Lead (water + blood) | Water | Water system | Event-based | SDWIS / CDC / NHANES | Proposed (partial) | **3** |
| Disinfection byproducts | Water | Water system | Quarterly | SDWIS | Missing | **3** |
| Pesticides in water | Water | County | Annual | USGS PNSP / WQP | Missing | **3** |
| CalEnviroScreen | EJ/SES | Census tract | Periodic | CA OEHHA | Missing | **3** |
| Residential segregation | EJ/SES | Census tract | Decennial | Census | Missing | **3** |
| Food access | EJ/SES | Census tract | Periodic | USDA Food Access Atlas | Missing | **3** |

---

## Gap Analysis

### Variables With No Adequate Data

| Variable | Gap | Impact |
|----------|-----|--------|
| Indoor wildfire PM2.5 | No national indoor product; 40--65% of smoke exposure occurs indoors | High |
| PFAS in private wells | ~15% of US households unmonitored | High |
| UHI effect | No standardized national product | Medium |
| Wildfire PM2.5 composition | Requires CTM simulation; no pre-computed product | Medium |

### OMOP Vocabulary Gap

Of 38 variables, **30 lack OMOP concept IDs**. The 8 with existing or near-ready concepts: SVI, ADI, poverty rate (SDoH vocabulary); PM2.5, O3 (proposed in exposome vocabulary); arsenic, lead, heat index (partial via SNOMED/LOINC clinical measurement codes -- not environmental exposure concepts).

Most critical Tier 1 gaps requiring new OMOP concept proposals:

- Smoke-specific PM2.5 (no concept distinguishing from ambient)
- HMS smoke plume density
- WBGT, UTCI (no heat stress index concepts)
- NO2 (no ambient environmental concept)
- PFOA, PFOS in drinking water

### Unstandardized Exposure Assignment

| Variable | Issue | Impact |
|----------|-------|--------|
| Water contaminants | Service-area boundaries partially closed by EPA Oct 2024 release; residual gaps for small systems | High |
| Smoke PM2.5 | 3+ competing methods with >50% estimate differences | High |
| Heat metrics | 4+ competing indices, no consensus | Medium |
| NDVI / greenspace | Buffer distance arbitrary; changes quintiles for 11--60% of participants | Medium |

### Poor Metadata Reporting

Across all domains, the most common omissions: CRS, exact dataset version, temporal alignment (day definition convention), geocoding method/accuracy, model uncertainty propagation.

---

## Tiered Recommendations

### Tier 1: Immediate Standardization (14 variables)

Strong evidence, mature data, highest priority for OMOP vocabulary proposals and micro-schema development. Estimated timeline: OMOP concept proposals within 6 months; micro-schemas within 3 months.

### Tier 2: Next Phase (14 variables)

Strong evidence but vocabulary gaps, resolution limitations, or unstandardized methods. Contingent on Tier 1 completion; estimated 12 months.

### Tier 3: Future Development (10 variables)

Niche, emerging, or facing fundamental data challenges. Revisit in 18--24 months.
