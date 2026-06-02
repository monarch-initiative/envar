-- EnVar add-on: a per-day variant of the spatial join.
--
-- gaiaDB's working.spatial_join_exposure inserts one external_exposure
-- row per (location × data row), but the exposure_start_date /
-- exposure_end_date columns come from the *variable's* attr_start_date /
-- attr_end_date, not from the data row. For per-day temperature values
-- this collapses every day into the same window-wide date range.
--
-- This function does the same join but reads the per-row exposure dates
-- from the data table's `source_date` column. It is otherwise identical
-- to the patched spatial_join_exposure: same buffered point-in-polygon
-- check, same person_id / location_id resolution via working.location_merge,
-- same exposure_source_value semantics.
--
-- The result is written to working.external_exposure_perday so callers can
-- compare it against working.external_exposure (the native gaia output).

CREATE TABLE IF NOT EXISTS working.external_exposure_perday (
    LIKE working.external_exposure INCLUDING DEFAULTS INCLUDING CONSTRAINTS
);

CREATE OR REPLACE FUNCTION working.envar_spatial_join_perday(
    p_variable_name TEXT,
    p_data_source_table TEXT,
    p_spatial_operator TEXT DEFAULT 'st_within',
    p_buffer_meters NUMERIC DEFAULT 100
)
RETURNS INTEGER AS $$
DECLARE
    v_sql TEXT;
    v_count INTEGER;
    v_attr_concept_id INTEGER;
    v_unit_concept_id INTEGER;
    v_value_as_concept_id INTEGER;
BEGIN
    SELECT
        vs.attr_concept_id,
        vs.unit_concept_id,
        vs.value_as_concept_id
    INTO v_attr_concept_id, v_unit_concept_id, v_value_as_concept_id
    FROM backbone.variable_source vs
    WHERE vs.variable_name = p_variable_name
    LIMIT 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Variable "%" not registered in backbone.variable_source',
            p_variable_name;
    END IF;

    v_sql := format($SQL$
        INSERT INTO working.external_exposure_perday(
            location_id, person_id, exposure_concept_id,
            exposure_start_date, exposure_start_datetime,
            exposure_end_date, exposure_end_datetime,
            exposure_type_concept_id, exposure_relationship_concept_id,
            exposure_source_concept_id, exposure_source_value,
            exposure_relationship_source_value, dose_unit_source_value,
            quantity, modifier_source_value, operator_concept_id,
            value_as_number, value_as_concept_id, unit_concept_id
        )
        SELECT
            gol.location_id,
            CASE WHEN gol.domain_id = 1147314 THEN gol.entity_id ELSE 0 END
                AS person_id,
            COALESCE(%L::integer, 0) AS exposure_concept_id,
            geo.source_date AS exposure_start_date,
            geo.source_date::timestamp AS exposure_start_datetime,
            geo.source_date AS exposure_end_date,
            geo.source_date::timestamp AS exposure_end_datetime,
            0, 0, NULL,
            %L AS exposure_source_value,
            CAST(NULL AS VARCHAR(50)),
            CAST(NULL AS VARCHAR(50)),
            CAST(NULL AS INTEGER),
            CAST(NULL AS VARCHAR(50)),
            CAST(NULL AS INTEGER),
            geo.%I::numeric AS value_as_number,
            %L::integer AS value_as_concept_id,
            %L::integer AS unit_concept_id
        FROM (
            SELECT source_date, %I, wgs_geom FROM %s
        ) geo
        JOIN working.location_merge gol
            ON %s(
                gol.geom,
                CASE WHEN %L > 0
                     THEN ST_Buffer(geo.wgs_geom::geography, %L)::geometry
                     ELSE geo.wgs_geom END
            )
            AND geo.source_date BETWEEN gol.start_date AND gol.end_date
    $SQL$,
        v_attr_concept_id,
        p_variable_name,
        p_variable_name,
        v_value_as_concept_id,
        v_unit_concept_id,
        p_variable_name,
        p_data_source_table,
        p_spatial_operator,
        p_buffer_meters, p_buffer_meters
    );

    EXECUTE v_sql;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'EnVar per-day join: inserted % rows for variable %',
        v_count, p_variable_name;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;
