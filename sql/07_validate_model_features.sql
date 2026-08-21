-- ============================================================
-- NFL FANTASY FOOTBALL ADVISOR
-- INDEPENDENT MODEL-FEATURE VALIDATION
--
-- File:
-- sql/07_validate_model_features.sql
--
-- Purpose:
-- Independently validate the feature-engineering layer before
-- exporting modeling data or training a projection model.
--
-- This script is read-only. It must not create, update,
-- truncate, or delete data.
--
-- Model grain:
-- season + week + player_id
--
-- Target:
-- target_fantasy_points_ppr
--
-- Chronological split:
-- Training:   2018-2023
-- Validation: 2024
-- Test:       2025
-- ============================================================

USE nfl_fantasy_advisor;

-- ============================================================
-- 1. ACTIVE DATABASE AND REQUIRED TABLES
-- ============================================================

SELECT
    DATABASE() AS active_database;

WITH required_tables AS (
    SELECT 'player_weeks' AS table_name
    UNION ALL
    SELECT 'player_game_history'
    UNION ALL
    SELECT 'opponent_position_week_history'
    UNION ALL
    SELECT 'model_player_weeks'
)
SELECT
    r.table_name,
    CASE
        WHEN t.table_name IS NOT NULL THEN 1
        ELSE 0
    END AS table_exists,
    CASE
        WHEN t.table_name IS NOT NULL THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM required_tables AS r
LEFT JOIN information_schema.tables AS t
    ON t.table_schema = DATABASE()
    AND t.table_name = r.table_name
ORDER BY
    r.table_name;

-- ============================================================
-- 2. FEATURE-LAYER ROW-COUNT RECONCILIATION
-- ============================================================

WITH table_counts AS (
    SELECT
        'player_game_history' AS table_name,
        45693 AS expected_rows,
        COUNT(*) AS actual_rows
    FROM player_game_history
    UNION ALL
    SELECT
        'opponent_position_week_history',
        16994,
        COUNT(*)
    FROM opponent_position_week_history
    UNION ALL
    SELECT
        'model_player_weeks',
        45693,
        COUNT(*)
    FROM model_player_weeks
)
SELECT
    table_name,
    expected_rows,
    actual_rows,
    actual_rows - expected_rows AS row_difference,
    CASE
        WHEN actual_rows = expected_rows THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM table_counts
ORDER BY
    table_name;

-- ============================================================
-- 3. GRAIN, KEYS, AND REQUIRED-VALUE VALIDATION
-- ============================================================

