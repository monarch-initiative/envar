# Pipeline

The EnVar ETL pipeline transforms environmental exposure data — the per-observation
values a geospatial tool produces, plus the EnVar provenance sidecar describing how
they were produced — into [OMOP CDM](https://ohdsi.github.io/CommonDataModel/) tables
under the [OHDSI GIS Working Group's](https://ohdsi.github.io/GIS/) `external_exposure`
schema extension.

- [ETL Pipeline: Usage and Specifications](etl.md) — how to run the pipeline, what it
  requires as input, what OMOP tables it produces, and its known limitations
- [D6.1: EnVar ETL Pipeline (LinkML-Map)](d6-1-report.md) — deliverable report covering
  the pipeline build, testing results, and status

## Design in one line

The transformation is **declarative, not imperative**: a
[linkml-map](https://linkml.io/linkml-map/) trans-spec states how each OMOP column is
derived from the source, and the linkml-map engine executes it. There is no
hand-written transformation code in the mapping step.

This matters for the project's central claim. EnVar's argument is that environmental
exposure data becomes reusable when the *transformation* is described as carefully as
the data — spatial-assignment method, temporal aggregation, day-boundary convention,
geocoding precision. A declarative spec makes the transformation itself an artifact you
can read, diff, and cite, rather than logic buried in a script.
