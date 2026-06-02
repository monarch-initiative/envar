# EnVar: Environmental Variables for Health Outcomes

Supporting the integration of environmental exposure data into the [OMOP Common Data Model](https://ohdsi.github.io/CommonDataModel/), in collaboration with the [OHDSI GIS Working Group](https://ohdsi.github.io/GIS/) and the [NIEHS HEW Data Accelerator](https://www.niehs.nih.gov/research/programs/extreme-weather).

## Background

The OHDSI GIS Working Group has built foundational infrastructure for linking geospatial environmental data to clinical records — including the [Gaia toolchain](https://ohdsi.github.io/GIS/gaia-intro.html), the [`external_exposure` schema extension](https://ohdsi.github.io/GIS/schema-extensions.html), and custom vocabularies for environmental exposures and social determinants of health. As more research teams begin integrating environmental variables into OMOP-based studies, there is a growing need for standardized metadata, broader vocabulary coverage, and practical guidance for environmental data producers.

EnVar contributes to this effort by bringing environmental health domain expertise, standards engineering, and connections to NIEHS data resources.

## What We Contribute

- **Landscape analysis** — surveying how environmental datasets are used in epidemiological research, what metadata is typically reported (or missing), and where gaps exist in current OMOP vocabulary coverage
- **Environmental micro-schemas** — [LinkML](https://linkml.io/)-based metadata specifications that capture the full context of environmental variables (what was measured, how, where, when, and at what resolution), complementing the structural work in Gaia. The authoritative source for the EnVar micro-schemas lives in a dedicated repo at **`~/ws/projects/linkml-microschemas-envar/`** — see [Related repositories](#related-repositories) below.
- **Vocabulary and metadata contributions** — working with the GIS WG to expand OMOP vocabulary coverage for environmental exposures and improve metadata standards for the [GAIA catalog](https://github.com/OHDSI/gaiaCatalog)
- **Guidance for data producers** — helping geospatial tool developers produce OMOP-compatible environmental data outputs

## Key Partners

| Partner | Role |
|---------|------|
| [OHDSI GIS Working Group](https://ohdsi.github.io/GIS/) | OMOP schema extensions, Gaia toolchain, vocabulary development |
| [NIEHS HEW Data Accelerator](https://www.niehs.nih.gov/research/programs/extreme-weather) | Program sponsor; GB-EDoH data standardization |
| [ORNL C-HER](https://arxiv.org/abs/2511.03750) | Exposomic data resource; test datasets |
| [All of Us](https://allofus.nih.gov/) | Environmental data integration via CHEL |
| [CLAD](https://github.com/cladteam) | Climate and Atmospheric Data team; All of Us environmental linkage |
| [ESIP Geodata 4 Health](https://www.esipfed.org/collaboration-areas/geo-data-4-health/) | Geospatial data standards and community collaboration |
| [CHORDS](https://www.niehs.nih.gov/research/programs/chords) | Climate and health data infrastructure |
| [CODATA](https://codata.org/) | Data standards expertise (via Jay Greenfield) |
| [African Population and Health Research Center](https://aphrc.org/) | HIV & climate change study site partners (Kenya) |
| [BioData Catalyst](https://biodatacatalyst.nhlbi.nih.gov/) | Geospatial data capacity for BDC; BDCHM data model |
| [Microschema](https://github.com/linkml/microschema) | LinkML-based CDE specifications for environmental variables |
| [Global Exposome Forum](https://humanexposomeproject.com/) | Exposomics community; ECTO and Monarch KG promotion |

## Related repositories

| Repo | Role |
|------|------|
| **`~/ws/projects/linkml-microschemas-envar/`** | **Authoritative source for the EnVar LinkML micro-schemas.** All schema drafts, slot additions, enum edits, structural revisions, and version bumps are made and documented there — not in this repo. This repo references and consumes the schemas; it does not own them. |
| `~/ws/notes/niehs_standards/` | Internal working repo — strategy, surveys, draft scenarios, research notes (kept private). |

## Team

[TIS Lab](https://tislab.org/) (Drs. Melissa Haendel and Anne Thessen, UNC Chapel Hill), funded by [NIEHS](https://www.niehs.nih.gov/).

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