SELECT
    'player_game_history' AS table_name,
    'season, week, player_id' AS intended_grain,
    COUNT(*) AS total_rows,
    COUNT(
        DISTINCT CONCAT_WS(
            '|',
            season,
            week,
            player_id
        )
    ) AS distinct_keys,
    COUNT(*) - COUNT(
        DISTINCT CONCAT_WS(
            '|',
            season,
            week,
            player_id
        )
    ) AS duplicate_rows_above_grain,
    SUM(
        season IS NULL
        OR week IS NULL
        OR NULLIF(TRIM(player_id), '') IS NULL
        OR NULLIF(TRIM(game_id), '') IS NULL
        OR game_date IS NULL
        OR NULLIF(TRIM(team), '') IS NULL
        OR NULLIF(TRIM(opponent), '') IS NULL
        OR NULLIF(TRIM(position), '') IS NULL
        OR target_fantasy_points_ppr IS NULL
        OR NULLIF(TRIM(data_split), '') IS NULL
    ) AS unavailable_required_value_rows,
    CASE
        WHEN COUNT(*) = COUNT(
                DISTINCT CONCAT_WS(
                    '|',
                    season,
                    week,
                    player_id
                )
            )
            AND SUM(
                season IS NULL
                OR week IS NULL
                OR NULLIF(TRIM(player_id), '') IS NULL
                OR NULLIF(TRIM(game_id), '') IS NULL
                OR game_date IS NULL
                OR NULLIF(TRIM(team), '') IS NULL
                OR NULLIF(TRIM(opponent), '') IS NULL
                OR NULLIF(TRIM(position), '') IS NULL
                OR target_fantasy_points_ppr IS NULL
                OR NULLIF(TRIM(data_split), '') IS NULL
            ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM player_game_history
UNION ALL
SELECT
    'opponent_position_week_history',
    'season, week, defensive_team, position',
    COUNT(*),
    COUNT(
        DISTINCT CONCAT_WS(
            '|',
            season,
            week,
            defensive_team,
            position
        )
    ),
    COUNT(*) - COUNT(
        DISTINCT CONCAT_WS(
            '|',
            season,
            week,
            defensive_team,
            position
        )
    ),
    SUM(
        season IS NULL
        OR week IS NULL
        OR NULLIF(TRIM(game_id), '') IS NULL
        OR game_date IS NULL
        OR NULLIF(TRIM(defensive_team), '') IS NULL
        OR NULLIF(TRIM(offensive_team), '') IS NULL
        OR NULLIF(TRIM(position), '') IS NULL
        OR fantasy_points_ppr_allowed IS NULL
        OR NULLIF(TRIM(data_split), '') IS NULL
    ),
    CASE
        WHEN COUNT(*) = COUNT(
                DISTINCT CONCAT_WS(
                    '|',
                    season,
                    week,
                    defensive_team,
                    position
                )
            )
            AND SUM(
                season IS NULL
                OR week IS NULL
                OR NULLIF(TRIM(game_id), '') IS NULL
                OR game_date IS NULL
                OR NULLIF(TRIM(defensive_team), '') IS NULL
                OR NULLIF(TRIM(offensive_team), '') IS NULL
                OR NULLIF(TRIM(position), '') IS NULL
                OR fantasy_points_ppr_allowed IS NULL
                OR NULLIF(TRIM(data_split), '') IS NULL
            ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END
FROM opponent_position_week_history
UNION ALL
SELECT
    'model_player_weeks',
    'season, week, player_id',
    COUNT(*),
    COUNT(
        DISTINCT CONCAT_WS(
            '|',
            season,
            week,
            player_id
        )
    ),
    COUNT(*) - COUNT(
        DISTINCT CONCAT_WS(
            '|',
            season,
            week,
            player_id
        )
    ),
    SUM(
        season IS NULL
        OR week IS NULL
        OR NULLIF(TRIM(player_id), '') IS NULL
        OR NULLIF(TRIM(game_id), '') IS NULL
        OR game_date IS NULL
        OR NULLIF(TRIM(team), '') IS NULL
        OR NULLIF(TRIM(opponent), '') IS NULL
        OR NULLIF(TRIM(position), '') IS NULL
        OR target_fantasy_points_ppr IS NULL
        OR NULLIF(TRIM(data_split), '') IS NULL
        OR NULLIF(TRIM(feature_version), '') IS NULL
    ),
    CASE
        WHEN COUNT(*) = COUNT(
                DISTINCT CONCAT_WS(
                    '|',
                    season,
                    week,
                    player_id
                )
            )
            AND SUM(
                season IS NULL
                OR week IS NULL
                OR NULLIF(TRIM(player_id), '') IS NULL
                OR NULLIF(TRIM(game_id), '') IS NULL
                OR game_date IS NULL
                OR NULLIF(TRIM(team), '') IS NULL
                OR NULLIF(TRIM(opponent), '') IS NULL
                OR NULLIF(TRIM(position), '') IS NULL
                OR target_fantasy_points_ppr IS NULL
                OR NULLIF(TRIM(data_split), '') IS NULL
                OR NULLIF(TRIM(feature_version), '') IS NULL
            ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END
FROM model_player_weeks;

-- ============================================================
-- 4. SOURCE-ROW AND TARGET RECONCILIATION
-- ============================================================

WITH source_counts AS (
    SELECT
        COUNT(*) AS source_player_week_rows
    FROM player_weeks
),
model_to_source AS (
    SELECT
        COUNT(*) AS model_rows,
        SUM(pw.player_id IS NULL)
            AS model_rows_without_source,
        SUM(
            pw.player_id IS NOT NULL
            AND ABS(
                m.target_fantasy_points_ppr
                - pw.fantasy_points_ppr
            ) > 0.0000000001
        ) AS target_mismatch_rows
    FROM model_player_weeks AS m
    LEFT JOIN player_weeks AS pw
        ON pw.season = m.season
        AND pw.week = m.week
        AND pw.player_id = m.player_id
),
source_to_model AS (
    SELECT
        SUM(m.player_id IS NULL)
            AS source_rows_missing_from_model
    FROM player_weeks AS pw
    LEFT JOIN model_player_weeks AS m
        ON m.season = pw.season
        AND m.week = pw.week
        AND m.player_id = pw.player_id
)
SELECT
    s.source_player_week_rows,
    ms.model_rows,
    ms.model_rows - s.source_player_week_rows
        AS row_difference,
    ms.model_rows_without_source,
    sm.source_rows_missing_from_model,
    ms.target_mismatch_rows,
    CASE
        WHEN ms.model_rows = s.source_player_week_rows
            AND ms.model_rows_without_source = 0
            AND sm.source_rows_missing_from_model = 0
            AND ms.target_mismatch_rows = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM source_counts AS s
CROSS JOIN model_to_source AS ms
CROSS JOIN source_to_model AS sm;

-- ============================================================
-- 5. CHRONOLOGICAL SPLIT AND DOMAIN VALIDATION
-- ============================================================

WITH audited_rows AS (
    SELECT
        m.*,
        CASE
            WHEN m.season BETWEEN 2018 AND 2023
                THEN 'training'
            WHEN m.season = 2024
                THEN 'validation'
            WHEN m.season = 2025
                THEN 'test'
        END AS expected_split
    FROM model_player_weeks AS m
)
SELECT
    season,
    expected_split,
    GROUP_CONCAT(
        DISTINCT data_split
        ORDER BY data_split
    ) AS observed_splits,
    COUNT(*) AS model_rows,
    MIN(week) AS minimum_week,
    MAX(week) AS maximum_week,
    MIN(game_date) AS minimum_game_date,
    MAX(game_date) AS maximum_game_date,
    COUNT(DISTINCT position) AS distinct_positions,
    SUM(data_split <> expected_split)
        AS split_mismatch_rows,
    SUM(position NOT IN ('QB', 'RB', 'WR', 'TE'))
        AS invalid_position_rows,
    SUM(week NOT BETWEEN 1 AND 18)
        AS invalid_week_rows,
    SUM(game_location NOT IN ('HOME', 'AWAY'))
        AS invalid_location_rows,
    SUM(is_home NOT IN (0, 1))
        AS invalid_home_flag_rows,
    SUM(feature_version <> 'v1_prior_game')
        AS invalid_feature_version_rows,
    CASE
        WHEN SUM(data_split <> expected_split) = 0
            AND SUM(
                position NOT IN ('QB', 'RB', 'WR', 'TE')
            ) = 0
            AND SUM(week NOT BETWEEN 1 AND 18) = 0
            AND SUM(
                game_location NOT IN ('HOME', 'AWAY')
            ) = 0
            AND SUM(is_home NOT IN (0, 1)) = 0
            AND SUM(
                feature_version <> 'v1_prior_game'
            ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM audited_rows
GROUP BY
    season,
    expected_split
ORDER BY
    season;

-- ============================================================
-- 6. HISTORY COUNTS, FLAGS, AND TEMPORAL ANCHORS
-- ============================================================

SELECT
    COUNT(*) AS model_rows,
    SUM(
        prior_games_count < 0
        OR prior_games_current_season < 0
        OR prior_games_current_season
            > prior_games_count
        OR opponent_prior_position_games < 0
        OR opponent_prior_position_games_current_season < 0
        OR opponent_prior_position_games_current_season
            > opponent_prior_position_games
        OR snap_records_last_3_games < 0
        OR snap_records_last_5_games < 0
    ) AS invalid_history_count_rows,
    SUM(
        is_first_observed_game
            <> (prior_games_count = 0)
    ) AS first_game_flag_mismatch_rows,
    SUM(
        is_first_observed_game_of_season
            <> (prior_games_current_season = 0)
    ) AS first_season_game_flag_mismatch_rows,
    SUM(
        has_previous_game
            <> (prior_games_count >= 1)
    ) AS previous_game_flag_mismatch_rows,
    SUM(
        has_3_prior_games
            <> (prior_games_count >= 3)
    ) AS three_prior_games_flag_mismatch_rows,
    SUM(
        has_5_prior_games
            <> (prior_games_count >= 5)
    ) AS five_prior_games_flag_mismatch_rows,
    SUM(
        has_opponent_history
            <> (opponent_prior_position_games >= 1)
    ) AS opponent_history_flag_mismatch_rows,
    SUM(
        team_changed_since_previous_game
            <> CASE
                WHEN previous_team IS NOT NULL
                    AND previous_team <> team
                THEN 1
                ELSE 0
            END
    ) AS team_change_flag_mismatch_rows,
    SUM(
        previous_game_date IS NOT NULL
        AND previous_game_date >= game_date
    ) AS nonprior_previous_game_date_rows,
    SUM(
        previous_game_season > season
    ) AS future_previous_game_season_rows,
    SUM(
        previous_game_season = season
        AND previous_game_week >= week
    ) AS nonprior_same_season_week_rows,
    SUM(
        previous_game_date IS NULL
        AND days_since_previous_game IS NOT NULL
    ) AS days_present_without_previous_game_rows,
    SUM(
        previous_game_date IS NOT NULL
        AND days_since_previous_game
            <> DATEDIFF(
                game_date,
                previous_game_date
            )
    ) AS days_since_previous_game_mismatch_rows,
    SUM(
        has_previous_snap_record = 1
        AND offense_pct_prev_game IS NULL
    ) AS missing_previous_snap_when_flagged_rows,
    SUM(
        has_previous_snap_record = 0
        AND offense_pct_prev_game IS NOT NULL
    ) AS snap_present_without_flag_rows
FROM model_player_weeks;

-- ============================================================
-- 7. TARGET AND CONFIGURED FULL-PPR RECONCILIATION
--
-- The target is retained as the supervised-learning label.
-- It must never be included in the predictor matrix.
-- ============================================================

SELECT
    COUNT(*) AS model_rows,
    SUM(
        pw.player_id IS NULL
        OR h.player_id IS NULL
    ) AS unmatched_reconciliation_rows,
    SUM(
        ABS(
            m.target_fantasy_points_ppr
            - pw.fantasy_points_ppr
        ) > 0.0000000001
    ) AS model_to_source_target_mismatch_rows,
    SUM(
        ABS(
            m.target_fantasy_points_ppr
            - h.target_fantasy_points_ppr
        ) > 0.0000000001
    ) AS model_to_history_target_mismatch_rows,
    SUM(
        ABS(
            h.target_fantasy_points_ppr
            - h.calculated_fantasy_points_ppr
        ) > 0.01
    ) AS configured_ppr_mismatch_rows,
    MAX(
        ABS(
            m.target_fantasy_points_ppr
            - pw.fantasy_points_ppr
        )
    ) AS maximum_model_source_difference,
    MAX(
        ABS(
            m.target_fantasy_points_ppr
            - h.target_fantasy_points_ppr
        )
    ) AS maximum_model_history_difference,
    MAX(
        ABS(
            h.target_fantasy_points_ppr
            - h.calculated_fantasy_points_ppr
        )
    ) AS maximum_configured_ppr_difference,
    CASE
        WHEN SUM(
                pw.player_id IS NULL
                OR h.player_id IS NULL
            ) = 0
            AND SUM(
                ABS(
                    m.target_fantasy_points_ppr
                    - pw.fantasy_points_ppr
                ) > 0.0000000001
            ) = 0
            AND SUM(
                ABS(
                    m.target_fantasy_points_ppr
                    - h.target_fantasy_points_ppr
                ) > 0.0000000001
            ) = 0
            AND SUM(
                ABS(
                    h.target_fantasy_points_ppr
                    - h.calculated_fantasy_points_ppr
                ) > 0.01
            ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM model_player_weeks AS m
LEFT JOIN player_weeks AS pw
    ON pw.season = m.season
    AND pw.week = m.week
    AND pw.player_id = m.player_id
LEFT JOIN player_game_history AS h
    ON h.season = m.season
    AND h.week = m.week
    AND h.player_id = m.player_id;

-- ============================================================
-- 8. PREVIOUS-GAME FEATURE RECORD TRACE
--
-- Stored previous-game season and week values are used to
-- locate the exact historical source row. All target-row and
-- feature values are then independently compared.
-- ============================================================

SELECT
    COUNT(*) AS model_rows,
    SUM(m.has_previous_game = 1)
        AS rows_with_previous_game,
    SUM(
        m.has_previous_game = 1
        AND h.player_id IS NOT NULL
    ) AS matched_previous_history_rows,
    SUM(
        m.has_previous_game = 1
        AND h.player_id IS NULL
    ) AS unmatched_previous_history_rows,
    SUM(
        m.has_previous_game = 0
        AND (
            m.fantasy_points_ppr_prev_game IS NOT NULL
            OR m.attempts_prev_game IS NOT NULL
            OR m.carries_prev_game IS NOT NULL
            OR m.targets_prev_game IS NOT NULL
            OR m.receptions_prev_game IS NOT NULL
            OR m.touches_prev_game IS NOT NULL
            OR m.opportunities_prev_game IS NOT NULL
            OR m.passing_yards_prev_game IS NOT NULL
            OR m.rushing_yards_prev_game IS NOT NULL
            OR m.receiving_yards_prev_game IS NOT NULL
            OR m.yards_from_scrimmage_prev_game IS NOT NULL
            OR m.total_offensive_tds_prev_game IS NOT NULL
            OR m.target_share_prev_game IS NOT NULL
            OR m.air_yards_share_prev_game IS NOT NULL
            OR m.wopr_prev_game IS NOT NULL
            OR m.offense_snaps_prev_game IS NOT NULL
            OR m.offense_pct_prev_game IS NOT NULL
        )
    ) AS first_game_rows_with_previous_feature_leakage,
    SUM(
        m.has_previous_game = 1
        AND h.player_id IS NOT NULL
        AND (
            m.previous_game_date <> h.game_date
            OR NOT (m.previous_team <=> h.team)
        )
    ) AS previous_context_mismatch_rows,
    SUM(
        m.has_previous_game = 1
        AND h.player_id IS NOT NULL
        AND h.game_id = m.game_id
    ) AS rows_using_target_game_as_previous_history,
    SUM(
        m.has_previous_game = 1
        AND h.player_id IS NOT NULL
        AND h.game_date >= m.game_date
    ) AS nonprior_history_rows,
    SUM(
        m.has_previous_game = 1
        AND h.player_id IS NOT NULL
        AND ABS(
            m.fantasy_points_ppr_prev_game
            - h.target_fantasy_points_ppr
        ) > 0.0000000001
    ) AS previous_ppr_mismatch_rows,
    SUM(
        m.has_previous_game = 1
        AND h.player_id IS NOT NULL
        AND (
            m.attempts_prev_game <> h.attempts
            OR m.carries_prev_game <> h.carries
            OR m.targets_prev_game <> h.targets
            OR m.receptions_prev_game <> h.receptions
            OR m.touches_prev_game <> h.touches
            OR m.opportunities_prev_game
                <> h.position_adjusted_opportunities
        )
    ) AS previous_volume_mismatch_rows,
    SUM(
        m.has_previous_game = 1
        AND h.player_id IS NOT NULL
        AND (
            m.passing_yards_prev_game
                <> h.passing_yards
            OR m.rushing_yards_prev_game
                <> h.rushing_yards
            OR m.receiving_yards_prev_game
                <> h.receiving_yards
            OR m.yards_from_scrimmage_prev_game
                <> h.yards_from_scrimmage
            OR m.total_offensive_tds_prev_game
                <> h.total_offensive_tds
        )
    ) AS previous_production_mismatch_rows,
    SUM(
        m.has_previous_game = 1
        AND h.player_id IS NOT NULL
        AND (
            ABS(
                m.target_share_prev_game
                - h.target_share
            ) > 0.0000000001
            OR ABS(
                m.air_yards_share_prev_game
                - h.air_yards_share
            ) > 0.0000000001
            OR ABS(
                m.wopr_prev_game
                - h.wopr
            ) > 0.0000000001
        )
    ) AS previous_usage_share_mismatch_rows,
    SUM(
        m.has_previous_game = 1
        AND h.player_id IS NOT NULL
        AND NOT (
            (
                m.offense_snaps_prev_game IS NULL
                AND h.offense_snaps IS NULL
            )
            OR (
                m.offense_snaps_prev_game IS NOT NULL
                AND h.offense_snaps IS NOT NULL
                AND ABS(
                    m.offense_snaps_prev_game
                    - h.offense_snaps
                ) <= 0.0000000001
            )
        )
    ) AS previous_offense_snaps_mismatch_rows,
    SUM(
        m.has_previous_game = 1
        AND h.player_id IS NOT NULL
        AND NOT (
            (
                m.offense_pct_prev_game IS NULL
                AND h.offense_pct IS NULL
            )
            OR (
                m.offense_pct_prev_game IS NOT NULL
                AND h.offense_pct IS NOT NULL
                AND ABS(
                    m.offense_pct_prev_game
                    - h.offense_pct
                ) <= 0.0000000001
            )
        )
    ) AS previous_offense_pct_mismatch_rows,
    MAX(
        CASE
            WHEN m.has_previous_game = 1
                AND h.player_id IS NOT NULL
            THEN ABS(
                m.fantasy_points_ppr_prev_game
                - h.target_fantasy_points_ppr
            )
        END
    ) AS maximum_previous_ppr_difference,
    CASE
        WHEN SUM(
                m.has_previous_game = 1
                AND h.player_id IS NULL
            ) = 0
            AND SUM(
                m.has_previous_game = 0
                AND (
                    m.fantasy_points_ppr_prev_game IS NOT NULL
                    OR m.attempts_prev_game IS NOT NULL
                    OR m.carries_prev_game IS NOT NULL
                    OR m.targets_prev_game IS NOT NULL
                    OR m.opportunities_prev_game IS NOT NULL
                    OR m.offense_pct_prev_game IS NOT NULL
                )
            ) = 0
            AND SUM(
                m.has_previous_game = 1
                AND h.player_id IS NOT NULL
                AND (
                    m.previous_game_date <> h.game_date
                    OR NOT (m.previous_team <=> h.team)
                )
            ) = 0
            AND SUM(
                m.has_previous_game = 1
                AND h.player_id IS NOT NULL
                AND h.game_id = m.game_id
            ) = 0
            AND SUM(
                m.has_previous_game = 1
                AND h.player_id IS NOT NULL
                AND h.game_date >= m.game_date
            ) = 0
            AND SUM(
                m.has_previous_game = 1
                AND h.player_id IS NOT NULL
                AND ABS(
                    m.fantasy_points_ppr_prev_game
                    - h.target_fantasy_points_ppr
                ) > 0.0000000001
            ) = 0
            AND SUM(
                m.has_previous_game = 1
                AND h.player_id IS NOT NULL
                AND (
                    m.attempts_prev_game <> h.attempts
                    OR m.carries_prev_game <> h.carries
                    OR m.targets_prev_game <> h.targets
                    OR m.receptions_prev_game <> h.receptions
                    OR m.touches_prev_game <> h.touches
                    OR m.opportunities_prev_game
                        <> h.position_adjusted_opportunities
                )
            ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM model_player_weeks AS m
LEFT JOIN player_game_history AS h
    ON m.has_previous_game = 1
    AND h.season = m.previous_game_season
    AND h.week = m.previous_game_week
    AND h.player_id = m.player_id;

-- ============================================================
-- 9. ROLLING PERFORMANCE, VOLUME, AND PRODUCTION RECONCILIATION
--
-- Every validation window ends at 1 PRECEDING. Comparisons are
-- rounded to ten decimal places only to ignore harmless binary
-- floating-point representation differences.
-- ============================================================

WITH expected_features AS (
    SELECT
        h.season,
        h.week,
        h.player_id,
        AVG(h.target_fantasy_points_ppr)
            OVER w_last_3
            AS expected_ppr_avg_last_3,
        AVG(h.target_fantasy_points_ppr)
            OVER w_last_5
            AS expected_ppr_avg_last_5,
        STDDEV_SAMP(h.target_fantasy_points_ppr)
            OVER w_last_5
            AS expected_ppr_stddev_last_5,
        MIN(h.target_fantasy_points_ppr)
            OVER w_last_5
            AS expected_ppr_min_last_5,
        MAX(h.target_fantasy_points_ppr)
            OVER w_last_5
            AS expected_ppr_max_last_5,
        AVG(h.target_fantasy_points_ppr)
            OVER w_season
            AS expected_ppr_season_to_date,
        STDDEV_SAMP(h.target_fantasy_points_ppr)
            OVER w_season
            AS expected_ppr_stddev_season_to_date,
        AVG(h.attempts) OVER w_last_3
            AS expected_attempts_avg_last_3,
        AVG(h.attempts) OVER w_last_5
            AS expected_attempts_avg_last_5,
        AVG(h.attempts) OVER w_season
            AS expected_attempts_season_to_date,
        AVG(h.carries) OVER w_last_3
            AS expected_carries_avg_last_3,
        AVG(h.carries) OVER w_last_5
            AS expected_carries_avg_last_5,
        AVG(h.carries) OVER w_season
            AS expected_carries_season_to_date,
        AVG(h.targets) OVER w_last_3
            AS expected_targets_avg_last_3,
        AVG(h.targets) OVER w_last_5
            AS expected_targets_avg_last_5,
        AVG(h.targets) OVER w_season
            AS expected_targets_season_to_date,
        AVG(h.receptions) OVER w_last_3
            AS expected_receptions_avg_last_3,
        AVG(h.receptions) OVER w_last_5
            AS expected_receptions_avg_last_5,
        AVG(h.touches) OVER w_last_3
            AS expected_touches_avg_last_3,
        AVG(h.touches) OVER w_last_5
            AS expected_touches_avg_last_5,
        AVG(h.position_adjusted_opportunities)
            OVER w_last_3
            AS expected_opportunities_avg_last_3,
        AVG(h.position_adjusted_opportunities)
            OVER w_last_5
            AS expected_opportunities_avg_last_5,
        AVG(h.position_adjusted_opportunities)
            OVER w_season
            AS expected_opportunities_season_to_date,
        AVG(h.passing_yards) OVER w_last_3
            AS expected_passing_yards_avg_last_3,
        AVG(h.rushing_yards) OVER w_last_3
            AS expected_rushing_yards_avg_last_3,
        AVG(h.receiving_yards) OVER w_last_3
            AS expected_receiving_yards_avg_last_3,
        AVG(h.yards_from_scrimmage) OVER w_last_3
            AS expected_scrimmage_yards_avg_last_3,
        AVG(h.total_offensive_tds) OVER w_last_3
            AS expected_offensive_tds_avg_last_3
    FROM player_game_history AS h
    WINDOW
        w_last_3 AS (
            PARTITION BY h.player_id
            ORDER BY
                h.season,
                h.week,
                h.game_date,
                h.game_id
            ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
        ),
        w_last_5 AS (
            PARTITION BY h.player_id
            ORDER BY
                h.season,
                h.week,
                h.game_date,
                h.game_id
            ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
        ),
        w_season AS (
            PARTITION BY
                h.player_id,
                h.season
            ORDER BY
                h.week,
                h.game_date,
                h.game_id
            ROWS BETWEEN UNBOUNDED PRECEDING
                AND 1 PRECEDING
        )
)
SELECT
    COUNT(*) AS model_rows,
    SUM(e.player_id IS NULL)
        AS unmatched_expected_feature_rows,
    SUM(
        m.prior_games_count = 0
        AND (
            m.fantasy_points_ppr_avg_last_3_games
                IS NOT NULL
            OR m.fantasy_points_ppr_avg_last_5_games
                IS NOT NULL
            OR m.attempts_avg_last_3_games IS NOT NULL
            OR m.carries_avg_last_3_games IS NOT NULL
            OR m.targets_avg_last_3_games IS NOT NULL
            OR m.receptions_avg_last_3_games IS NOT NULL
            OR m.touches_avg_last_3_games IS NOT NULL
            OR m.opportunities_avg_last_3_games
                IS NOT NULL
            OR m.passing_yards_avg_last_3_games
                IS NOT NULL
            OR m.rushing_yards_avg_last_3_games
                IS NOT NULL
            OR m.receiving_yards_avg_last_3_games
                IS NOT NULL
            OR m.total_offensive_tds_avg_last_3_games
                IS NOT NULL
        )
    ) AS first_game_rows_with_rolling_feature_leakage,
    SUM(
        e.player_id IS NOT NULL
        AND (
            NOT (
                ROUND(
                    m.fantasy_points_ppr_avg_last_3_games,
                    10
                )
                <=>
                ROUND(e.expected_ppr_avg_last_3, 10)
            )
            OR NOT (
                ROUND(
                    m.fantasy_points_ppr_avg_last_5_games,
                    10
                )
                <=>
                ROUND(e.expected_ppr_avg_last_5, 10)
            )
            OR NOT (
                ROUND(
                    m.fantasy_points_ppr_stddev_last_5_games,
                    10
                )
                <=>
                ROUND(e.expected_ppr_stddev_last_5, 10)
            )
            OR NOT (
                ROUND(
                    m.fantasy_points_ppr_min_last_5_games,
                    10
                )
                <=>
                ROUND(e.expected_ppr_min_last_5, 10)
            )
            OR NOT (
                ROUND(
                    m.fantasy_points_ppr_max_last_5_games,
                    10
                )
                <=>
                ROUND(e.expected_ppr_max_last_5, 10)
            )
            OR NOT (
                ROUND(
                    m.fantasy_points_ppr_season_to_date,
                    10
                )
                <=>
                ROUND(e.expected_ppr_season_to_date, 10)
            )
            OR NOT (
                ROUND(
                    m.fantasy_points_ppr_stddev_season_to_date,
                    10
                )
                <=>
                ROUND(
                    e.expected_ppr_stddev_season_to_date,
                    10
                )
            )
        )
    ) AS rolling_ppr_mismatch_rows,
    SUM(
        e.player_id IS NOT NULL
        AND (
            NOT (
                ROUND(m.attempts_avg_last_3_games, 10)
                <=>
                ROUND(e.expected_attempts_avg_last_3, 10)
            )
            OR NOT (
                ROUND(m.attempts_avg_last_5_games, 10)
                <=>
                ROUND(e.expected_attempts_avg_last_5, 10)
            )
            OR NOT (
                ROUND(m.attempts_season_to_date, 10)
                <=>
                ROUND(
                    e.expected_attempts_season_to_date,
                    10
                )
            )
            OR NOT (
                ROUND(m.carries_avg_last_3_games, 10)
                <=>
                ROUND(e.expected_carries_avg_last_3, 10)
            )
            OR NOT (
                ROUND(m.carries_avg_last_5_games, 10)
                <=>
                ROUND(e.expected_carries_avg_last_5, 10)
            )
            OR NOT (
                ROUND(m.carries_season_to_date, 10)
                <=>
                ROUND(
                    e.expected_carries_season_to_date,
                    10
                )
            )
            OR NOT (
                ROUND(m.targets_avg_last_3_games, 10)
                <=>
                ROUND(e.expected_targets_avg_last_3, 10)
            )
            OR NOT (
                ROUND(m.targets_avg_last_5_games, 10)
                <=>
                ROUND(e.expected_targets_avg_last_5, 10)
            )
            OR NOT (
                ROUND(m.targets_season_to_date, 10)
                <=>
                ROUND(
                    e.expected_targets_season_to_date,
                    10
                )
            )
            OR NOT (
                ROUND(m.receptions_avg_last_3_games, 10)
                <=>
                ROUND(e.expected_receptions_avg_last_3, 10)
            )
            OR NOT (
                ROUND(m.receptions_avg_last_5_games, 10)
                <=>
                ROUND(e.expected_receptions_avg_last_5, 10)
            )
            OR NOT (
                ROUND(m.touches_avg_last_3_games, 10)
                <=>
                ROUND(e.expected_touches_avg_last_3, 10)
            )
            OR NOT (
                ROUND(m.touches_avg_last_5_games, 10)
                <=>
                ROUND(e.expected_touches_avg_last_5, 10)
            )
            OR NOT (
                ROUND(
                    m.opportunities_avg_last_3_games,
                    10
                )
                <=>
                ROUND(
                    e.expected_opportunities_avg_last_3,
                    10
                )
            )
            OR NOT (
                ROUND(
                    m.opportunities_avg_last_5_games,
                    10
                )
                <=>
                ROUND(
                    e.expected_opportunities_avg_last_5,
                    10
                )
            )
            OR NOT (
                ROUND(
                    m.opportunities_season_to_date,
                    10
                )
                <=>
                ROUND(
                    e.expected_opportunities_season_to_date,
                    10
                )
            )
        )
    ) AS rolling_volume_mismatch_rows,
    SUM(
        e.player_id IS NOT NULL
        AND (
            NOT (
                ROUND(
                    m.passing_yards_avg_last_3_games,
                    10
                )
                <=>
                ROUND(
                    e.expected_passing_yards_avg_last_3,
                    10
                )
            )
            OR NOT (
                ROUND(
                    m.rushing_yards_avg_last_3_games,
                    10
                )
                <=>
                ROUND(
                    e.expected_rushing_yards_avg_last_3,
                    10
                )
            )
            OR NOT (
                ROUND(
                    m.receiving_yards_avg_last_3_games,
                    10
                )
                <=>
                ROUND(
                    e.expected_receiving_yards_avg_last_3,
                    10
                )
            )
            OR NOT (
                ROUND(
                    m.yards_from_scrimmage_avg_last_3_games,
                    10
                )
                <=>
                ROUND(
                    e.expected_scrimmage_yards_avg_last_3,
                    10
                )
            )
            OR NOT (
                ROUND(
                    m.total_offensive_tds_avg_last_3_games,
                    10
                )
                <=>
                ROUND(
                    e.expected_offensive_tds_avg_last_3,
                    10
                )
            )
        )
    ) AS rolling_production_mismatch_rows,
    MAX(
        ABS(
            m.fantasy_points_ppr_avg_last_3_games
            - e.expected_ppr_avg_last_3
        )
    ) AS maximum_3_game_ppr_difference,
    CASE
        WHEN SUM(e.player_id IS NULL) = 0
            AND SUM(
                m.prior_games_count = 0
                AND (
                    m.fantasy_points_ppr_avg_last_3_games
                        IS NOT NULL
                    OR m.attempts_avg_last_3_games IS NOT NULL
                    OR m.carries_avg_last_3_games IS NOT NULL
                    OR m.targets_avg_last_3_games IS NOT NULL
                    OR m.opportunities_avg_last_3_games
                        IS NOT NULL
                )
            ) = 0
            AND SUM(
                e.player_id IS NOT NULL
                AND NOT (
                    ROUND(
                        m.fantasy_points_ppr_avg_last_3_games,
                        10
                    )
                    <=>
                    ROUND(e.expected_ppr_avg_last_3, 10)
                )
            ) = 0
            AND SUM(
                e.player_id IS NOT NULL
                AND NOT (
                    ROUND(
                        m.opportunities_avg_last_3_games,
                        10
                    )
                    <=>
                    ROUND(
                        e.expected_opportunities_avg_last_3,
                        10
                    )
                )
            ) = 0
            AND SUM(
                e.player_id IS NOT NULL
                AND NOT (
                    ROUND(
                        m.yards_from_scrimmage_avg_last_3_games,
                        10
                    )
                    <=>
                    ROUND(
                        e.expected_scrimmage_yards_avg_last_3,
                        10
                    )
                )
            ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM model_player_weeks AS m
LEFT JOIN expected_features AS e
    ON e.season = m.season
    AND e.week = m.week
    AND e.player_id = m.player_id;

-- ============================================================
-- 10. USAGE, SNAP, AND EFFICIENCY RECONCILIATION
--
-- Efficiency ratios are recomputed from rolling numerators and
-- denominators. Individual-game ratios are not averaged.
-- ============================================================

WITH rolling_inputs AS (
    SELECT
        h.season,
        h.week,
        h.player_id,
        AVG(h.target_share) OVER w_last_3
            AS expected_target_share_avg_last_3,
        AVG(h.target_share) OVER w_last_5
            AS expected_target_share_avg_last_5,
        AVG(h.target_share) OVER w_season
            AS expected_target_share_season_to_date,
        AVG(h.air_yards_share) OVER w_last_3
            AS expected_air_yards_share_avg_last_3,
        AVG(h.air_yards_share) OVER w_last_5
            AS expected_air_yards_share_avg_last_5,
        AVG(h.wopr) OVER w_last_3
            AS expected_wopr_avg_last_3,
        AVG(h.wopr) OVER w_last_5
            AS expected_wopr_avg_last_5,
        AVG(h.offense_snaps) OVER w_last_3
            AS expected_offense_snaps_avg_last_3,
        AVG(h.offense_snaps) OVER w_last_5
            AS expected_offense_snaps_avg_last_5,
        AVG(h.offense_pct) OVER w_last_3
            AS expected_offense_pct_avg_last_3,
        AVG(h.offense_pct) OVER w_last_5
            AS expected_offense_pct_avg_last_5,
        SUM(h.completions) OVER w_last_3
            AS completions_last_3,
        SUM(h.attempts) OVER w_last_3
            AS attempts_last_3,
        SUM(h.passing_yards) OVER w_last_3
            AS passing_yards_last_3,
        SUM(h.carries) OVER w_last_3
            AS carries_last_3,
        SUM(h.rushing_yards) OVER w_last_3
            AS rushing_yards_last_3,
        SUM(h.targets) OVER w_last_3
            AS targets_last_3,
        SUM(h.receptions) OVER w_last_3
            AS receptions_last_3,
        SUM(h.receiving_yards) OVER w_last_3
            AS receiving_yards_last_3,
        SUM(h.target_fantasy_points_ppr) OVER w_last_3
            AS fantasy_points_last_3,
        SUM(
            h.position_adjusted_opportunities
        ) OVER w_last_3
            AS opportunities_last_3,
        SUM(h.total_offensive_yards) OVER w_last_3
            AS total_offensive_yards_last_3
    FROM player_game_history AS h
    WINDOW
        w_last_3 AS (
            PARTITION BY h.player_id
            ORDER BY
                h.season,
                h.week,
                h.game_date,
                h.game_id
            ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
        ),
        w_last_5 AS (
            PARTITION BY h.player_id
            ORDER BY
                h.season,
                h.week,
                h.game_date,
                h.game_id
            ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
        ),
        w_season AS (
            PARTITION BY
                h.player_id,
                h.season
            ORDER BY
                h.week,
                h.game_date,
                h.game_id
            ROWS BETWEEN UNBOUNDED PRECEDING
                AND 1 PRECEDING
        )
),
expected_features AS (
    SELECT
        r.*,
        1E0 * r.completions_last_3
            / NULLIF(r.attempts_last_3, 0)
            AS expected_completion_pct,
        1E0 * r.passing_yards_last_3
            / NULLIF(r.attempts_last_3, 0)
            AS expected_passing_yards_per_attempt,
        1E0 * r.rushing_yards_last_3
            / NULLIF(r.carries_last_3, 0)
            AS expected_rushing_yards_per_carry,
        1E0 * r.receiving_yards_last_3
            / NULLIF(r.targets_last_3, 0)
            AS expected_receiving_yards_per_target,
        1E0 * r.receiving_yards_last_3
            / NULLIF(r.receptions_last_3, 0)
            AS expected_receiving_yards_per_reception,
        r.fantasy_points_last_3
            / NULLIF(r.opportunities_last_3, 0)
            AS expected_fantasy_points_per_opportunity,
        1E0 * r.total_offensive_yards_last_3
            / NULLIF(r.opportunities_last_3, 0)
            AS expected_total_yards_per_opportunity
    FROM rolling_inputs AS r
),
row_audit AS (
    SELECT
        m.season,
        m.week,
        m.player_id,
        CASE
            WHEN e.player_id IS NULL THEN 1
            ELSE 0
        END AS unmatched_expected_feature_row,
        CASE
            WHEN m.prior_games_count = 0
                AND (
                    m.target_share_avg_last_3_games
                        IS NOT NULL
                    OR m.air_yards_share_avg_last_3_games
                        IS NOT NULL
                    OR m.wopr_avg_last_3_games IS NOT NULL
                    OR m.offense_snaps_avg_last_3_games
                        IS NOT NULL
                    OR m.offense_pct_avg_last_3_games
                        IS NOT NULL
                    OR m.completion_pct_avg_last_3_games
                        IS NOT NULL
                    OR m.fantasy_points_per_opportunity_avg_last_3_games
                        IS NOT NULL
                )
            THEN 1
            ELSE 0
        END AS first_game_feature_leakage,
        CASE
            WHEN e.player_id IS NOT NULL
                AND (
                    NOT (
                        ROUND(
                            m.target_share_avg_last_3_games,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_target_share_avg_last_3,
                            10
                        )
                    )
                    OR NOT (
                        ROUND(
                            m.target_share_avg_last_5_games,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_target_share_avg_last_5,
                            10
                        )
                    )
                    OR NOT (
                        ROUND(
                            m.target_share_season_to_date,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_target_share_season_to_date,
                            10
                        )
                    )
                    OR NOT (
                        ROUND(
                            m.air_yards_share_avg_last_3_games,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_air_yards_share_avg_last_3,
                            10
                        )
                    )
                    OR NOT (
                        ROUND(
                            m.air_yards_share_avg_last_5_games,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_air_yards_share_avg_last_5,
                            10
                        )
                    )
                    OR NOT (
                        ROUND(m.wopr_avg_last_3_games, 10)
                        <=>
                        ROUND(e.expected_wopr_avg_last_3, 10)
                    )
                    OR NOT (
                        ROUND(m.wopr_avg_last_5_games, 10)
                        <=>
                        ROUND(e.expected_wopr_avg_last_5, 10)
                    )
                )
            THEN 1
            ELSE 0
        END AS usage_mismatch_row,
        CASE
            WHEN e.player_id IS NOT NULL
                AND (
                    NOT (
                        ROUND(
                            m.offense_snaps_avg_last_3_games,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_offense_snaps_avg_last_3,
                            10
                        )
                    )
                    OR NOT (
                        ROUND(
                            m.offense_snaps_avg_last_5_games,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_offense_snaps_avg_last_5,
                            10
                        )
                    )
                    OR NOT (
                        ROUND(
                            m.offense_pct_avg_last_3_games,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_offense_pct_avg_last_3,
                            10
                        )
                    )
                    OR NOT (
                        ROUND(
                            m.offense_pct_avg_last_5_games,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_offense_pct_avg_last_5,
                            10
                        )
                    )
                )
            THEN 1
            ELSE 0
        END AS snap_mismatch_row,
        CASE
            WHEN e.player_id IS NOT NULL
                AND (
                    NOT (
                        ROUND(
                            m.completion_pct_avg_last_3_games,
                            10
                        )
                        <=>
                        ROUND(e.expected_completion_pct, 10)
                    )
                    OR NOT (
                        ROUND(
                            m.passing_yards_per_attempt_avg_last_3_games,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_passing_yards_per_attempt,
                            10
                        )
                    )
                    OR NOT (
                        ROUND(
                            m.rushing_yards_per_carry_avg_last_3_games,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_rushing_yards_per_carry,
                            10
                        )
                    )
                    OR NOT (
                        ROUND(
                            m.receiving_yards_per_target_avg_last_3_games,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_receiving_yards_per_target,
                            10
                        )
                    )
                    OR NOT (
                        ROUND(
                            m.receiving_yards_per_reception_avg_last_3_games,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_receiving_yards_per_reception,
                            10
                        )
                    )
                    OR NOT (
                        ROUND(
                            m.fantasy_points_per_opportunity_avg_last_3_games,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_fantasy_points_per_opportunity,
                            10
                        )
                    )
                    OR NOT (
                        ROUND(
                            m.total_yards_per_opportunity_avg_last_3_games,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_total_yards_per_opportunity,
                            10
                        )
                    )
                )
            THEN 1
            ELSE 0
        END AS efficiency_mismatch_row,
        CASE
            WHEN e.player_id IS NOT NULL
                AND (
                    (
                        e.attempts_last_3 = 0
                        AND (
                            m.completion_pct_avg_last_3_games
                                IS NOT NULL
                            OR m.passing_yards_per_attempt_avg_last_3_games
                                IS NOT NULL
                        )
                    )
                    OR (
                        e.carries_last_3 = 0
                        AND m.rushing_yards_per_carry_avg_last_3_games
                            IS NOT NULL
                    )
                    OR (
                        e.targets_last_3 = 0
                        AND m.receiving_yards_per_target_avg_last_3_games
                            IS NOT NULL
                    )
                    OR (
                        e.receptions_last_3 = 0
                        AND m.receiving_yards_per_reception_avg_last_3_games
                            IS NOT NULL
                    )
                    OR (
                        e.opportunities_last_3 = 0
                        AND (
                            m.fantasy_points_per_opportunity_avg_last_3_games
                                IS NOT NULL
                            OR m.total_yards_per_opportunity_avg_last_3_games
                                IS NOT NULL
                        )
                    )
                )
            THEN 1
            ELSE 0
        END AS zero_denominator_published_row,
        CASE
            WHEN m.completion_pct_avg_last_3_games
                IS NOT NULL
                AND (
                    m.completion_pct_avg_last_3_games < 0
                    OR m.completion_pct_avg_last_3_games > 1
                )
            THEN 1
            ELSE 0
        END AS invalid_completion_pct_row,
        CASE
            WHEN m.fantasy_points_per_opportunity_avg_last_3_games
                    IS NOT NULL
                AND e.expected_fantasy_points_per_opportunity
                    IS NOT NULL
            THEN ABS(
                m.fantasy_points_per_opportunity_avg_last_3_games
                - e.expected_fantasy_points_per_opportunity
            )
        END AS fantasy_efficiency_difference
    FROM model_player_weeks AS m
    LEFT JOIN expected_features AS e
        ON e.season = m.season
        AND e.week = m.week
        AND e.player_id = m.player_id
),
audit_totals AS (
    SELECT
        COUNT(*) AS model_rows,
        SUM(unmatched_expected_feature_row)
            AS unmatched_expected_feature_rows,
        SUM(first_game_feature_leakage)
            AS first_game_rows_with_usage_or_efficiency_leakage,
        SUM(usage_mismatch_row)
            AS rolling_usage_mismatch_rows,
        SUM(snap_mismatch_row)
            AS rolling_snap_mismatch_rows,
        SUM(efficiency_mismatch_row)
            AS rolling_efficiency_mismatch_rows,
        SUM(zero_denominator_published_row)
            AS zero_denominator_published_rows,
        SUM(invalid_completion_pct_row)
            AS completion_pct_out_of_range_rows,
        MAX(fantasy_efficiency_difference)
            AS maximum_fantasy_efficiency_difference
    FROM row_audit
)
SELECT
    *,
    CASE
        WHEN unmatched_expected_feature_rows = 0
            AND first_game_rows_with_usage_or_efficiency_leakage = 0
            AND rolling_usage_mismatch_rows = 0
            AND rolling_snap_mismatch_rows = 0
            AND rolling_efficiency_mismatch_rows = 0
            AND zero_denominator_published_rows = 0
            AND completion_pct_out_of_range_rows = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM audit_totals;

-- ============================================================
-- 11. OPPONENT-STRENGTH WINDOW RECONCILIATION
-- ============================================================

WITH expected_opponent_features AS (
    SELECT
        o.season,
        o.week,
        o.game_id AS anchor_game_id,
        o.game_date AS anchor_game_date,
        o.defensive_team,
        o.position,
        LAG(o.game_id) OVER w_opponent
            AS previous_opponent_game_id,
        LAG(o.game_date) OVER w_opponent
            AS previous_opponent_game_date,
        LAG(o.fantasy_points_ppr_allowed)
            OVER w_opponent
            AS expected_ppr_prev_game,
        AVG(o.fantasy_points_ppr_allowed)
            OVER w_last_3
            AS expected_ppr_avg_last_3,
        AVG(o.fantasy_points_ppr_allowed)
            OVER w_last_5
            AS expected_ppr_avg_last_5,
        AVG(o.fantasy_points_ppr_allowed)
            OVER w_season
            AS expected_ppr_season_to_date,
        LAG(
            o.position_adjusted_opportunities_allowed
        ) OVER w_opponent
            AS expected_opportunities_prev_game,
        AVG(
            1E0
            * o.position_adjusted_opportunities_allowed
        ) OVER w_last_3
            AS expected_opportunities_avg_last_3,
        AVG(
            1E0
            * o.position_adjusted_opportunities_allowed
        ) OVER w_season
            AS expected_opportunities_season_to_date,
        AVG(
            1E0 * o.passing_yards_allowed
        ) OVER w_season
            AS expected_passing_yards_season_to_date,
        AVG(
            1E0 * o.rushing_yards_allowed
        ) OVER w_season
            AS expected_rushing_yards_season_to_date,
        AVG(
            1E0 * o.receiving_yards_allowed
        ) OVER w_season
            AS expected_receiving_yards_season_to_date,
        AVG(
            1E0 * o.total_offensive_tds_allowed
        ) OVER w_season
            AS expected_offensive_tds_season_to_date
    FROM opponent_position_week_history AS o
    WINDOW
        w_opponent AS (
            PARTITION BY
                o.defensive_team,
                o.position
            ORDER BY
                o.season,
                o.week,
                o.game_date,
                o.game_id
        ),
        w_last_3 AS (
            PARTITION BY
                o.defensive_team,
                o.position
            ORDER BY
                o.season,
                o.week,
                o.game_date,
                o.game_id
            ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
        ),
        w_last_5 AS (
            PARTITION BY
                o.defensive_team,
                o.position
            ORDER BY
                o.season,
                o.week,
                o.game_date,
                o.game_id
            ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
        ),
        w_season AS (
            PARTITION BY
                o.defensive_team,
                o.position,
                o.season
            ORDER BY
                o.week,
                o.game_date,
                o.game_id
            ROWS BETWEEN UNBOUNDED PRECEDING
                AND 1 PRECEDING
        )
),
row_audit AS (
    SELECT
        m.season,
        m.week,
        m.player_id,
        CASE
            WHEN e.defensive_team IS NULL THEN 1
            ELSE 0
        END AS unmatched_opponent_anchor,
        CASE
            WHEN e.defensive_team IS NOT NULL
                AND (
                    e.anchor_game_id <> m.game_id
                    OR e.anchor_game_date <> m.game_date
                )
            THEN 1
            ELSE 0
        END AS opponent_anchor_context_mismatch,
        CASE
            WHEN m.opponent_prior_position_games = 0
                AND (
                    m.opp_ppr_allowed_prev_game IS NOT NULL
                    OR m.opp_ppr_allowed_avg_last_3_games
                        IS NOT NULL
                    OR m.opp_ppr_allowed_avg_last_5_games
                        IS NOT NULL
                    OR m.opp_opportunities_allowed_prev_game
                        IS NOT NULL
                )
            THEN 1
            ELSE 0
        END AS first_opponent_history_leakage,
        CASE
            WHEN m.opponent_prior_position_games_current_season
                    = 0
                AND (
                    m.opp_ppr_allowed_season_to_date
                        IS NOT NULL
                    OR m.opp_opportunities_allowed_season_to_date
                        IS NOT NULL
                    OR m.opp_passing_yards_allowed_season_to_date
                        IS NOT NULL
                    OR m.opp_rushing_yards_allowed_season_to_date
                        IS NOT NULL
                    OR m.opp_receiving_yards_allowed_season_to_date
                        IS NOT NULL
                    OR m.opp_offensive_tds_allowed_season_to_date
                        IS NOT NULL
                )
            THEN 1
            ELSE 0
        END AS first_opponent_season_history_leakage,
        CASE
            WHEN e.previous_opponent_game_id = m.game_id
            THEN 1
            ELSE 0
        END AS target_game_used_as_previous_history,
        CASE
            WHEN e.previous_opponent_game_date IS NOT NULL
                AND e.previous_opponent_game_date
                    >= m.game_date
            THEN 1
            ELSE 0
        END AS nonprior_opponent_history,
        CASE
            WHEN e.defensive_team IS NOT NULL
                AND (
                    NOT (
                        ROUND(
                            m.opp_ppr_allowed_prev_game,
                            10
                        )
                        <=>
                        ROUND(e.expected_ppr_prev_game, 10)
                    )
                    OR NOT (
                        ROUND(
                            m.opp_ppr_allowed_avg_last_3_games,
                            10
                        )
                        <=>
                        ROUND(e.expected_ppr_avg_last_3, 10)
                    )
                    OR NOT (
                        ROUND(
                            m.opp_ppr_allowed_avg_last_5_games,
                            10
                        )
                        <=>
                        ROUND(e.expected_ppr_avg_last_5, 10)
                    )
                    OR NOT (
                        ROUND(
                            m.opp_ppr_allowed_season_to_date,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_ppr_season_to_date,
                            10
                        )
                    )
                )
            THEN 1
            ELSE 0
        END AS opponent_ppr_mismatch,
        CASE
            WHEN e.defensive_team IS NOT NULL
                AND (
                    NOT (
                        m.opp_opportunities_allowed_prev_game
                        <=>
                        e.expected_opportunities_prev_game
                    )
                    OR NOT (
                        ROUND(
                            m.opp_opportunities_allowed_avg_last_3_games,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_opportunities_avg_last_3,
                            10
                        )
                    )
                    OR NOT (
                        ROUND(
                            m.opp_opportunities_allowed_season_to_date,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_opportunities_season_to_date,
                            10
                        )
                    )
                )
            THEN 1
            ELSE 0
        END AS opponent_opportunity_mismatch,
        CASE
            WHEN e.defensive_team IS NOT NULL
                AND (
                    NOT (
                        ROUND(
                            m.opp_passing_yards_allowed_season_to_date,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_passing_yards_season_to_date,
                            10
                        )
                    )
                    OR NOT (
                        ROUND(
                            m.opp_rushing_yards_allowed_season_to_date,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_rushing_yards_season_to_date,
                            10
                        )
                    )
                    OR NOT (
                        ROUND(
                            m.opp_receiving_yards_allowed_season_to_date,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_receiving_yards_season_to_date,
                            10
                        )
                    )
                    OR NOT (
                        ROUND(
                            m.opp_offensive_tds_allowed_season_to_date,
                            10
                        )
                        <=>
                        ROUND(
                            e.expected_offensive_tds_season_to_date,
                            10
                        )
                    )
                )
            THEN 1
            ELSE 0
        END AS opponent_production_mismatch,
        CASE
            WHEN m.opp_ppr_allowed_prev_game IS NOT NULL
                AND e.expected_ppr_prev_game IS NOT NULL
            THEN ABS(
                m.opp_ppr_allowed_prev_game
                - e.expected_ppr_prev_game
            )
        END AS previous_opponent_ppr_difference
    FROM model_player_weeks AS m
    LEFT JOIN expected_opponent_features AS e
        ON e.season = m.season
        AND e.week = m.week
        AND e.defensive_team = m.opponent
        AND e.position = m.position
),
audit_totals AS (
    SELECT
        COUNT(*) AS model_rows,
        SUM(unmatched_opponent_anchor)
            AS unmatched_opponent_anchor_rows,
        SUM(opponent_anchor_context_mismatch)
            AS opponent_anchor_context_mismatch_rows,
        SUM(first_opponent_history_leakage)
            AS first_opponent_rows_with_feature_leakage,
        SUM(first_opponent_season_history_leakage)
            AS first_opponent_season_rows_with_feature_leakage,
        SUM(target_game_used_as_previous_history)
            AS rows_using_target_game_as_previous_history,
        SUM(nonprior_opponent_history)
            AS nonprior_opponent_history_rows,
        SUM(opponent_ppr_mismatch)
            AS opponent_ppr_mismatch_rows,
        SUM(opponent_opportunity_mismatch)
            AS opponent_opportunity_mismatch_rows,
        SUM(opponent_production_mismatch)
            AS opponent_production_mismatch_rows,
        MAX(previous_opponent_ppr_difference)
            AS maximum_previous_opponent_ppr_difference
    FROM row_audit
)
SELECT
    *,
    CASE
        WHEN unmatched_opponent_anchor_rows = 0
            AND opponent_anchor_context_mismatch_rows = 0
            AND first_opponent_rows_with_feature_leakage = 0
            AND first_opponent_season_rows_with_feature_leakage = 0
            AND rows_using_target_game_as_previous_history = 0
            AND nonprior_opponent_history_rows = 0
            AND opponent_ppr_mismatch_rows = 0
            AND opponent_opportunity_mismatch_rows = 0
            AND opponent_production_mismatch_rows = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM audit_totals;

-- ============================================================
-- 12. EXPECTED MISSINGNESS AND FEATURE COVERAGE
--
-- Rolling averages use partial prior windows, so last-three
-- and last-five averages become available after one earlier
-- game. The has_3_prior_games and has_5_prior_games flags
-- identify rows with complete windows.
-- ============================================================

SELECT
    COUNT(*) AS model_rows,
    SUM(
        (fantasy_points_ppr_prev_game IS NULL)
            <> (has_previous_game = 0)
    ) AS previous_ppr_null_rule_mismatch_rows,
    SUM(
        (fantasy_points_ppr_avg_last_3_games IS NULL)
            <> (has_previous_game = 0)
    ) AS three_game_ppr_null_rule_mismatch_rows,
    SUM(
        (fantasy_points_ppr_avg_last_5_games IS NULL)
            <> (has_previous_game = 0)
    ) AS five_game_ppr_null_rule_mismatch_rows,
    SUM(
        (fantasy_points_ppr_stddev_last_5_games IS NULL)
            <> (prior_games_count < 2)
    ) AS five_game_ppr_stddev_null_rule_mismatch_rows,
    SUM(
        (fantasy_points_ppr_season_to_date IS NULL)
            <> (prior_games_current_season = 0)
    ) AS season_ppr_null_rule_mismatch_rows,
    SUM(
        (
            fantasy_points_ppr_stddev_season_to_date
                IS NULL
        )
            <> (prior_games_current_season < 2)
    ) AS season_ppr_stddev_null_rule_mismatch_rows,
    SUM(
        (target_share_prev_game IS NULL)
            <> (has_previous_game = 0)
    ) AS previous_target_share_null_rule_mismatch_rows,
    SUM(
        (target_share_avg_last_3_games IS NULL)
            <> (has_previous_game = 0)
    ) AS rolling_target_share_null_rule_mismatch_rows,
    SUM(
        (offense_pct_prev_game IS NULL)
            <> (has_previous_snap_record = 0)
    ) AS previous_snap_null_rule_mismatch_rows,
    SUM(
        (opp_ppr_allowed_prev_game IS NULL)
            <> (has_opponent_history = 0)
    ) AS previous_opponent_ppr_null_rule_mismatch_rows,
    SUM(
        (opp_ppr_allowed_avg_last_3_games IS NULL)
            <> (has_opponent_history = 0)
    ) AS rolling_opponent_ppr_null_rule_mismatch_rows,
    SUM(
        (opp_ppr_allowed_season_to_date IS NULL)
            <> (
                opponent_prior_position_games_current_season
                    = 0
            )
    ) AS season_opponent_ppr_null_rule_mismatch_rows,
    CASE
        WHEN SUM(
                (fantasy_points_ppr_prev_game IS NULL)
                    <> (has_previous_game = 0)
            ) = 0
            AND SUM(
                (
                    fantasy_points_ppr_avg_last_3_games
                        IS NULL
                )
                    <> (has_previous_game = 0)
            ) = 0
            AND SUM(
                (
                    fantasy_points_ppr_avg_last_5_games
                        IS NULL
                )
                    <> (has_previous_game = 0)
            ) = 0
            AND SUM(
                (
                    fantasy_points_ppr_season_to_date
                        IS NULL
                )
                    <> (
                        prior_games_current_season = 0
                    )
            ) = 0
            AND SUM(
                (offense_pct_prev_game IS NULL)
                    <> (has_previous_snap_record = 0)
            ) = 0
            AND SUM(
                (opp_ppr_allowed_prev_game IS NULL)
                    <> (has_opponent_history = 0)
            ) = 0
            AND SUM(
                (
                    opp_ppr_allowed_season_to_date
                        IS NULL
                )
                    <> (
                        opponent_prior_position_games_current_season
                            = 0
                    )
            ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM model_player_weeks;

SELECT
    season,
    position,
    COUNT(*) AS model_rows,
    ROUND(
        100.0 * SUM(has_previous_game = 1)
            / COUNT(*),
        2
    ) AS previous_game_coverage_pct,
    ROUND(
        100.0 * SUM(has_3_prior_games = 1)
            / COUNT(*),
        2
    ) AS complete_3_game_history_pct,
    ROUND(
        100.0 * SUM(has_5_prior_games = 1)
            / COUNT(*),
        2
    ) AS complete_5_game_history_pct,
    ROUND(
        100.0 * SUM(
            offense_pct_prev_game IS NOT NULL
        ) / COUNT(*),
        2
    ) AS previous_snap_coverage_pct,
    ROUND(
        100.0 * SUM(
            fantasy_points_per_opportunity_avg_last_3_games
                IS NOT NULL
        ) / COUNT(*),
        2
    ) AS fantasy_efficiency_coverage_pct,
    ROUND(
        100.0 * SUM(has_opponent_history = 1)
            / COUNT(*),
        2
    ) AS previous_opponent_history_pct,
    ROUND(
        100.0 * SUM(
            opp_ppr_allowed_season_to_date IS NOT NULL
        ) / COUNT(*),
        2
    ) AS opponent_season_history_pct
FROM model_player_weeks
GROUP BY
    season,
    position
ORDER BY
    season,
    FIELD(position, 'QB', 'RB', 'WR', 'TE');

-- ============================================================
-- 13. RANGE, DOMAIN, AND FORBIDDEN-COLUMN VALIDATION
-- ============================================================

SELECT
    COUNT(*) AS model_rows,
    SUM(
        attempts_avg_last_3_games < 0
        OR attempts_avg_last_5_games < 0
        OR attempts_season_to_date < 0
        OR carries_avg_last_3_games < 0
        OR carries_avg_last_5_games < 0
        OR carries_season_to_date < 0
        OR targets_avg_last_3_games < 0
        OR targets_avg_last_5_games < 0
        OR targets_season_to_date < 0
        OR receptions_avg_last_3_games < 0
        OR receptions_avg_last_5_games < 0
        OR touches_avg_last_3_games < 0
        OR touches_avg_last_5_games < 0
        OR opportunities_avg_last_3_games < 0
        OR opportunities_avg_last_5_games < 0
        OR opportunities_season_to_date < 0
    ) AS negative_volume_feature_rows,
    SUM(
        offense_snaps_prev_game < 0
        OR offense_snaps_avg_last_3_games < 0
        OR offense_snaps_avg_last_5_games < 0
    ) AS negative_snap_feature_rows,
    SUM(
        (
            offense_pct_prev_game IS NOT NULL
            AND (
                offense_pct_prev_game < 0
                OR offense_pct_prev_game > 1
            )
        )
        OR (
            offense_pct_avg_last_3_games IS NOT NULL
            AND (
                offense_pct_avg_last_3_games < 0
                OR offense_pct_avg_last_3_games > 1
            )
        )
        OR (
            offense_pct_avg_last_5_games IS NOT NULL
            AND (
                offense_pct_avg_last_5_games < 0
                OR offense_pct_avg_last_5_games > 1
            )
        )
    ) AS snap_pct_out_of_range_rows,
    SUM(
        (
            target_share_prev_game IS NOT NULL
            AND (
                target_share_prev_game < 0
                OR target_share_prev_game > 1
            )
        )
        OR (
            target_share_avg_last_3_games IS NOT NULL
            AND (
                target_share_avg_last_3_games < 0
                OR target_share_avg_last_3_games > 1
            )
        )
        OR (
            target_share_avg_last_5_games IS NOT NULL
            AND (
                target_share_avg_last_5_games < 0
                OR target_share_avg_last_5_games > 1
            )
        )
        OR (
            target_share_season_to_date IS NOT NULL
            AND (
                target_share_season_to_date < 0
                OR target_share_season_to_date > 1
            )
        )
    ) AS target_share_out_of_range_rows,
    SUM(
        completion_pct_avg_last_3_games IS NOT NULL
        AND (
            completion_pct_avg_last_3_games < 0
            OR completion_pct_avg_last_3_games > 1
        )
    ) AS completion_pct_out_of_range_rows,
    SUM(
        snap_records_last_3_games
            > LEAST(prior_games_count, 3)
        OR snap_records_last_5_games
            > LEAST(prior_games_count, 5)
    ) AS impossible_snap_history_count_rows,
    SUM(
        days_since_previous_game IS NOT NULL
        AND days_since_previous_game <= 0
    ) AS invalid_days_since_previous_game_rows,
    SUM(
        team_rest IS NOT NULL
        AND team_rest < 0
    ) AS negative_team_rest_rows,
    SUM(
        opponent_rest IS NOT NULL
        AND opponent_rest < 0
    ) AS negative_opponent_rest_rows,
    SUM(
        source_spread_line IS NULL
        OR total_line IS NULL
        OR total_line <= 0
    ) AS invalid_or_missing_betting_context_rows,
    SUM(
        (game_location = 'HOME' AND is_home <> 1)
        OR (game_location = 'AWAY' AND is_home <> 0)
    ) AS home_location_consistency_rows,
    CASE
        WHEN SUM(
                attempts_avg_last_3_games < 0
                OR carries_avg_last_3_games < 0
                OR targets_avg_last_3_games < 0
                OR opportunities_avg_last_3_games < 0
            ) = 0
            AND SUM(
                offense_snaps_prev_game < 0
                OR offense_snaps_avg_last_3_games < 0
                OR offense_snaps_avg_last_5_games < 0
            ) = 0
            AND SUM(
                offense_pct_prev_game IS NOT NULL
                AND (
                    offense_pct_prev_game < 0
                    OR offense_pct_prev_game > 1
                )
            ) = 0
            AND SUM(
                target_share_prev_game IS NOT NULL
                AND (
                    target_share_prev_game < 0
                    OR target_share_prev_game > 1
                )
            ) = 0
            AND SUM(
                completion_pct_avg_last_3_games IS NOT NULL
                AND (
                    completion_pct_avg_last_3_games < 0
                    OR completion_pct_avg_last_3_games > 1
                )
            ) = 0
            AND SUM(
                snap_records_last_3_games
                    > LEAST(prior_games_count, 3)
                OR snap_records_last_5_games
                    > LEAST(prior_games_count, 5)
            ) = 0
            AND SUM(
                days_since_previous_game IS NOT NULL
                AND days_since_previous_game <= 0
            ) = 0
            AND SUM(
                source_spread_line IS NULL
                OR total_line IS NULL
                OR total_line <= 0
            ) = 0
            AND SUM(
                (game_location = 'HOME' AND is_home <> 1)
                OR (
                    game_location = 'AWAY'
                    AND is_home <> 0
                )
            ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM model_player_weeks;

WITH forbidden_columns AS (
    SELECT 'fantasy_points_ppr' AS column_name
    UNION ALL SELECT 'calculated_fantasy_points_ppr'
    UNION ALL SELECT 'fantasy_point_difference'
    UNION ALL SELECT 'completions'
    UNION ALL SELECT 'attempts'
    UNION ALL SELECT 'passing_yards'
    UNION ALL SELECT 'passing_tds'
    UNION ALL SELECT 'passing_interceptions'
    UNION ALL SELECT 'carries'
    UNION ALL SELECT 'rushing_yards'
    UNION ALL SELECT 'rushing_tds'
    UNION ALL SELECT 'receptions'
    UNION ALL SELECT 'targets'
    UNION ALL SELECT 'receiving_yards'
    UNION ALL SELECT 'receiving_tds'
    UNION ALL SELECT 'target_share'
    UNION ALL SELECT 'air_yards_share'
    UNION ALL SELECT 'wopr'
    UNION ALL SELECT 'offense_snaps'
    UNION ALL SELECT 'offense_pct'
    UNION ALL SELECT 'home_score'
    UNION ALL SELECT 'away_score'
    UNION ALL SELECT 'team_score'
    UNION ALL SELECT 'opponent_score'
    UNION ALL SELECT 'result'
    UNION ALL SELECT 'game_total'
    UNION ALL SELECT 'overtime'
    UNION ALL SELECT 'report_status'
    UNION ALL SELECT 'practice_status'
    UNION ALL SELECT 'depth_chart_position'
    UNION ALL SELECT 'depth_rank'
    UNION ALL SELECT 'pos_rank'
)
SELECT
    COUNT(c.column_name)
        AS forbidden_columns_present,
    COALESCE(
        GROUP_CONCAT(
            c.column_name
            ORDER BY c.column_name
            SEPARATOR ', '
        ),
        'None'
    ) AS forbidden_column_list,
    CASE
        WHEN COUNT(c.column_name) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM forbidden_columns AS f
LEFT JOIN information_schema.columns AS c
    ON c.table_schema = DATABASE()
    AND c.table_name = 'model_player_weeks'
    AND c.column_name = f.column_name;

-- ============================================================
-- 14. TARGET AND FEATURE DISTRIBUTION PROFILE
--
-- This profile compares training, validation, and test data.
-- Distribution differences are not automatically errors, but
-- material shifts must be understood before modeling.
-- ============================================================

WITH ranked_targets AS (
    SELECT
        m.*,
        ROW_NUMBER() OVER (
            PARTITION BY
                m.data_split,
                m.position
            ORDER BY
                m.target_fantasy_points_ppr,
                m.season,
                m.week,
                m.player_id
        ) AS target_rank,
        COUNT(*) OVER (
            PARTITION BY
                m.data_split,
                m.position
        ) AS partition_rows
    FROM model_player_weeks AS m
)
SELECT
    data_split,
    position,
    MIN(season) AS minimum_season,
    MAX(season) AS maximum_season,
    COUNT(*) AS model_rows,
    COUNT(DISTINCT player_id) AS distinct_players,
    ROUND(
        AVG(target_fantasy_points_ppr),
        2
    ) AS average_target_ppr,
    ROUND(
        AVG(
            CASE
                WHEN target_rank IN (
                    FLOOR((partition_rows + 1) / 2),
                    FLOOR((partition_rows + 2) / 2)
                )
                THEN target_fantasy_points_ppr
            END
        ),
        2
    ) AS median_target_ppr,
    ROUND(
        STDDEV_SAMP(target_fantasy_points_ppr),
        2
    ) AS target_ppr_stddev,
    MIN(target_fantasy_points_ppr)
        AS minimum_target_ppr,
    MAX(target_fantasy_points_ppr)
        AS maximum_target_ppr,
    ROUND(
        100.0 * SUM(
            target_fantasy_points_ppr = 0
        ) / COUNT(*),
        2
    ) AS zero_target_pct,
    ROUND(
        100.0 * SUM(
            target_fantasy_points_ppr < 0
        ) / COUNT(*),
        2
    ) AS negative_target_pct,
    ROUND(
        100.0 * SUM(
            fantasy_points_ppr_prev_game IS NOT NULL
        ) / COUNT(*),
        2
    ) AS previous_ppr_coverage_pct,
    ROUND(
        AVG(fantasy_points_ppr_prev_game),
        2
    ) AS average_previous_ppr,
    ROUND(
        AVG(opportunities_avg_last_3_games),
        2
    ) AS average_3_game_opportunities,
    ROUND(
        AVG(offense_pct_prev_game),
        4
    ) AS average_previous_snap_pct,
    ROUND(
        AVG(opp_ppr_allowed_season_to_date),
        2
    ) AS average_opponent_ppr_allowed
FROM ranked_targets
GROUP BY
    data_split,
    position
ORDER BY
    FIELD(
        data_split,
        'training',
        'validation',
        'test'
    ),
    FIELD(position, 'QB', 'RB', 'WR', 'TE');

-- ============================================================
-- 15. TEMPORAL BOUNDARY SPOT CHECKS
-- ============================================================

WITH team_schedule AS (
    SELECT
        tw.season,
        tw.week,
        tw.game_id,
        tw.game_date,
        tw.team,
        LAG(tw.game_date) OVER (
            PARTITION BY
                tw.season,
                tw.team
            ORDER BY
                tw.week,
                tw.game_date,
                tw.game_id
        ) AS previous_team_game_date
    FROM team_weeks AS tw
),
model_with_team_schedule AS (
    SELECT
        m.*,
        ts.previous_team_game_date,
        CASE
            WHEN ts.previous_team_game_date IS NOT NULL
            THEN DATEDIFF(
                m.game_date,
                ts.previous_team_game_date
            )
        END AS team_days_since_previous_game
    FROM model_player_weeks AS m
    LEFT JOIN team_schedule AS ts
        ON ts.season = m.season
        AND ts.week = m.week
        AND ts.team = m.team
),
boundary_candidates AS (
    SELECT
        '01_first_observed_game' AS boundary_case,
        b.season,
        b.week,
        b.game_id,
        b.game_date,
        b.player_id,
        b.player_display_name,
        b.position,
        b.team,
        b.opponent,
        b.data_split,
        b.prior_games_count,
        b.previous_game_season,
        b.previous_game_week,
        b.previous_game_date,
        b.previous_team,
        b.days_since_previous_game,
        b.team_changed_since_previous_game,
        b.has_previous_snap_record,
        b.fantasy_points_ppr_prev_game,
        b.fantasy_points_ppr_avg_last_3_games,
        b.fantasy_points_ppr_avg_last_5_games,
        b.offense_pct_prev_game,
        b.opp_ppr_allowed_prev_game,
        b.target_fantasy_points_ppr,
        b.previous_team_game_date,
        b.team_days_since_previous_game,
        ROW_NUMBER() OVER (
            ORDER BY
                b.season,
                b.week,
                b.player_id
        ) AS case_rank
    FROM model_with_team_schedule AS b
    WHERE b.prior_games_count = 0
    UNION ALL
    SELECT
        '02_at_least_five_prior_games',
        b.season,
        b.week,
        b.game_id,
        b.game_date,
        b.player_id,
        b.player_display_name,
        b.position,
        b.team,
        b.opponent,
        b.data_split,
        b.prior_games_count,
        b.previous_game_season,
        b.previous_game_week,
        b.previous_game_date,
        b.previous_team,
        b.days_since_previous_game,
        b.team_changed_since_previous_game,
        b.has_previous_snap_record,
        b.fantasy_points_ppr_prev_game,
        b.fantasy_points_ppr_avg_last_3_games,
        b.fantasy_points_ppr_avg_last_5_games,
        b.offense_pct_prev_game,
        b.opp_ppr_allowed_prev_game,
        b.target_fantasy_points_ppr,
        b.previous_team_game_date,
        b.team_days_since_previous_game,
        ROW_NUMBER() OVER (
            ORDER BY
                b.season,
                b.week,
                b.player_id
        )
    FROM model_with_team_schedule AS b
    WHERE b.has_5_prior_games = 1
    UNION ALL
    SELECT
        '03_week_after_team_bye',
        b.season,
        b.week,
        b.game_id,
        b.game_date,
        b.player_id,
        b.player_display_name,
        b.position,
        b.team,
        b.opponent,
        b.data_split,
        b.prior_games_count,
        b.previous_game_season,
        b.previous_game_week,
        b.previous_game_date,
        b.previous_team,
        b.days_since_previous_game,
        b.team_changed_since_previous_game,
        b.has_previous_snap_record,
        b.fantasy_points_ppr_prev_game,
        b.fantasy_points_ppr_avg_last_3_games,
        b.fantasy_points_ppr_avg_last_5_games,
        b.offense_pct_prev_game,
        b.opp_ppr_allowed_prev_game,
        b.target_fantasy_points_ppr,
        b.previous_team_game_date,
        b.team_days_since_previous_game,
        ROW_NUMBER() OVER (
            ORDER BY
                b.season,
                b.week,
                b.player_id
        )
    FROM model_with_team_schedule AS b
    WHERE b.team_days_since_previous_game
        BETWEEN 11 AND 20
    AND b.previous_game_date
        = b.previous_team_game_date
    UNION ALL
    SELECT
        '04_player_changed_teams',
        b.season,
        b.week,
        b.game_id,
        b.game_date,
        b.player_id,
        b.player_display_name,
        b.position,
        b.team,
        b.opponent,
        b.data_split,
        b.prior_games_count,
        b.previous_game_season,
        b.previous_game_week,
        b.previous_game_date,
        b.previous_team,
        b.days_since_previous_game,
        b.team_changed_since_previous_game,
        b.has_previous_snap_record,
        b.fantasy_points_ppr_prev_game,
        b.fantasy_points_ppr_avg_last_3_games,
        b.fantasy_points_ppr_avg_last_5_games,
        b.offense_pct_prev_game,
        b.opp_ppr_allowed_prev_game,
        b.target_fantasy_points_ppr,
        b.previous_team_game_date,
        b.team_days_since_previous_game,
        ROW_NUMBER() OVER (
            ORDER BY
                b.season,
                b.week,
                b.player_id
        )
    FROM model_with_team_schedule AS b
    WHERE b.team_changed_since_previous_game = 1
    UNION ALL
    SELECT
        '05_week_1_with_prior_season_history',
        b.season,
        b.week,
        b.game_id,
        b.game_date,
        b.player_id,
        b.player_display_name,
        b.position,
        b.team,
        b.opponent,
        b.data_split,
        b.prior_games_count,
        b.previous_game_season,
        b.previous_game_week,
        b.previous_game_date,
        b.previous_team,
        b.days_since_previous_game,
        b.team_changed_since_previous_game,
        b.has_previous_snap_record,
        b.fantasy_points_ppr_prev_game,
        b.fantasy_points_ppr_avg_last_3_games,
        b.fantasy_points_ppr_avg_last_5_games,
        b.offense_pct_prev_game,
        b.opp_ppr_allowed_prev_game,
        b.target_fantasy_points_ppr,
        b.previous_team_game_date,
        b.team_days_since_previous_game,
        ROW_NUMBER() OVER (
            ORDER BY
                b.season,
                b.week,
                b.player_id
        )
    FROM model_with_team_schedule AS b
    WHERE b.week = 1
    AND b.previous_game_season < b.season
    UNION ALL
    SELECT
        '06_validation_row',
        b.season,
        b.week,
        b.game_id,
        b.game_date,
        b.player_id,
        b.player_display_name,
        b.position,
        b.team,
        b.opponent,
        b.data_split,
        b.prior_games_count,
        b.previous_game_season,
        b.previous_game_week,
        b.previous_game_date,
        b.previous_team,
        b.days_since_previous_game,
        b.team_changed_since_previous_game,
        b.has_previous_snap_record,
        b.fantasy_points_ppr_prev_game,
        b.fantasy_points_ppr_avg_last_3_games,
        b.fantasy_points_ppr_avg_last_5_games,
        b.offense_pct_prev_game,
        b.opp_ppr_allowed_prev_game,
        b.target_fantasy_points_ppr,
        b.previous_team_game_date,
        b.team_days_since_previous_game,
        ROW_NUMBER() OVER (
            ORDER BY
                b.season,
                b.week,
                b.player_id
        )
    FROM model_with_team_schedule AS b
    WHERE b.data_split = 'validation'
    AND b.has_5_prior_games = 1
    UNION ALL
    SELECT
        '07_test_row',
        b.season,
        b.week,
        b.game_id,
        b.game_date,
        b.player_id,
        b.player_display_name,
        b.position,
        b.team,
        b.opponent,
        b.data_split,
        b.prior_games_count,
        b.previous_game_season,
        b.previous_game_week,
        b.previous_game_date,
        b.previous_team,
        b.days_since_previous_game,
        b.team_changed_since_previous_game,
        b.has_previous_snap_record,
        b.fantasy_points_ppr_prev_game,
        b.fantasy_points_ppr_avg_last_3_games,
        b.fantasy_points_ppr_avg_last_5_games,
        b.offense_pct_prev_game,
        b.opp_ppr_allowed_prev_game,
        b.target_fantasy_points_ppr,
        b.previous_team_game_date,
        b.team_days_since_previous_game,
        ROW_NUMBER() OVER (
            ORDER BY
                b.season,
                b.week,
                b.player_id
        )
    FROM model_with_team_schedule AS b
    WHERE b.data_split = 'test'
    AND b.has_5_prior_games = 1
    UNION ALL
    SELECT
        '08_missing_previous_snap',
        b.season,
        b.week,
        b.game_id,
        b.game_date,
        b.player_id,
        b.player_display_name,
        b.position,
        b.team,
        b.opponent,
        b.data_split,
        b.prior_games_count,
        b.previous_game_season,
        b.previous_game_week,
        b.previous_game_date,
        b.previous_team,
        b.days_since_previous_game,
        b.team_changed_since_previous_game,
        b.has_previous_snap_record,
        b.fantasy_points_ppr_prev_game,
        b.fantasy_points_ppr_avg_last_3_games,
        b.fantasy_points_ppr_avg_last_5_games,
        b.offense_pct_prev_game,
        b.opp_ppr_allowed_prev_game,
        b.target_fantasy_points_ppr,
        b.previous_team_game_date,
        b.team_days_since_previous_game,
        ROW_NUMBER() OVER (
            ORDER BY
                b.season,
                b.week,
                b.player_id
        )
    FROM model_with_team_schedule AS b
    WHERE b.has_previous_game = 1
    AND b.has_previous_snap_record = 0
)
SELECT
    COUNT(*) OVER ()
        AS returned_boundary_cases,
    boundary_case,
    season,
    week,
    game_date,
    player_display_name,
    position,
    team,
    opponent,
    data_split,
    prior_games_count,
    previous_game_season,
    previous_game_week,
    previous_game_date,
    previous_team,
    days_since_previous_game,
    team_changed_since_previous_game,
    has_previous_snap_record,
    fantasy_points_ppr_prev_game,
    fantasy_points_ppr_avg_last_3_games,
    fantasy_points_ppr_avg_last_5_games,
    offense_pct_prev_game,
    opp_ppr_allowed_prev_game,
    target_fantasy_points_ppr,
    previous_team_game_date,
    team_days_since_previous_game,
    CASE boundary_case
        WHEN '01_first_observed_game'
        THEN CASE
            WHEN prior_games_count = 0
                AND previous_game_date IS NULL
                AND fantasy_points_ppr_prev_game IS NULL
            THEN 'PASS'
            ELSE 'FAIL'
        END
        WHEN '02_at_least_five_prior_games'
        THEN CASE
            WHEN prior_games_count >= 5
                AND fantasy_points_ppr_avg_last_5_games
                    IS NOT NULL
            THEN 'PASS'
            ELSE 'FAIL'
        END
        WHEN '03_week_after_team_bye'
        THEN CASE
            WHEN team_days_since_previous_game
                    BETWEEN 11 AND 20
                AND previous_game_date
                    = previous_team_game_date
            THEN 'PASS'
            ELSE 'FAIL'
        END
        WHEN '04_player_changed_teams'
        THEN CASE
            WHEN team_changed_since_previous_game = 1
                AND previous_team <> team
            THEN 'PASS'
            ELSE 'FAIL'
        END
        WHEN '05_week_1_with_prior_season_history'
        THEN CASE
            WHEN week = 1
                AND previous_game_season < season
                AND previous_game_date < game_date
            THEN 'PASS'
            ELSE 'FAIL'
        END
        WHEN '06_validation_row'
        THEN CASE
            WHEN data_split = 'validation'
                AND season = 2024
                AND prior_games_count >= 5
            THEN 'PASS'
            ELSE 'FAIL'
        END
        WHEN '07_test_row'
        THEN CASE
            WHEN data_split = 'test'
                AND season = 2025
                AND prior_games_count >= 5
            THEN 'PASS'
            ELSE 'FAIL'
        END
        WHEN '08_missing_previous_snap'
        THEN CASE
            WHEN has_previous_snap_record = 0
                AND fantasy_points_ppr_prev_game IS NOT NULL
                AND offense_pct_prev_game IS NULL
            THEN 'PASS'
            ELSE 'FAIL'
        END
    END AS boundary_validation_status
FROM boundary_candidates
WHERE case_rank = 1
ORDER BY
    boundary_case;

-- ============================================================
-- 16. FINAL MODEL-EXPORT READINESS SUMMARY
--
-- This consolidates the blocking controls from the detailed
-- validation sections above. A READY result means the feature
-- table is ready for export and baseline modeling, not that a
-- trained model is ready for production use.
-- ============================================================

WITH validation_configuration AS (
    SELECT
        45693 AS expected_model_rows,
        116 AS expected_model_columns
),
source_metrics AS (
    SELECT
        COUNT(*) AS source_player_week_rows
    FROM player_weeks
),
core_metrics AS (
    SELECT
        COUNT(*) AS model_rows,
        COUNT(
            DISTINCT CONCAT_WS(
                '|',
                season,
                week,
                player_id
            )
        ) AS distinct_model_keys,
        SUM(
            CASE
                WHEN season IS NULL
                    OR week IS NULL
                    OR NULLIF(TRIM(player_id), '') IS NULL
                    OR NULLIF(TRIM(player_display_name), '') IS NULL
                    OR NULLIF(TRIM(game_id), '') IS NULL
                    OR game_date IS NULL
                    OR NULLIF(TRIM(team), '') IS NULL
                    OR NULLIF(TRIM(opponent), '') IS NULL
                    OR NULLIF(TRIM(position), '') IS NULL
                    OR target_fantasy_points_ppr IS NULL
                    OR NULLIF(TRIM(data_split), '') IS NULL
                    OR NULLIF(TRIM(feature_version), '') IS NULL
                    OR is_first_observed_game IS NULL
                    OR is_first_observed_game_of_season IS NULL
                    OR has_previous_game IS NULL
                    OR has_3_prior_games IS NULL
                    OR has_5_prior_games IS NULL
                    OR has_previous_snap_record IS NULL
                    OR has_opponent_history IS NULL
                THEN 1
                ELSE 0
            END
        ) AS missing_required_rows,
        SUM(
            CASE
                WHEN season NOT BETWEEN 2018 AND 2025
                    OR week NOT BETWEEN 1 AND 18
                    OR position NOT IN ('QB', 'RB', 'WR', 'TE')
                    OR game_location NOT IN ('HOME', 'AWAY')
                    OR is_home NOT IN (0, 1)
                    OR feature_version <> 'v1_prior_game'
                    OR data_split <> CASE
                        WHEN season BETWEEN 2018 AND 2023
                            THEN 'training'
                        WHEN season = 2024
                            THEN 'validation'
                        WHEN season = 2025
                            THEN 'test'
                    END
                THEN 1
                ELSE 0
            END
        ) AS invalid_domain_rows,
        SUM(
            CASE
                WHEN prior_games_count < 0
                    OR prior_games_current_season < 0
                    OR prior_games_current_season
                        > prior_games_count
                    OR opponent_prior_position_games < 0
                    OR opponent_prior_position_games_current_season
                        < 0
                    OR opponent_prior_position_games_current_season
                        > opponent_prior_position_games
                    OR snap_records_last_3_games < 0
                    OR snap_records_last_5_games < 0
                    OR is_first_observed_game
                        <> (prior_games_count = 0)
                    OR is_first_observed_game_of_season
                        <> (prior_games_current_season = 0)
                    OR has_previous_game
                        <> (prior_games_count >= 1)
                    OR has_3_prior_games
                        <> (prior_games_count >= 3)
                    OR has_5_prior_games
                        <> (prior_games_count >= 5)
                    OR has_opponent_history
                        <> (
                            opponent_prior_position_games >= 1
                        )
                    OR (
                        previous_game_date IS NOT NULL
                        AND previous_game_date >= game_date
                    )
                    OR (
                        previous_game_season = season
                        AND previous_game_week >= week
                    )
                    OR (
                        previous_game_date IS NULL
                        AND days_since_previous_game IS NOT NULL
                    )
                    OR (
                        previous_game_date IS NOT NULL
                        AND days_since_previous_game
                            <> DATEDIFF(
                                game_date,
                                previous_game_date
                            )
                    )
                    OR (
                        has_previous_snap_record = 1
                        AND offense_pct_prev_game IS NULL
                    )
                    OR (
                        has_previous_snap_record = 0
                        AND offense_pct_prev_game IS NOT NULL
                    )
                THEN 1
                ELSE 0
            END
        ) AS history_integrity_failure_rows,
        SUM(
            CASE
                WHEN (
                    prior_games_count = 0
                    AND (
                        fantasy_points_ppr_prev_game IS NOT NULL
                        OR fantasy_points_ppr_avg_last_3_games
                            IS NOT NULL
                        OR fantasy_points_ppr_avg_last_5_games
                            IS NOT NULL
                        OR attempts_prev_game IS NOT NULL
                        OR carries_prev_game IS NOT NULL
                        OR targets_prev_game IS NOT NULL
                        OR opportunities_prev_game IS NOT NULL
                        OR target_share_prev_game IS NOT NULL
                        OR offense_pct_prev_game IS NOT NULL
                        OR completion_pct_avg_last_3_games
                            IS NOT NULL
                        OR fantasy_points_per_opportunity_avg_last_3_games
                            IS NOT NULL
                    )
                )
                OR (
                    prior_games_current_season = 0
                    AND (
                        fantasy_points_ppr_season_to_date
                            IS NOT NULL
                        OR attempts_season_to_date IS NOT NULL
                        OR carries_season_to_date IS NOT NULL
                        OR targets_season_to_date IS NOT NULL
                        OR opportunities_season_to_date
                            IS NOT NULL
                        OR target_share_season_to_date
                            IS NOT NULL
                    )
                )
                THEN 1
                ELSE 0
            END
        ) AS player_feature_leakage_rows,
        SUM(
            CASE
                WHEN (
                    opponent_prior_position_games = 0
                    AND (
                        opp_ppr_allowed_prev_game IS NOT NULL
                        OR opp_ppr_allowed_avg_last_3_games
                            IS NOT NULL
                        OR opp_ppr_allowed_avg_last_5_games
                            IS NOT NULL
                        OR opp_opportunities_allowed_prev_game
                            IS NOT NULL
                    )
                )
                OR (
                    opponent_prior_position_games_current_season
                        = 0
                    AND (
                        opp_ppr_allowed_season_to_date
                            IS NOT NULL
                        OR opp_opportunities_allowed_season_to_date
                            IS NOT NULL
                        OR opp_passing_yards_allowed_season_to_date
                            IS NOT NULL
                        OR opp_rushing_yards_allowed_season_to_date
                            IS NOT NULL
                        OR opp_receiving_yards_allowed_season_to_date
                            IS NOT NULL
                        OR opp_offensive_tds_allowed_season_to_date
                            IS NOT NULL
                    )
                )
                THEN 1
                ELSE 0
            END
        ) AS opponent_feature_leakage_rows,
        SUM(
            CASE
                WHEN attempts_avg_last_3_games < 0
                    OR carries_avg_last_3_games < 0
                    OR targets_avg_last_3_games < 0
                    OR opportunities_avg_last_3_games < 0
                    OR offense_snaps_prev_game < 0
                    OR offense_snaps_avg_last_3_games < 0
                    OR offense_snaps_avg_last_5_games < 0
                    OR (
                        offense_pct_prev_game IS NOT NULL
                        AND offense_pct_prev_game NOT BETWEEN 0 AND 1
                    )
                    OR (
                        target_share_prev_game IS NOT NULL
                        AND target_share_prev_game NOT BETWEEN 0 AND 1
                    )
                    OR (
                        completion_pct_avg_last_3_games
                            IS NOT NULL
                        AND completion_pct_avg_last_3_games
                            NOT BETWEEN 0 AND 1
                    )
                    OR snap_records_last_3_games
                        > LEAST(prior_games_count, 3)
                    OR snap_records_last_5_games
                        > LEAST(prior_games_count, 5)
                    OR (
                        days_since_previous_game IS NOT NULL
                        AND days_since_previous_game <= 0
                    )
                    OR team_rest < 0
                    OR opponent_rest < 0
                    OR source_spread_line IS NULL
                    OR total_line IS NULL
                    OR total_line <= 0
                    OR (
                        game_location = 'HOME'
                        AND is_home <> 1
                    )
                    OR (
                        game_location = 'AWAY'
                        AND is_home <> 0
                    )
                THEN 1
                ELSE 0
            END
        ) AS invalid_range_or_context_rows
    FROM model_player_weeks
),
model_to_source AS (
    SELECT
        SUM(
            CASE
                WHEN pw.player_id IS NULL
                THEN 1
                ELSE 0
            END
        ) AS model_rows_without_source,
        SUM(
            CASE
                WHEN pw.player_id IS NOT NULL
                    AND ABS(
                        m.target_fantasy_points_ppr
                        - pw.fantasy_points_ppr
                    ) > 0.0000000001
                THEN 1
                ELSE 0
            END
        ) AS target_mismatch_rows
    FROM model_player_weeks AS m
    LEFT JOIN player_weeks AS pw
        ON pw.season = m.season
        AND pw.week = m.week
        AND pw.player_id = m.player_id
),
source_to_model AS (
    SELECT
        SUM(
            CASE
                WHEN m.player_id IS NULL
                THEN 1
                ELSE 0
            END
        ) AS source_rows_missing_from_model
    FROM player_weeks AS pw
    LEFT JOIN model_player_weeks AS m
        ON m.season = pw.season
        AND m.week = pw.week
        AND m.player_id = pw.player_id
),
schema_metrics AS (
    SELECT
        COUNT(*) AS model_column_count
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
    AND table_name = 'model_player_weeks'
),
forbidden_columns AS (
    SELECT 'fantasy_points_ppr' AS column_name
    UNION ALL SELECT 'calculated_fantasy_points_ppr'
    UNION ALL SELECT 'fantasy_point_difference'
    UNION ALL SELECT 'completions'
    UNION ALL SELECT 'attempts'
    UNION ALL SELECT 'passing_yards'
    UNION ALL SELECT 'passing_tds'
    UNION ALL SELECT 'passing_interceptions'
    UNION ALL SELECT 'carries'
    UNION ALL SELECT 'rushing_yards'
    UNION ALL SELECT 'rushing_tds'
    UNION ALL SELECT 'receptions'
    UNION ALL SELECT 'targets'
    UNION ALL SELECT 'receiving_yards'
    UNION ALL SELECT 'receiving_tds'
    UNION ALL SELECT 'target_share'
    UNION ALL SELECT 'air_yards_share'
    UNION ALL SELECT 'wopr'
    UNION ALL SELECT 'offense_snaps'
    UNION ALL SELECT 'offense_pct'
    UNION ALL SELECT 'home_score'
    UNION ALL SELECT 'away_score'
    UNION ALL SELECT 'team_score'
    UNION ALL SELECT 'opponent_score'
    UNION ALL SELECT 'result'
    UNION ALL SELECT 'game_total'
    UNION ALL SELECT 'overtime'
    UNION ALL SELECT 'report_status'
    UNION ALL SELECT 'practice_status'
    UNION ALL SELECT 'depth_chart_position'
    UNION ALL SELECT 'depth_rank'
    UNION ALL SELECT 'pos_rank'
),
forbidden_metrics AS (
    SELECT
        COUNT(c.column_name) AS forbidden_columns_present
    FROM forbidden_columns AS f
    LEFT JOIN information_schema.columns AS c
        ON c.table_schema = DATABASE()
        AND c.table_name = 'model_player_weeks'
        AND c.column_name = f.column_name
)
SELECT
    cfg.expected_model_rows,
    src.source_player_week_rows,
    core.model_rows,
    core.distinct_model_keys,
    cfg.expected_model_columns,
    sch.model_column_count,
    mts.model_rows_without_source,
    stm.source_rows_missing_from_model,
    mts.target_mismatch_rows,
    core.missing_required_rows,
    core.invalid_domain_rows,
    core.history_integrity_failure_rows,
    core.player_feature_leakage_rows,
    core.opponent_feature_leakage_rows,
    core.invalid_range_or_context_rows,
    forb.forbidden_columns_present,
    7 AS documented_caveat_count,
    CASE
        WHEN src.source_player_week_rows
                = cfg.expected_model_rows
            AND core.model_rows
                = cfg.expected_model_rows
            AND core.distinct_model_keys
                = cfg.expected_model_rows
            AND sch.model_column_count
                = cfg.expected_model_columns
            AND mts.model_rows_without_source = 0
            AND stm.source_rows_missing_from_model = 0
            AND mts.target_mismatch_rows = 0
            AND core.missing_required_rows = 0
            AND core.invalid_domain_rows = 0
            AND core.history_integrity_failure_rows = 0
            AND core.player_feature_leakage_rows = 0
            AND core.opponent_feature_leakage_rows = 0
            AND core.invalid_range_or_context_rows = 0
            AND forb.forbidden_columns_present = 0
        THEN 'READY_FOR_MODEL_EXPORT'
        ELSE 'NOT_READY_FOR_MODEL_EXPORT'
    END AS model_export_readiness
FROM validation_configuration AS cfg
CROSS JOIN source_metrics AS src
CROSS JOIN core_metrics AS core
CROSS JOIN model_to_source AS mts
CROSS JOIN source_to_model AS stm
CROSS JOIN schema_metrics AS sch
CROSS JOIN forbidden_metrics AS forb;

-- Documented modeling caveats:
-- 1. The population contains players appearing in weekly statistics;
--    a separate future-week candidate-generation process is required.
-- 2. The target, identifiers, data_split, feature_version, and audit
--    timestamps must be excluded from the predictor matrix.
-- 3. Current-week injury and depth-chart features remain excluded
--    until their prediction-time availability can be guaranteed.
-- 4. Missing historical snap records remain NULL and are represented
--    by explicit availability flags.
-- 5. The 2018 season has lower historical-feature coverage because
--    no pre-2018 player history is included.
-- 6. The 2025 WR target and opportunity distributions shifted lower
--    than training and require explicit test-set evaluation.
-- 7. Model results will be predictive associations, not causal claims.