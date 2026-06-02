# Dataset Generator Documentation Requirements

Deliverable 7.1.

!!! warning "Preliminary"
    This survey documents research findings from deep-research synthesis. The metadata gap analysis and recommended templates have not yet been validated with the data producer organizations (NASA, NOAA, EPA) described here. Stakeholder interviews are pending.

---

## Executive Summary

Environmental dataset producers -- NASA satellite teams, NOAA climate centers, EPA monitoring programs, and academic exposure modelers -- create data with rich scientific metadata but lack the structured documentation needed for OMOP CDM integration.

**The documentation gap in brief:**

| What producers provide | What OMOP needs | Gap |
|----------------------|-----------------|-----|
| CF standard_name (e.g., `mass_concentration_of_pm2p5_...`) | OMOP concept_id (integer FK) | No crosswalk exists |
| Native units (kg m-3) | unit_concept_id (UCUM: ug/m3) | Unit conversion + concept mapping needed |
| Spatial extent as bounding box | location_id FK via location_history | Spatial join semantics undocumented |
| Temporal coverage as ISO date range | exposure_start/end_date aligned to residence period | Temporal overlap logic undefined |
| Dataset-level DOI | Per-record provenance (data_source, model_version) | No field in external_exposure |

The core problem is not poor documentation -- NASA and NOAA have among the most rigorous metadata systems in science. The problem is that these systems were designed for Earth science, not clinical data integration.

---

## Producer Profiles

### NASA (SEDAC, LAADS DAAC, LP DAAC, GES DISC)

**Produces:** Gridded satellite-derived products -- AOD (1 km), NDVI/EVI (250 m), nighttime lights (500 m), PM2.5 surfaces.

**Metadata system:** The most comprehensive in environmental science. The **Unified Metadata Model (UMM)** defines profiles for collections (UMM-C), granules (UMM-G), services (UMM-S), and variables (UMM-Var), all searchable via the **Common Metadata Repository (CMR)**. UMM-C captures 100+ fields per collection [VERIFY CLAIM].

**Not documented for OMOP:** No concept_id mapping; no spatial assignment guidance (how gridded values become person-level exposure); no temporal alignment semantics; no UCUM unit mapping.

### NOAA (NCEI, NWS/CPC, NLDAS, GHCN)

**Produces:** Climate/weather observations and reanalysis -- GHCN (100K+ stations), NLDAS-2 (hourly, 12 km), ERA5, HMS smoke polygons (manually-drawn smoke polygon product from 2005-present; underlying HMS system active since 2002).

**Metadata system:** ISO 19115/19115-2 mandatory for NCEI-archived data. CF Conventions required for NetCDF (4,500+ standard names with canonical units). CF `cell_methods` partially addresses temporal aggregation.

**Not documented for OMOP:** No concept crosswalk; no population-weighted spatial aggregation guidance; no temporal alignment for health events; NLDAS-2 coastal bias (-1.48C for Tmax [VERIFY CLAIM]) and heat index validity threshold (>80F only) not flagged for health consumers.

### EPA (AQS, CMAQ, AirToxScreen, TRI, WQP)

**Produces:** Monitor data (~5,000 active AQS monitors; >10,000 total in the database), air quality models (CMAQ at 12/4/1 km), risk assessments (AirToxScreen at census tract for 2017–2019; census block for 2020+), water quality (WQP: 430M+ results).

**Metadata system:** AQS uses the Environmental Sampling and Results (ESAR) standard. CMAQ output uses I/O API NetCDF. Parameter codes are EPA-specific (e.g., 88101 = PM2.5 Local Conditions, NAAQS-eligible FRM/FEM data).

**Not documented for OMOP:** No concept_id mapping; no guidance on linking CMAQ grids to patient locations; no unit mapping to UCUM; AirToxScreen conflates exposure and risk with no guidance on OMOP usage; WQP has extreme method/unit heterogeneity.

### Academic Modeled Surfaces (Di/van Donkelaar, CACES, MESA Air)

**Produces:** High-resolution modeled exposure surfaces combining satellite, monitors, CTMs, and ML.

**Metadata system:** Primary documentation is the methods paper. README files unstandardized. No machine-readable metadata schema. NetCDF files have partial CF compliance.

**Not documented for OMOP:** No concept mappings; no spatial assignment guidance; sub-grid uncertainty rarely quantified; version differences (V5 vs V6) not flagged for downstream users.

---

## Metadata Gap Analysis

Three categories of **critical** gaps block OMOP integration:

### 1. Variable-to-Concept Mapping

No crosswalk from CF standard_names, EPA parameter codes, or academic variable names to OMOP concept_ids. This is the single most important gap.

!!! info "Health-Relevant CF Standard Names"
    Only ~15--20 of 4,500+ CF standard names are directly relevant to health research: criteria air pollutants (PM2.5, PM10, O3, NO2, SO2, CO), meteorological variables (temperature, humidity, wind, radiation), and some air toxics (benzene, formaldehyde). Coverage is absent for composite indices (WBGT, UTCI), green space (NDVI), built environment, noise, social indices, and water contaminants.

### 2. Temporal Aggregation Method

CF `cell_methods` partially addresses this, but health research requires documenting how values should be interpreted relative to health event timing. "Annual mean PM2.5" and "daily PM2.5" are fundamentally different exposures -- no standard captures this, and OMOP has no field for it.

Known day-definition pitfalls:

- **PRISM:** 24h ending 12:00 GMT (7 AM EST) -- reported Tmax likely occurred on previous local calendar day
- **Daymet:** 24h preceding UTC midnight
- **NLDAS-2:** Hourly UTC
- **CMAQ:** Hourly UTC

### 3. Exposure Model Type

Whether a value comes from a direct monitor reading, satellite estimate, CTM simulation, or ML fusion product fundamentally affects interpretation and uncertainty. No standard captures this; OMOP has no field for it.

---

## Unit Standardization

| Environmental unit | UCUM code | Conversion from CF canonical |
|-------------------|-----------|------------------------------|
| ug/m3 (PM2.5, PM10) | ug/m3 | CF: kg/m3, multiply by 1e9 |
| ppb (O3, NO2, SO2) | ppb | CF: mol/mol, multiply by 1e9 |
| degrees Celsius | Cel | CF: K, subtract 273.15 |
| mg/L (water) | mg/L | Direct |
| NDVI (unitless) | 1 | Dimensionless ratio |
| dB(A) (noise) | dB | Direct |

---

## What Producers Must Provide for OMOP

Based on the `external_exposure` table field requirements:

| Requirement | Producer responsibility |
|-------------|----------------------|
| `exposure_concept_id` | Document what variable is measured in terms mappable to OMOP concepts |
| `exposure_start/end_date` | Document temporal coverage and aggregation method |
| `exposure_type_concept_id` | Document whether value is measured, modeled, or derived |
| `value_as_number` | Provide numeric values with clear semantics |
| `unit_concept_id` | Document units in UCUM-compatible form |

Beyond what `external_exposure` captures, EnVar micro-schemas should document: spatial resolution, temporal aggregation method, exposure model type, data provenance (URL/DOI), and spatial assignment guidance.

---

## Standards Bridging: CF <-> LinkML <-> OMOP

Building a CF-to-OMOP crosswalk requires:

1. Identifying the ~20--30 CF standard_names used in health-relevant datasets
2. Finding or proposing corresponding OMOP concept_ids
3. Documenting unit conversion (CF SI units to UCUM codes)

This crosswalk is a concrete EnVar deliverable that would directly enable data producers to make their outputs OMOP-compatible with minimal effort.
