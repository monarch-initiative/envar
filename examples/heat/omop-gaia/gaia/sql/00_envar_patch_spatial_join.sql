-- EnVar patch to working.spatial_join_exposure
--
-- The upstream gaia-db function (OHDSI/gaiaDB/sql/04_spatial_join_functions.sql)
-- builds the inner `att` subquery with `SELECT * FROM backbone.variable_source`
-- and then *adds* overlay columns named `attr_start_date`, `attr_end_date`,
-- `attr_concept_id`, `unit_concept_id`, `value_as_concept_id`. Whenever the
-- variable_source row already carries any of those columns populated, the
-- subquery has two columns with the same name and PostgreSQL aborts the join
-- with "column reference attr_start_date is ambiguous".
--
-- This is a real upstream bug, encountered the first time we tried to run
-- the unmodified gaia spatial-join function against a JSON-LD-registered
-- variable. Fix: list the columns we actually need from variable_source
-- (variable_source_id, data_source_uuid, variable_name) instead of `*`.
-- Everything else is identical to the upstream implementation.
--
-- The two-point branch is removed because the heat scenario only uses the
-- 1-point path; reintroducing it would mean copying ~50 more lines of the
-- same pattern without any change in behaviour for this example.

CREATE OR REPLACE FUNCTION working.spatial_join_exposure(
    p_variable_name TEXT,
    p_data_source_table TEXT,
    p_geometry_source_table TEXT DEFAULT NULL,
    p_variable_merge_column TEXT DEFAULT NULL,
    p_geometry_merge_column TEXT DEFAULT NULL,
    p_spatial_operator TEXT DEFAULT 'st_within',
    p_buffer_meters NUMERIC DEFAULT 0
)
RETURNS INTEGER AS $$
DECLARE
    v_sql TEXT;
    v_variable_source_id INTEGER;
    v_data_source_uuid UUID;
    v_attr_concept_id INTEGER;
    v_unit_concept_id INTEGER;
    v_value_as_concept_id INTEGER;
    v_attr_start_date DATE;
    v_attr_end_date DATE;
    v_count INTEGER;
BEGIN
    IF p_geometry_source_table IS NOT NULL THEN
        RAISE EXCEPTION
            'EnVar patch: two-point spatial join not used by heat scenario; '
            'restore upstream implementation if needed';
    END IF;

    SELECT
        vs.variable_source_id,
        vs.data_source_uuid,
        vs.attr_concept_id,
        vs.unit_concept_id,
        vs.value_as_concept_id,
        COALESCE(vs.attr_start_date, vs.start_date),
        COALESCE(vs.attr_end_date, vs.end_date)
    INTO
        v_variable_source_id,
        v_data_source_uuid,
        v_attr_concept_id,
        v_unit_concept_id,
        v_value_as_concept_id,
        v_attr_start_date,
        v_attr_end_date
    FROM backbone.variable_source vs
    WHERE vs.variable_name = p_variable_name
    LIMIT 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Variable "%" not found in backbone.variable_source', p_variable_name;
    END IF;

    RAISE NOTICE 'Processing spatial join for variable: % (ID: %)',
        p_variable_name, v_variable_source_id;

    v_sql := format($SQL$
        INSERT INTO working.external_exposure(
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
            CASE WHEN att.attr_concept_id IS NOT NULL
                 THEN att.attr_concept_id::float::int ELSE 0 END
                AS exposure_concept_id,
            GREATEST(att.attr_start_date::date, gol.start_date)
                AS exposure_start_date,
            GREATEST(att.attr_start_date::timestamp, gol.start_date::timestamp)
                AS exposure_start_datetime,
            LEAST(att.attr_end_date::date, gol.end_date)
                AS exposure_end_date,
            LEAST(att.attr_end_date::timestamp, gol.end_date::timestamp)
                AS exposure_end_datetime,
            0 AS exposure_type_concept_id,
            0 AS exposure_relationship_concept_id,
            NULL AS exposure_source_concept_id,
            %L AS exposure_source_value,
            CAST(NULL AS VARCHAR(50)) AS exposure_relationship_source_value,
            CAST(NULL AS VARCHAR(50)) AS dose_unit_source_value,
            CAST(NULL AS INTEGER) AS quantity,
            CAST(NULL AS VARCHAR(50)) AS modifier_source_value,
            CAST(NULL AS INTEGER) AS operator_concept_id,
            geo.%I::numeric AS value_as_number,
            att.value_as_concept_id::float::integer AS value_as_concept_id,
            att.unit_concept_id::float::integer AS unit_concept_id
        FROM (
            SELECT
                vs.variable_source_id,
                vs.data_source_uuid,
                vs.variable_name,
                1 AS join_all,
                %L::integer AS attr_concept_id,
                %L::date AS attr_start_date,
                %L::date AS attr_end_date,
                %L::integer AS unit_concept_id,
                %L::integer AS value_as_concept_id
            FROM backbone.variable_source vs
            WHERE vs.variable_name = %L
        ) att
        INNER JOIN (
            SELECT %I, wgs_geom, 1 AS join_all
            FROM %s
        ) geo ON att.join_all = geo.join_all
        JOIN working.location_merge gol
            ON %s(
                gol.geom,
                CASE WHEN %L > 0
                     THEN ST_Buffer(geo.wgs_geom::geography, %L)::geometry
                     ELSE geo.wgs_geom
                END
            )
            AND (
                gol.start_date BETWEEN att.attr_start_date::date
                                   AND att.attr_end_date::date
                OR gol.end_date BETWEEN att.attr_start_date::date
                                    AND att.attr_end_date::date
                OR (gol.start_date <= att.attr_start_date::date
                    AND gol.end_date >= att.attr_end_date::date)
            )
    $SQL$,
        p_variable_name,
        p_variable_name,
        v_attr_concept_id, v_attr_start_date, v_attr_end_date,
        v_unit_concept_id, v_value_as_concept_id,
        p_variable_name,
        p_variable_name,
        p_data_source_table,
        p_spatial_operator,
        p_buffer_meters, p_buffer_meters
    );

    RAISE NOTICE 'Executing spatial join SQL...';
    EXECUTE v_sql;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE 'Spatial join complete. Inserted % exposure records for variable %',
        v_count, p_variable_name;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;
