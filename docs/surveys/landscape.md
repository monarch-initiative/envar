# Environmental Data Standards Landscape

Deliverable 2.1.

!!! warning "Preliminary"
    This survey is a working document synthesized from deep-research reports. Findings have not been fully vetted by all stakeholders and may be revised.

---

## Executive Summary

This report surveys standards, tools, and projects linking environmental and geospatial data to clinical health outcomes.

**Key findings:**

1. **No ratified OMOP table for environmental data.** The OHDSI GIS Working Group has proposed the `external_exposure` table, but it is not in the official OMOP CDM spec. Every site uses ad-hoc workarounds. The GIS WG opened [gaiaCatalog Issue #19](https://github.com/OHDSI/gaiaCatalog/issues/19) in July 2025 to finalize the design.

2. **Limited OMOP vocabulary coverage.** The Exposome Vocabulary has ~79,000 toxin-target relationships, but most environmental exposure variables used in studies (air pollutants, water contaminants, noise, greenspace, climate variables) lack OMOP concept IDs. This is the single biggest blocker.

3. **Epic Healthy Planet captures SDoH but not environmental exposures.** Epic supports structured SDoH screening (PRAPARE, AHC-HRSN) at the point of care, encoded with LOINC; the values are subsequently mapped to OMOP's Observation table via downstream ETL. Environmental exposures have no clinical workflow equivalent -- they must always be linked post-hoc via geocoding.

4. **The Monarch/EHS-Data-Standards ecosystem provides schema infrastructure.** `linkml-microschema-profile` defines a composable CDE pattern EnVar should adopt. `exposome-schema` provides reusable exposure concepts but lacks geospatial metadata. `soma` models lab-assay outcomes but not population-level geospatial exposures.

5. **Most environmental epidemiology does not use OMOP.** European exposome projects (EHEN/EXPANSE, HELIX, UK Biobank), US cohort studies (ECHO, MESA Air), and government platforms (CDC Tracking, OpenSAFELY) use custom data models.

6. **Transformation metadata is the critical gap.** Across 42+ datasets, the spatial interpolation parameters, temporal aggregation windows, and exposure assignment methods that convert raw measurements into exposure estimates are systematically underreported.

---

## OHDSI GIS Working Group

### The `external_exposure` Table

Proposed CDM extension linking persons to place-based health determinants via `location_history`. Key fields: `person_id`, `location_id`, `exposure_concept_id`, `exposure_start/end_date`, `value_as_number`, `unit_concept_id`.

**What it cannot represent:**

| Limitation | Example |
|-----------|---------|
| Distributions / uncertainty | PM2.5 = 12.3 +/- 2.1 ug/m3 |
| Multi-component exposures | Air toxics risk = f(benzene, formaldehyde, ...) |
| Time series | Daily PM2.5 over a 90-day window |
| Spatial resolution metadata | "12km CMAQ grid cell" vs "1km LUR estimate" |
| Temporal aggregation method | "Annual mean" vs "98th percentile of daily values" |
| Exposure assessment method | CMAQ vs satellite-derived vs monitor interpolation |
| Data provenance | URL/DOI of source dataset, model version |

These limitations are what EnVar's micro-schemas and OMOP proposals should address.

### GAIA Toolchain

Four components: **gaiaDB** (PostGIS + OMOP integration), **gaiaCore** (R/Python/REST API), **gaiaCatalog** (Schema.org JSON-LD metadata), **gaiaDocker** (deployment). Architecture is sound; needs more content and vocabulary.

**Key gap:** GAIA uses Schema.org JSON-LD; EnVar uses LinkML. No bridge exists today, but LinkML can generate JSON-LD, making a bridge feasible.

### OMOP Vocabulary Coverage

| Vocabulary | Coverage |
|-----------|---------|
| **OMOP GIS Vocabulary** | Geographic and geospatial concepts |
| **OMOP Exposome Vocabulary** | ~79,000 toxin-target relationships (T3DB-sourced); thin on common epi variables |
| **OMOP SDoH Vocabulary** | SVI, ADI, EJI, COI; 6,738 concept associations (per OHDSI GIS WG); uses "Phenotypic Feature" domain |

**Critical gap:** Many commonly used environmental variables (PM2.5 at various aggregation levels, NO2, noise metrics, NDVI, heat indices) lack OMOP concept IDs.

---

## Epic Healthy Planet / SDoH

Epic's Healthy Planet supports structured SDoH screening at point of care. Environmental exposures differ fundamentally: they are area-based (not individual), have no clinical workflow (always retrospective linkage), and lack standard vocabulary.

**Area-level SDoH is the structural precedent.** Indicators like SVI and ADI face the same challenges as environmental exposures: values belong to geographies, not persons. They use the same geocoding -> spatial join -> `external_exposure` pipeline. Environmental data should follow this pattern.

---

## Monarch/EHS-Data-Standards Schemas

### soma

Models biological assays for airway biology (~40+ classes). `ExposureCondition` captures lab exposure (agent + concentration + duration) but not population-level geospatial exposures. The `QuantityValue` pattern is reusable; the AOP framework is conceptually relevant.

**Recommendation:** Don't import directly. Useful background, not a schema dependency.

### exposome-schema

`ExposureEvent` abstract class has relevant concepts (`exposure_route`, `exposure_medium`, `exposure_duration`) but inadequate types (bare strings, bare floats, no units). No support for spatial resolution, temporal aggregation, model type, or data source.

**Recommendation:** Reuse concepts but re-type them as proper value micro-schemas.

### linkml-microschema-profile

**The template EnVar micro-schemas should follow.** Defines composable, identifier-free CDEs:

| Class | Purpose |
|-------|---------|
| `Quantity` | Numeric value with unit (UCUM/UO/QUDT) |
| `Timepoint` | A point in time |
| `TimeInterval` | A period with start, end, duration |
| `CodedValue` | A term from a controlled vocabulary |

The `ClinicalMeasurementRecord` pattern provides the basis for an `EnvironmentalExposureRecord`. OMOP is already in the prefix map.

---

## Federal Programs

| Program | Focus | Status |
|---------|-------|--------|
| **HEW Data Accelerator** | EnVar's parent program; GB-EDoH standardization | Active |
| **ORNL C-HER** | 30+ spatially indexed exposomic datasets | Active; test datasets for EnVar |
| **CHORDS** | Climate and health data infrastructure (wildfires) | Active; 3-year, $4M NIEHS project |
| **CAFE RCC** | Climate-health research coordination (BU/Harvard) | Active; $6.7M NIEHS grant |

---

## European Exposome Projects

The largest coordinated exposure assessment efforts globally, but none use OMOP:

| Project | Scale | Focus |
|---------|-------|-------|
| **EHEN** | 9 sub-projects, 126 research groups, 24 countries; €100M+ (Horizon 2020) | Air pollution, noise, greenspace, chemicals. Sub-projects include EXPANSE, ATHLETE, EPHOR, EQUAL-LIFE, EXIMIOUS, HEDIMED, HEAP, LongITools, REMEDIA. |
| **EXPANSE** (EHEN sub-project) | Urban settings | LUR models becoming de facto standards |
| **ATHLETE** (EHEN sub-project) | 18 birth cohorts | Multi-omics + external exposome |
| **HELIX** | 32K mother-child pairs (exposure modeling); 1.2K subset (biomarkers) | 200+ exposures; rexposome R package |
| **HBM4EU** | 28 countries; ended June 2022 | Chemical biomonitoring (EUR 74M) |
| **PARC** | ~200 partners across 28 countries; 2022–2029; EUR 400M (50% EU / 50% Member States co-funded) | Chemical risk assessment |
| **UK Biobank** | 500K participants | Geocoded environmental linkages via NHS-linked addresses (addresses not released to researchers) |

---

## Clinical Data Integration

- **All of Us / CLAD / CHEL** -- CHEL annotates participants with H3 hex IDs and provides geospatial datasets. Jim Phuong's geocoding pipeline inspired the Geodata 4 Health collaboration.
- **FHIR PIT** (UNC Chapel Hill) -- Integrates EHR data (FHIR format) with EPA CMAQ, roadway, and Census ACS data. Validated on ~160K patients with asthma or related pulmonary conditions (Xu et al. 2022, PMC9015759). Feeds into **ICEES** (NCATS Biomedical Data Translator).

---

## Dataset Landscape

42+ environmental datasets routinely used in epidemiology, organized by domain. See the [priority variables survey](priority-variables.md) for the specific variables derived from these datasets.

### Most-Used Dataset Families

| Family | Example | Why it dominates |
|--------|---------|-----------------|
| Regulatory monitoring | EPA AQS | Authoritative, validated, long records |
| Satellite/reanalysis surfaces | MODIS AOD, ERA5 | Spatial completeness |
| National administrative systems | SDWIS, Superfund NPL | Policy-relevant |
| ML fusion exposure models | Di et al. PM2.5, CACES | Gap-filled, high-resolution |

### Cross-Cutting Methodological Challenges

- **Spatial misalignment:** 43--68% reduction in risk ratio estimates for primary pollutants (Goldman et al. 2010, Atlanta time-series, *Environ Sci Technol*; PMC2948846)
- **MAUP:** NO2-COVID-19 associations changed from positive to negative to null depending on aggregation strategy [VERIFY CLAIM]
- **Geocoding error:** 74.4% urban vs 10.5% rural address-level precision (Goin et al. 2017, French E3N cohort, *Environ Health*; PMC5324215)
- **Residential mobility:** 55% of Texas children with leukemia moved between birth and diagnosis (Janitz et al. 2019, *J Expo Sci Environ Epidemiol*; PMC11465071)

---

## The Gap: What No Existing Schema Captures

The **transformation metadata layer** -- spatial interpolation, temporal aggregation, exposure assignment, data fusion -- is not captured by any existing schema.

### Critical New Slots for Environmental Micro-Schemas

| Slot | Type | Critical? |
|------|------|-----------|
| `spatial_resolution` | CodedValue | **Yes** |
| `temporal_aggregation_method` | CodedValue | **Yes** |
| `exposure_model_type` | CodedValue | **Yes** |
| `data_source` | uri | **Yes** |
| `temporal_coverage` | TimeInterval | **Yes** |
| `buffer_distance` | Quantity | Maybe |
| `model_uncertainty` | Quantity | Maybe |

### Standards Silos

| Tradition | Standards | Blind Spots |
|-----------|----------|-------------|
| Geospatial/climate | CF Conventions, ISO 19115 | Nothing about epidemiological transformations |
| Biomedical | OMOP, FHIR, SNOMED, LOINC | No environmental exposure concepts |
| Ontological | ECTO, ENVO, ExO | No transformation metadata |

**No crosswalk exists** from CF standard_names to OMOP concepts. EnVar should produce SSSOM mappings from ECTO/ENVO/CHEBI to OMOP.

---

## Alignment Priorities

| Priority | Action | Impact |
|----------|--------|--------|
| 1 | Expand OMOP Exposome Vocabulary with environmental variable concepts | Highest -- biggest blocker |
| 2 | Support `external_exposure` table ratification via OHDSI governance | High -- structural prerequisite |
| 3 | Build on `linkml-microschema-profile` for environmental CDEs | Right pattern, team involved |
| 4 | Coordinate with OHDSI GIS WG on all proposals | All OMOP changes go through this group |
| 5 | Create SSSOM mappings from ECTO/ENVO/CHEBI to OMOP | Bridge the vocabulary silo |
| 6 | Design micro-schemas with 5--6 critical geospatial metadata slots | Keep it lean; iterate from use cases |
| 7 | Build GAIA <-> LinkML bridge via JSON-LD generation | Connect dataset and variable metadata |
