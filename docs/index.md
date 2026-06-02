# EnVar: Environmental Variables for Health Outcomes

Supporting the integration of environmental exposure data into the [OMOP Common Data Model](https://ohdsi.github.io/CommonDataModel/), in collaboration with the [OHDSI GIS Working Group](https://ohdsi.github.io/GIS/). EnVar is funded by the [NIEHS HEW Data Accelerator](https://www.niehs.nih.gov/research/programs/extreme-weather).

## Background

The OHDSI GIS Working Group has built foundational infrastructure for linking geospatial environmental data to clinical records — including the [Gaia toolchain](https://ohdsi.github.io/GIS/gaia-intro.html), the [`external_exposure` schema extension](https://ohdsi.github.io/GIS/schema-extensions.html), and custom vocabularies for environmental exposures and social determinants of health. As more research teams begin integrating environmental variables into OMOP-based studies, there is a growing need for standardized metadata, broader vocabulary coverage, and practical guidance for environmental data producers.

EnVar contributes to this effort by bringing environmental health domain expertise, standards engineering, and connections to NIEHS data resources.

## What We Contribute

- **Landscape analysis** — surveying how environmental datasets are used in epidemiological research, what metadata is typically reported (or missing), and where gaps exist in current OMOP vocabulary coverage
- **Environmental micro-schemas** — [LinkML](https://linkml.io/)-based metadata specifications that capture the full context of environmental variables (what was measured, how, where, when, and at what resolution), complementing the structural work in Gaia
- **Vocabulary and metadata contributions** — working with the GIS WG to expand OMOP vocabulary coverage for environmental exposures and improve metadata standards for [gaiaCatalog](https://github.com/OHDSI/gaiaCatalog)
- **Guidance for data producers** — helping geospatial tool developers produce OMOP-compatible environmental data outputs

## Related Projects

EnVar sits within a broader landscape of [TISLab projects](projects/index.md) that connect geospatial data and health outcomes. These include work on [HIV & climate change](projects/hiv-climate.md), [environmental CDEs](projects/geodata4health.md), [All of Us data linkage](projects/clad.md), and [BioData Catalyst](projects/bdc-dmc.md).
