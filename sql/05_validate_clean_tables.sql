USE nfl_fantasy_advisor;

-- ============================================================
-- CLEAN ANALYTICAL LAYER VALIDATION
--
-- This script is read-only. It validates the tables created by
-- sql/04_create_clean_tables.sql without modifying any data.
-- ============================================================

-- ============================================================
-- 1. ACTIVE DATABASE
--
-- Expected: nfl_fantasy_advisor
-- ============================================================

SELECT
    DATABASE() AS active_database;

-- ============================================================
-- 2. CLEAN TABLE ROW-COUNT RECONCILIATION
--
-- Expected: all ten tables return PASS.
-- ============================================================

WITH expected_counts AS (
    SELECT
        1 AS sort_order,
        'games' AS table_name,
        2127 AS expected_rows
    UNION ALL
    SELECT
        2,
        'team_weeks',
        4254
    UNION ALL
    SELECT
        3,
        'player_weeks',
        45693
    UNION ALL
    SELECT
        4,
        'roster_player_weeks',
        362828
    UNION ALL
    SELECT
        5,
        'players',
        7920
    UNION ALL
    SELECT
        6,
        'player_week_id_crosswalk',
        352455
    UNION ALL
    SELECT
        7,
        'injury_player_weeks',
        43561
    UNION ALL
    SELECT
        8,
        'snap_player_weeks',
        196130
    UNION ALL
    SELECT
        9,
        'depth_chart_legacy_weeks',
        242058
    UNION ALL
    SELECT
        10,
        'depth_chart_snapshots',
        548638
),
actual_counts AS (
    SELECT
        'games' AS table_name,
        COUNT(*) AS actual_rows
    FROM games
    UNION ALL
    SELECT
        'team_weeks',
        COUNT(*)
    FROM team_weeks
    UNION ALL
    SELECT
        'player_weeks',
        COUNT(*)
    FROM player_weeks
    UNION ALL
    SELECT
        'roster_player_weeks',
        COUNT(*)
    FROM roster_player_weeks
    UNION ALL
    SELECT
        'players',
        COUNT(*)
    FROM players
    UNION ALL
    SELECT
        'player_week_id_crosswalk',
        COUNT(*)
    FROM player_week_id_crosswalk
    UNION ALL
    SELECT
        'injury_player_weeks',
        COUNT(*)
    FROM injury_player_weeks
    UNION ALL
    SELECT
        'snap_player_weeks',
        COUNT(*)
    FROM snap_player_weeks
    UNION ALL
    SELECT
        'depth_chart_legacy_weeks',
        COUNT(*)
    FROM depth_chart_legacy_weeks
    UNION ALL
    SELECT
        'depth_chart_snapshots',
        COUNT(*)
    FROM depth_chart_snapshots
)
SELECT
    e.table_name,
    e.expected_rows,
    a.actual_rows,
    a.actual_rows - e.expected_rows AS row_difference,
    CASE
        WHEN a.actual_rows = e.expected_rows THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM expected_counts AS e
JOIN actual_counts AS a
    ON a.table_name = e.table_name
ORDER BY e.sort_order;

-- ============================================================
-- 3. INTENDED-GRAIN UNIQUENESS
--
-- Expected: duplicate_key_groups = 0 and PASS for every table.
-- Primary and unique keys enforce these rules, while this query
-- preserves inspectable evidence of the result.
-- ============================================================

SELECT
    'games' AS table_name,
    'game_id' AS intended_key,
    (
        SELECT COUNT(*)
        FROM (
            SELECT game_id
            FROM games
            GROUP BY game_id
            HAVING COUNT(*) > 1
        ) AS duplicate_groups
    ) AS duplicate_key_groups,
    CASE
        WHEN (
            SELECT COUNT(*)
            FROM (
                SELECT game_id
                FROM games
                GROUP BY game_id
                HAVING COUNT(*) > 1
            ) AS duplicate_groups
        ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
UNION ALL
SELECT
    'team_weeks',
    'season, week, team',
    (
        SELECT COUNT(*)
        FROM (
            SELECT
                season,
                week,
                team
            FROM team_weeks
            GROUP BY
                season,
                week,
                team
            HAVING COUNT(*) > 1
        ) AS duplicate_groups
    ),
    CASE
        WHEN (
            SELECT COUNT(*)
            FROM (
                SELECT
                    season,
                    week,
                    team
                FROM team_weeks
                GROUP BY
                    season,
                    week,
                    team
                HAVING COUNT(*) > 1
            ) AS duplicate_groups
        ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END
UNION ALL
SELECT
    'player_weeks',
    'season, week, player_id',
    (
        SELECT COUNT(*)
        FROM (
            SELECT
                season,
                week,
                player_id
            FROM player_weeks
            GROUP BY
                season,
                week,
                player_id
            HAVING COUNT(*) > 1
        ) AS duplicate_groups
    ),
    CASE
        WHEN (
            SELECT COUNT(*)
            FROM (
                SELECT
                    season,
                    week,
                    player_id
                FROM player_weeks
                GROUP BY
                    season,
                    week,
                    player_id
                HAVING COUNT(*) > 1
            ) AS duplicate_groups
        ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END
UNION ALL
SELECT
    'roster_player_weeks',
    'season, week, team, player_id',
    (
        SELECT COUNT(*)
        FROM (
            SELECT
                season,
                week,
                team,
                player_id
            FROM roster_player_weeks
            GROUP BY
                season,
                week,
                team,
                player_id
            HAVING COUNT(*) > 1
        ) AS duplicate_groups
    ),
    CASE
        WHEN (
            SELECT COUNT(*)
            FROM (
                SELECT
                    season,
                    week,
                    team,
                    player_id
                FROM roster_player_weeks
                GROUP BY
                    season,
                    week,
                    team,
                    player_id
                HAVING COUNT(*) > 1
            ) AS duplicate_groups
        ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END
UNION ALL
SELECT
    'players',
    'player_id',
    (
        SELECT COUNT(*)
        FROM (
            SELECT player_id
            FROM players
            GROUP BY player_id
            HAVING COUNT(*) > 1
        ) AS duplicate_groups
    ),
    CASE
        WHEN (
            SELECT COUNT(*)
            FROM (
                SELECT player_id
                FROM players
                GROUP BY player_id
                HAVING COUNT(*) > 1
            ) AS duplicate_groups
        ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END
UNION ALL
SELECT
    'player_week_id_crosswalk',
    'season, week, team, player_id',
    (
        SELECT COUNT(*)
        FROM (
            SELECT
                season,
                week,
                team,
                player_id
            FROM player_week_id_crosswalk
            GROUP BY
                season,
                week,
                team,
                player_id
            HAVING COUNT(*) > 1
        ) AS duplicate_groups
    ),
    CASE
        WHEN (
            SELECT COUNT(*)
            FROM (
                SELECT
                    season,
                    week,
                    team,
                    player_id
                FROM player_week_id_crosswalk
                GROUP BY
                    season,
                    week,
                    team,
                    player_id
                HAVING COUNT(*) > 1
            ) AS duplicate_groups
        ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END
UNION ALL
SELECT
    'injury_player_weeks',
    'season, week, team, player_id',
    (
        SELECT COUNT(*)
        FROM (
            SELECT
                season,
                week,
                team,
                player_id
            FROM injury_player_weeks
            GROUP BY
                season,
                week,
                team,
                player_id
            HAVING COUNT(*) > 1
        ) AS duplicate_groups
    ),
    CASE
        WHEN (
            SELECT COUNT(*)
            FROM (
                SELECT
                    season,
                    week,
                    team,
                    player_id
                FROM injury_player_weeks
                GROUP BY
                    season,
                    week,
                    team,
                    player_id
                HAVING COUNT(*) > 1
            ) AS duplicate_groups
        ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END
UNION ALL
SELECT
    'snap_player_weeks',
    'season, week, team, pfr_player_id',
    (
        SELECT COUNT(*)
        FROM (
            SELECT
                season,
                week,
                team,
                pfr_player_id
            FROM snap_player_weeks
            GROUP BY
                season,
                week,
                team,
                pfr_player_id
            HAVING COUNT(*) > 1
        ) AS duplicate_groups
    ),
    CASE
        WHEN (
            SELECT COUNT(*)
            FROM (
                SELECT
                    season,
                    week,
                    team,
                    pfr_player_id
                FROM snap_player_weeks
                GROUP BY
                    season,
                    week,
                    team,
                    pfr_player_id
                HAVING COUNT(*) > 1
            ) AS duplicate_groups
        ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END
UNION ALL
SELECT
    'depth_chart_legacy_weeks',
    'season, week, team, player_id, position, rank',
    (
        SELECT COUNT(*)
        FROM (
            SELECT
                season,
                week,
                team,
                player_id,
                pos_grp,
                pos_abb,
                pos_rank
            FROM depth_chart_legacy_weeks
            GROUP BY
                season,
                week,
                team,
                player_id,
                pos_grp,
                pos_abb,
                pos_rank
            HAVING COUNT(*) > 1
        ) AS duplicate_groups
    ),
    CASE
        WHEN (
            SELECT COUNT(*)
            FROM (
                SELECT
                    season,
                    week,
                    team,
                    player_id,
                    pos_grp,
                    pos_abb,
                    pos_rank
                FROM depth_chart_legacy_weeks
                GROUP BY
                    season,
                    week,
                    team,
                    player_id,
                    pos_grp,
                    pos_abb,
                    pos_rank
                HAVING COUNT(*) > 1
            ) AS duplicate_groups
        ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END
UNION ALL
SELECT
    'depth_chart_snapshots',
    'timestamp, team, player_id, position, slot',
    (
        SELECT COUNT(*)
        FROM (
            SELECT
                snapshot_at_utc,
                team,
                player_id,
                pos_abb,
                pos_slot
            FROM depth_chart_snapshots
            GROUP BY
                snapshot_at_utc,
                team,
                player_id,
                pos_abb,
                pos_slot
            HAVING COUNT(*) > 1
        ) AS duplicate_groups
    ),
    CASE
        WHEN (
            SELECT COUNT(*)
            FROM (
                SELECT
                    snapshot_at_utc,
                    team,
                    player_id,
                    pos_abb,
                    pos_slot
                FROM depth_chart_snapshots
                GROUP BY
                    snapshot_at_utc,
                    team,
                    player_id,
                    pos_abb,
                    pos_slot
                HAVING COUNT(*) > 1
            ) AS duplicate_groups
        ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END;

-- ============================================================
-- 4. REQUIRED-KEY COMPLETENESS
--
-- Expected: unavailable_required_key_rows = 0 and PASS for all.
-- ============================================================

SELECT
    'games' AS table_name,
    COUNT(*) AS total_rows,
    SUM(
        CASE
            WHEN game_id IS NULL
            OR TRIM(game_id) = ''
            OR season IS NULL
            OR week IS NULL
            OR game_date IS NULL
            OR away_team IS NULL
            OR TRIM(away_team) = ''
            OR home_team IS NULL
            OR TRIM(home_team) = ''
            THEN 1
            ELSE 0
        END
    ) AS unavailable_required_key_rows,
    CASE
        WHEN SUM(
            CASE
                WHEN game_id IS NULL
                OR TRIM(game_id) = ''
                OR season IS NULL
                OR week IS NULL
                OR game_date IS NULL
                OR away_team IS NULL
                OR TRIM(away_team) = ''
                OR home_team IS NULL
                OR TRIM(home_team) = ''
                THEN 1
                ELSE 0
            END
        ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM games
UNION ALL
SELECT
    'team_weeks',
    COUNT(*),
    SUM(
        CASE
            WHEN season IS NULL
            OR week IS NULL
            OR team IS NULL
            OR TRIM(team) = ''
            OR game_id IS NULL
            OR TRIM(game_id) = ''
            OR opponent IS NULL
            OR TRIM(opponent) = ''
            THEN 1
            ELSE 0
        END
    ),
    CASE
        WHEN SUM(
            CASE
                WHEN season IS NULL
                OR week IS NULL
                OR team IS NULL
                OR TRIM(team) = ''
                OR game_id IS NULL
                OR TRIM(game_id) = ''
                OR opponent IS NULL
                OR TRIM(opponent) = ''
                THEN 1
                ELSE 0
            END
        ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END
FROM team_weeks
UNION ALL
SELECT
    'player_weeks',
    COUNT(*),
    SUM(
        CASE
            WHEN season IS NULL
            OR week IS NULL
            OR player_id IS NULL
            OR TRIM(player_id) = ''
            OR game_id IS NULL
            OR TRIM(game_id) = ''
            OR team IS NULL
            OR TRIM(team) = ''
            OR opponent_team IS NULL
            OR TRIM(opponent_team) = ''
            OR position IS NULL
            OR TRIM(position) = ''
            THEN 1
            ELSE 0
        END
    ),
    CASE
        WHEN SUM(
            CASE
                WHEN season IS NULL
                OR week IS NULL
                OR player_id IS NULL
                OR TRIM(player_id) = ''
                OR game_id IS NULL
                OR TRIM(game_id) = ''
                OR team IS NULL
                OR TRIM(team) = ''
                OR opponent_team IS NULL
                OR TRIM(opponent_team) = ''
                OR position IS NULL
                OR TRIM(position) = ''
                THEN 1
                ELSE 0
            END
        ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END
FROM player_weeks
UNION ALL
SELECT
    'roster_player_weeks',
    COUNT(*),
    SUM(
        CASE
            WHEN season IS NULL
            OR week IS NULL
            OR team IS NULL
            OR TRIM(team) = ''
            OR player_id IS NULL
            OR TRIM(player_id) = ''
            THEN 1
            ELSE 0
        END
    ),
    CASE
        WHEN SUM(
            CASE
                WHEN season IS NULL
                OR week IS NULL
                OR team IS NULL
                OR TRIM(team) = ''
                OR player_id IS NULL
                OR TRIM(player_id) = ''
                THEN 1
                ELSE 0
            END
        ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END
FROM roster_player_weeks
UNION ALL
SELECT
    'players',
    COUNT(*),
    SUM(
        CASE
            WHEN player_id IS NULL
            OR TRIM(player_id) = ''
            THEN 1
            ELSE 0
        END
    ),
    CASE
        WHEN SUM(
            CASE
                WHEN player_id IS NULL
                OR TRIM(player_id) = ''
                THEN 1
                ELSE 0
            END
        ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END
FROM players
UNION ALL
SELECT
    'player_week_id_crosswalk',
    COUNT(*),
    SUM(
        CASE
            WHEN season IS NULL
            OR week IS NULL
            OR team IS NULL
            OR TRIM(team) = ''
            OR player_id IS NULL
            OR TRIM(player_id) = ''
            OR pfr_player_id IS NULL
            OR TRIM(pfr_player_id) = ''
            THEN 1
            ELSE 0
        END
    ),
    CASE
        WHEN SUM(
            CASE
                WHEN season IS NULL
                OR week IS NULL
                OR team IS NULL
                OR TRIM(team) = ''
                OR player_id IS NULL
                OR TRIM(player_id) = ''
                OR pfr_player_id IS NULL
                OR TRIM(pfr_player_id) = ''
                THEN 1
                ELSE 0
            END
        ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END
FROM player_week_id_crosswalk
UNION ALL
SELECT
    'injury_player_weeks',
    COUNT(*),
    SUM(
        CASE
            WHEN season IS NULL
            OR week IS NULL
            OR team IS NULL
            OR TRIM(team) = ''
            OR player_id IS NULL
            OR TRIM(player_id) = ''
            THEN 1
            ELSE 0
        END
    ),
    CASE
        WHEN SUM(
            CASE
                WHEN season IS NULL
                OR week IS NULL
                OR team IS NULL
                OR TRIM(team) = ''
                OR player_id IS NULL
                OR TRIM(player_id) = ''
                THEN 1
                ELSE 0
            END
        ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END
FROM injury_player_weeks
UNION ALL
SELECT
    'snap_player_weeks',
    COUNT(*),
    SUM(
        CASE
            WHEN season IS NULL
            OR week IS NULL
            OR team IS NULL
            OR TRIM(team) = ''
            OR game_id IS NULL
            OR TRIM(game_id) = ''
            OR pfr_player_id IS NULL
            OR TRIM(pfr_player_id) = ''
            THEN 1
            ELSE 0
        END
    ),
    CASE
        WHEN SUM(
            CASE
                WHEN season IS NULL
                OR week IS NULL
                OR team IS NULL
                OR TRIM(team) = ''
                OR game_id IS NULL
                OR TRIM(game_id) = ''
                OR pfr_player_id IS NULL
                OR TRIM(pfr_player_id) = ''
                THEN 1
                ELSE 0
            END
        ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END
FROM snap_player_weeks
UNION ALL
SELECT
    'depth_chart_legacy_weeks',
    COUNT(*),
    SUM(
        CASE
            WHEN season IS NULL
            OR week IS NULL
            OR team IS NULL
            OR TRIM(team) = ''
            OR player_id IS NULL
            OR TRIM(player_id) = ''
            OR pos_grp IS NULL
            OR TRIM(pos_grp) = ''
            OR pos_abb IS NULL
            OR TRIM(pos_abb) = ''
            OR pos_rank IS NULL
            THEN 1
            ELSE 0
        END
    ),
    CASE
        WHEN SUM(
            CASE
                WHEN season IS NULL
                OR week IS NULL
                OR team IS NULL
                OR TRIM(team) = ''
                OR player_id IS NULL
                OR TRIM(player_id) = ''
                OR pos_grp IS NULL
                OR TRIM(pos_grp) = ''
                OR pos_abb IS NULL
                OR TRIM(pos_abb) = ''
                OR pos_rank IS NULL
                THEN 1
                ELSE 0
            END
        ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END
FROM depth_chart_legacy_weeks
UNION ALL
SELECT
    'depth_chart_snapshots',
    COUNT(*),
    SUM(
        CASE
            WHEN source_season IS NULL
            OR snapshot_text IS NULL
            OR TRIM(snapshot_text) = ''
            OR snapshot_at_utc IS NULL
            OR team IS NULL
            OR TRIM(team) = ''
            OR player_id IS NULL
            OR TRIM(player_id) = ''
            OR pos_abb IS NULL
            OR TRIM(pos_abb) = ''
            OR pos_slot IS NULL
            THEN 1
            ELSE 0
        END
    ),
    CASE
        WHEN SUM(
            CASE
                WHEN source_season IS NULL
                OR snapshot_text IS NULL
                OR TRIM(snapshot_text) = ''
                OR snapshot_at_utc IS NULL
                OR team IS NULL
                OR TRIM(team) = ''
                OR player_id IS NULL
                OR TRIM(player_id) = ''
                OR pos_abb IS NULL
                OR TRIM(pos_abb) = ''
                OR pos_slot IS NULL
                THEN 1
                ELSE 0
            END
        ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END
FROM depth_chart_snapshots;

-- ============================================================
-- 5. DOMAIN AND CROSS-FIELD VALIDITY
--
-- Expected: invalid_rows = 0 and PASS for every table.
--
-- Snap percentages allow values through 1.01 because the source
-- contains a small rounding effect in special-teams percentages.
-- ============================================================

WITH domain_checks AS (
    SELECT
        'games' AS table_name,
        COUNT(*) AS invalid_rows
    FROM games
    WHERE game_type <> 'REG'
        OR week NOT BETWEEN 1 AND 18
        OR away_team = home_team
        OR away_score IS NULL
        OR home_score IS NULL
        OR away_score < 0
        OR home_score < 0
    UNION ALL
    SELECT
        'team_weeks',
        COUNT(*)
    FROM team_weeks
    WHERE week NOT BETWEEN 1 AND 18
        OR team = opponent
        OR game_location NOT IN ('HOME', 'AWAY')
        OR is_home NOT IN (0, 1)
        OR (
            game_location = 'HOME'
            AND is_home <> 1
        )
        OR (
            game_location = 'AWAY'
            AND is_home <> 0
        )
        OR points_for IS NULL
        OR points_against IS NULL
        OR points_for < 0
        OR points_against < 0
    UNION ALL
    SELECT
        'player_weeks',
        COUNT(*)
    FROM player_weeks
    WHERE week NOT BETWEEN 1 AND 18
        OR season_type <> 'REG'
        OR position NOT IN ('QB', 'RB', 'WR', 'TE')
        OR team = opponent_team
        OR fantasy_points_ppr IS NULL
        OR calculated_fantasy_points_ppr IS NULL
        OR fantasy_point_difference IS NULL
    UNION ALL
    SELECT
        'roster_player_weeks',
        COUNT(*)
    FROM roster_player_weeks
    WHERE week NOT BETWEEN 1 AND 18
        OR game_type <> 'REG'
        OR pfr_id_conflict NOT IN (0, 1)
        OR pfr_id_available NOT IN (0, 1)
        OR (
            pfr_id_available = 1
            AND (
                pfr_player_id IS NULL
                OR TRIM(pfr_player_id) = ''
            )
        )
        OR (
            pfr_id_available = 0
            AND pfr_player_id IS NOT NULL
        )
    UNION ALL
    SELECT
        'players',
        COUNT(*)
    FROM players
    WHERE latest_roster_week NOT BETWEEN 1 AND 18
        OR pfr_id_conflict NOT IN (0, 1)
    UNION ALL
    SELECT
        'player_week_id_crosswalk',
        COUNT(*)
    FROM player_week_id_crosswalk
    WHERE week NOT BETWEEN 1 AND 18
        OR pfr_id_conflict NOT IN (0, 1)
    UNION ALL
    SELECT
        'injury_player_weeks',
        COUNT(*)
    FROM injury_player_weeks
    WHERE week NOT BETWEEN 1 AND 18
        OR game_type <> 'REG'
        OR has_final_report_status NOT IN (0, 1)
        OR has_practice_status NOT IN (0, 1)
        OR has_update_timestamp NOT IN (0, 1)
        OR (
            has_final_report_status = 1
            AND (
                report_status IS NULL
                OR TRIM(report_status) = ''
            )
        )
        OR (
            has_final_report_status = 0
            AND report_status IS NOT NULL
        )
        OR (
            has_practice_status = 1
            AND (
                practice_status IS NULL
                OR TRIM(practice_status) = ''
            )
        )
        OR (
            has_practice_status = 0
            AND practice_status IS NOT NULL
        )
        OR (
            has_update_timestamp = 1
            AND date_modified_utc IS NULL
        )
        OR (
            has_update_timestamp = 0
            AND date_modified_utc IS NOT NULL
        )
    UNION ALL
    SELECT
        'snap_player_weeks',
        COUNT(*)
    FROM snap_player_weeks
    WHERE week NOT BETWEEN 1 AND 18
        OR game_type <> 'REG'
        OR team = opponent
        OR player_id_match_status NOT IN (
            'matched',
            'unmatched'
        )
        OR (
            player_id_match_status = 'matched'
            AND player_id IS NULL
        )
        OR (
            player_id_match_status = 'unmatched'
            AND player_id IS NOT NULL
        )
        OR offense_snaps < 0
        OR defense_snaps < 0
        OR st_snaps < 0
        OR offense_pct < 0
        OR offense_pct > 1.01
        OR defense_pct < 0
        OR defense_pct > 1.01
        OR st_pct < 0
        OR st_pct > 1.01
    UNION ALL
    SELECT
        'depth_chart_legacy_weeks',
        COUNT(*)
    FROM depth_chart_legacy_weeks
    WHERE week NOT BETWEEN 1 AND 19
        OR game_type <> 'REG'
        OR pos_rank < 1
    UNION ALL
    SELECT
        'depth_chart_snapshots',
        COUNT(*)
    FROM depth_chart_snapshots
    WHERE source_season <> 2025
        OR pos_slot < 1
        OR pos_rank < 1
)
SELECT
    table_name,
    invalid_rows,
    CASE
        WHEN invalid_rows = 0 THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM domain_checks
ORDER BY table_name;

-- ============================================================
-- 6. CHRONOLOGICAL DATA-SPLIT CONSISTENCY
--
-- Expected mapping:
-- 2018-2023 = training
-- 2024      = validation
-- 2025      = test
--
-- Expected: split_mismatch_rows = 0 and PASS for every table.
-- ============================================================

WITH split_checks AS (
    SELECT
        'games' AS table_name,
        COUNT(*) AS split_mismatch_rows
    FROM games
    WHERE data_split <>
        CASE
            WHEN season BETWEEN 2018 AND 2023
                THEN 'training'
            WHEN season = 2024
                THEN 'validation'
            WHEN season = 2025
                THEN 'test'
            ELSE 'unexpected'
        END
    UNION ALL
    SELECT
        'team_weeks',
        COUNT(*)
    FROM team_weeks
    WHERE data_split <>
        CASE
            WHEN season BETWEEN 2018 AND 2023
                THEN 'training'
            WHEN season = 2024
                THEN 'validation'
            WHEN season = 2025
                THEN 'test'
            ELSE 'unexpected'
        END
    UNION ALL
    SELECT
        'player_weeks',
        COUNT(*)
    FROM player_weeks
    WHERE data_split <>
        CASE
            WHEN season BETWEEN 2018 AND 2023
                THEN 'training'
            WHEN season = 2024
                THEN 'validation'
            WHEN season = 2025
                THEN 'test'
            ELSE 'unexpected'
        END
    UNION ALL
    SELECT
        'roster_player_weeks',
        COUNT(*)
    FROM roster_player_weeks
    WHERE data_split <>
        CASE
            WHEN season BETWEEN 2018 AND 2023
                THEN 'training'
            WHEN season = 2024
                THEN 'validation'
            WHEN season = 2025
                THEN 'test'
            ELSE 'unexpected'
        END
    UNION ALL
    SELECT
        'players',
        COUNT(*)
    FROM players
    WHERE identity_data_split <>
        CASE
            WHEN latest_roster_season
                BETWEEN 2018 AND 2023
                THEN 'training'
            WHEN latest_roster_season = 2024
                THEN 'validation'
            WHEN latest_roster_season = 2025
                THEN 'test'
            ELSE 'unexpected'
        END
    UNION ALL
    SELECT
        'player_week_id_crosswalk',
        COUNT(*)
    FROM player_week_id_crosswalk
    WHERE data_split <>
        CASE
            WHEN season BETWEEN 2018 AND 2023
                THEN 'training'
            WHEN season = 2024
                THEN 'validation'
            WHEN season = 2025
                THEN 'test'
            ELSE 'unexpected'
        END
    UNION ALL
    SELECT
        'injury_player_weeks',
        COUNT(*)
    FROM injury_player_weeks
    WHERE data_split <>
        CASE
            WHEN season BETWEEN 2018 AND 2023
                THEN 'training'
            WHEN season = 2024
                THEN 'validation'
            WHEN season = 2025
                THEN 'test'
            ELSE 'unexpected'
        END
    UNION ALL
    SELECT
        'snap_player_weeks',
        COUNT(*)
    FROM snap_player_weeks
    WHERE data_split <>
        CASE
            WHEN season BETWEEN 2018 AND 2023
                THEN 'training'
            WHEN season = 2024
                THEN 'validation'
            WHEN season = 2025
                THEN 'test'
            ELSE 'unexpected'
        END
    UNION ALL
    SELECT
        'depth_chart_legacy_weeks',
        COUNT(*)
    FROM depth_chart_legacy_weeks
    WHERE data_split <>
        CASE
            WHEN season BETWEEN 2018 AND 2023
                THEN 'training'
            WHEN season = 2024
                THEN 'validation'
            WHEN season = 2025
                THEN 'test'
            ELSE 'unexpected'
        END
    UNION ALL
    SELECT
        'depth_chart_snapshots',
        COUNT(*)
    FROM depth_chart_snapshots
    WHERE data_split <>
        CASE
            WHEN source_season BETWEEN 2018 AND 2023
                THEN 'training'
            WHEN source_season = 2024
                THEN 'validation'
            WHEN source_season = 2025
                THEN 'test'
            ELSE 'unexpected'
        END
)
SELECT
    table_name,
    split_mismatch_rows,
    CASE
        WHEN split_mismatch_rows = 0 THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM split_checks
ORDER BY table_name;

-- ============================================================
-- 7. CONFIGURED FULL-PPR RECONCILIATION
--
-- Expected:
-- player_week_rows            = 45,693
-- missing_ppr_rows            = 0
-- ppr_mismatch_rows           = 0
-- maximum_absolute_difference = 0
-- validation_status           = PASS
-- ============================================================

SELECT
    COUNT(*) AS player_week_rows,
    SUM(
        CASE
            WHEN fantasy_points_ppr IS NULL
            THEN 1
            ELSE 0
        END
    ) AS missing_ppr_rows,
    SUM(
        CASE
            WHEN ABS(fantasy_point_difference) > 0.01
            THEN 1
            ELSE 0
        END
    ) AS ppr_mismatch_rows,
    MAX(
        ABS(fantasy_point_difference)
    ) AS maximum_absolute_difference,
    CASE
        WHEN COUNT(*) = 45693
        AND SUM(
                CASE
                    WHEN fantasy_points_ppr IS NULL
                    THEN 1
                    ELSE 0
                END
            ) = 0
        AND SUM(
                CASE
                    WHEN ABS(
                        fantasy_point_difference
                    ) > 0.01
                    THEN 1
                    ELSE 0
                END
            ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM player_weeks;

-- ============================================================
-- 8. GAME AND SCHEDULE CONSISTENCY
--
-- Expected: affected_rows = 0 and PASS for every check.
-- ============================================================

WITH schedule_checks AS (
    SELECT
        'game total equals combined score'
            AS check_name,
        COUNT(*) AS affected_rows
    FROM games
    WHERE total <> home_score + away_score
    UNION ALL
    SELECT
        'game result equals home margin',
        COUNT(*)
    FROM games
    WHERE result <> home_score - away_score
    UNION ALL
    SELECT
        'each game has exactly two team rows',
        COUNT(*)
    FROM (
        SELECT game_id
        FROM team_weeks
        GROUP BY game_id
        HAVING COUNT(*) <> 2
    ) AS invalid_games
    UNION ALL
    SELECT
        'team rows have a parent game',
        COUNT(*)
    FROM team_weeks AS tw
    LEFT JOIN games AS g
        ON g.game_id = tw.game_id
    WHERE g.game_id IS NULL
    UNION ALL
    SELECT
        'team rows have reciprocal opponents',
        COUNT(*)
    FROM team_weeks AS tw
    LEFT JOIN team_weeks AS opponent_row
        ON opponent_row.game_id = tw.game_id
        AND opponent_row.team = tw.opponent
        AND opponent_row.opponent = tw.team
    WHERE opponent_row.team IS NULL
    UNION ALL
    SELECT
        'player rows have a parent game',
        COUNT(*)
    FROM player_weeks AS pw
    LEFT JOIN games AS g
        ON g.game_id = pw.game_id
    WHERE g.game_id IS NULL
    UNION ALL
    SELECT
        'player rows have a team-week',
        COUNT(*)
    FROM player_weeks AS pw
    LEFT JOIN team_weeks AS tw
        ON tw.season = pw.season
        AND tw.week = pw.week
        AND tw.team = pw.team
    WHERE tw.team IS NULL
    UNION ALL
    SELECT
        'player opponent agrees with schedule',
        COUNT(*)
    FROM player_weeks AS pw
    JOIN team_weeks AS tw
        ON tw.season = pw.season
        AND tw.week = pw.week
        AND tw.team = pw.team
    WHERE pw.game_id <> tw.game_id
        OR pw.opponent_team <> tw.opponent
    UNION ALL
    SELECT
        'snap rows have a team-week',
        COUNT(*)
    FROM snap_player_weeks AS spw
    LEFT JOIN team_weeks AS tw
        ON tw.season = spw.season
        AND tw.week = spw.week
        AND tw.team = spw.team
    WHERE tw.team IS NULL
    UNION ALL
    SELECT
        'snap opponent agrees with schedule',
        COUNT(*)
    FROM snap_player_weeks AS spw
    JOIN team_weeks AS tw
        ON tw.season = spw.season
        AND tw.week = spw.week
        AND tw.team = spw.team
    WHERE spw.game_id <> tw.game_id
        OR spw.opponent <> tw.opponent
)
SELECT
    check_name,
    affected_rows,
    CASE
        WHEN affected_rows = 0 THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM schedule_checks
ORDER BY check_name;

-- ============================================================
-- 9. PLAYER IDENTITY AND CROSSWALK INTEGRITY
--
-- Expected: affected_rows = 0 and PASS for every check.
-- ============================================================

WITH identity_integrity_checks AS (
    SELECT
        'player rows have a player dimension record'
            AS check_name,
        COUNT(*) AS affected_rows
    FROM player_weeks AS pw
    LEFT JOIN players AS p
        ON p.player_id = pw.player_id
    WHERE p.player_id IS NULL
    UNION ALL
    SELECT
        'player rows have a same-team weekly roster record',
        COUNT(*)
    FROM player_weeks AS pw
    LEFT JOIN roster_player_weeks AS rpw
        ON rpw.season = pw.season
        AND rpw.week = pw.week
        AND rpw.team = pw.team
        AND rpw.player_id = pw.player_id
    WHERE rpw.player_id IS NULL
    UNION ALL
    SELECT
        'crosswalk rows have a weekly roster record',
        COUNT(*)
    FROM player_week_id_crosswalk AS x
    LEFT JOIN roster_player_weeks AS rpw
        ON rpw.season = x.season
        AND rpw.week = x.week
        AND rpw.team = x.team
        AND rpw.player_id = x.player_id
    WHERE rpw.player_id IS NULL
    UNION ALL
    SELECT
        'crosswalk rows have a player dimension record',
        COUNT(*)
    FROM player_week_id_crosswalk AS x
    LEFT JOIN players AS p
        ON p.player_id = x.player_id
    WHERE p.player_id IS NULL
    UNION ALL
    SELECT
        'PFR IDs map to one player per team-week',
        COUNT(*)
    FROM (
        SELECT
            season,
            week,
            team,
            pfr_player_id
        FROM player_week_id_crosswalk
        GROUP BY
            season,
            week,
            team,
            pfr_player_id
        HAVING COUNT(DISTINCT player_id) > 1
    ) AS conflicting_pfr_mappings
    UNION ALL
    SELECT
        'dimension PFR IDs map to one GSIS player',
        COUNT(*)
    FROM (
        SELECT pfr_player_id
        FROM players
        WHERE pfr_player_id IS NOT NULL
        GROUP BY pfr_player_id
        HAVING COUNT(DISTINCT player_id) > 1
    ) AS repeated_dimension_pfr_ids
    UNION ALL
    SELECT
        'player dimension records have full names',
        COUNT(*)
    FROM players
    WHERE full_name IS NULL
        OR TRIM(full_name) = ''
)
SELECT
    check_name,
    affected_rows,
    CASE
        WHEN affected_rows = 0 THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM identity_integrity_checks
ORDER BY check_name;

-- ============================================================
-- 10. EXPECTED PLAYER-IDENTITY CONDITIONS
--
-- These are documented source conditions, not failed keys.
--
-- Expected:
-- multi-team player-week groups = 13
-- flagged PFR-conflict rows     = 68
-- players without PFR ID        = 1,250
-- ============================================================

WITH expected_identity_conditions AS (
    SELECT
        'multi-team roster player-week groups'
            AS condition_name,
        13 AS expected_count,
        (
            SELECT COUNT(*)
            FROM (
                SELECT
                    season,
                    week,
                    player_id
                FROM roster_player_weeks
                GROUP BY
                    season,
                    week,
                    player_id
                HAVING COUNT(DISTINCT team) > 1
            ) AS multi_team_groups
        ) AS actual_count
    UNION ALL
    SELECT
        'weekly roster rows flagged for PFR conflict',
        68,
        (
            SELECT COUNT(*)
            FROM roster_player_weeks
            WHERE pfr_id_conflict = 1
        )
    UNION ALL
    SELECT
        'player dimension rows without a PFR ID',
        1250,
        (
            SELECT COUNT(*)
            FROM players
            WHERE pfr_player_id IS NULL
                OR TRIM(pfr_player_id) = ''
        )
)
SELECT
    condition_name,
    expected_count,
    actual_count,
    actual_count - expected_count AS count_difference,
    CASE
        WHEN actual_count = expected_count THEN 'EXPECTED'
        ELSE 'REVIEW'
    END AS assessment
FROM expected_identity_conditions
ORDER BY condition_name;

-- ============================================================
-- 11. SNAP-COUNT PLAYER-ID COVERAGE
--
-- Expected:
-- total rows       = 196,130
-- matched rows     = 195,781
-- unmatched rows   = 349
-- match percentage = 99.82
-- ============================================================

SELECT
    COUNT(*) AS total_snap_rows,
    SUM(
        CASE
            WHEN player_id_match_status = 'matched'
            THEN 1
            ELSE 0
        END
    ) AS matched_player_rows,
    SUM(
        CASE
            WHEN player_id_match_status = 'unmatched'
            THEN 1
            ELSE 0
        END
    ) AS unmatched_player_rows,
    ROUND(
        100.0
        * SUM(
            CASE
                WHEN player_id_match_status = 'matched'
                THEN 1
                ELSE 0
            END
        )
        / NULLIF(COUNT(*), 0),
        2
    ) AS player_match_pct,
    CASE
        WHEN COUNT(*) = 196130
        AND SUM(
                CASE
                    WHEN player_id_match_status = 'matched'
                    THEN 1
                    ELSE 0
                END
            ) = 195781
        AND SUM(
                CASE
                    WHEN player_id_match_status = 'unmatched'
                    THEN 1
                    ELSE 0
                END
            ) = 349
        THEN 'PASS'
        ELSE 'REVIEW'
    END AS validation_status
FROM snap_player_weeks;

-- ============================================================
-- 12. INJURY-TO-ROSTER COVERAGE
--
-- Expected:
-- injury rows          = 43,561
-- roster matched       = 43,549
-- roster unmatched     = 12
-- core-position misses = 6
-- match percentage     = 99.97
--
-- The unmatched records are concentrated around player
-- transactions and team changes. They must remain unmatched at
-- the same-team grain rather than being forced onto another team.
-- ============================================================

SELECT
    COUNT(*) AS injury_rows,
    SUM(
        CASE
            WHEN rpw.player_id IS NOT NULL THEN 1
            ELSE 0
        END
    ) AS roster_matched_rows,
    SUM(
        CASE
            WHEN rpw.player_id IS NULL THEN 1
            ELSE 0
        END
    ) AS roster_unmatched_rows,
    SUM(
        CASE
            WHEN rpw.player_id IS NULL
            AND ipw.position IN ('QB', 'RB', 'WR', 'TE')
            THEN 1
            ELSE 0
        END
    ) AS core_position_unmatched_rows,
    ROUND(
        100.0
        * SUM(
            CASE
                WHEN rpw.player_id IS NOT NULL THEN 1
                ELSE 0
            END
        )
        / NULLIF(COUNT(*), 0),
        2
    ) AS roster_match_pct,
    CASE
        WHEN COUNT(*) = 43561
        AND SUM(
                CASE
                    WHEN rpw.player_id IS NULL THEN 1
                    ELSE 0
                END
            ) = 12
        THEN 'EXPECTED_LIMITATION'
        ELSE 'REVIEW'
    END AS assessment
FROM injury_player_weeks AS ipw
LEFT JOIN roster_player_weeks AS rpw
    ON rpw.season = ipw.season
    AND rpw.week = ipw.week
    AND rpw.team = ipw.team
    AND rpw.player_id = ipw.player_id;

-- ============================================================
-- 13. DEPTH-CHART PLAYER COVERAGE
--
-- Expected:
-- legacy depth rows:
--   242,058 total, zero unmatched
--
-- timestamped snapshots:
--   548,638 total
--   548,452 matched
--   186 unmatched records representing 3 players
-- ============================================================

SELECT
    'legacy_weekly' AS depth_dataset,
    COUNT(*) AS total_rows,
    SUM(
        CASE
            WHEN p.player_id IS NOT NULL THEN 1
            ELSE 0
        END
    ) AS player_matched_rows,
    SUM(
        CASE
            WHEN p.player_id IS NULL THEN 1
            ELSE 0
        END
    ) AS player_unmatched_rows,
    COUNT(
        DISTINCT CASE
            WHEN p.player_id IS NULL THEN dlw.player_id
        END
    ) AS unmatched_players,
    ROUND(
        100.0
        * SUM(
            CASE
                WHEN p.player_id IS NOT NULL THEN 1
                ELSE 0
            END
        )
        / NULLIF(COUNT(*), 0),
        2
    ) AS player_match_pct,
    CASE
        WHEN SUM(
            CASE
                WHEN p.player_id IS NULL THEN 1
                ELSE 0
            END
        ) = 0
        THEN 'PASS'
        ELSE 'REVIEW'
    END AS assessment
FROM depth_chart_legacy_weeks AS dlw
LEFT JOIN players AS p
    ON p.player_id = dlw.player_id
UNION ALL
SELECT
    'timestamped',
    COUNT(*),
    SUM(
        CASE
            WHEN p.player_id IS NOT NULL THEN 1
            ELSE 0
        END
    ),
    SUM(
        CASE
            WHEN p.player_id IS NULL THEN 1
            ELSE 0
        END
    ),
    COUNT(
        DISTINCT CASE
            WHEN p.player_id IS NULL THEN ds.player_id
        END
    ),
    ROUND(
        100.0
        * SUM(
            CASE
                WHEN p.player_id IS NOT NULL THEN 1
                ELSE 0
            END
        )
        / NULLIF(COUNT(*), 0),
        2
    ),
    CASE
        WHEN COUNT(*) = 548638
        AND SUM(
                CASE
                    WHEN p.player_id IS NULL THEN 1
                    ELSE 0
                END
            ) = 186
        AND COUNT(
                DISTINCT CASE
                    WHEN p.player_id IS NULL
                    THEN ds.player_id
                END
            ) = 3
        THEN 'EXPECTED_LIMITATION'
        ELSE 'REVIEW'
    END
FROM depth_chart_snapshots AS ds
LEFT JOIN players AS p
    ON p.player_id = ds.player_id;

-- ============================================================
-- 14. INJURY COMPLETENESS BY SEASON
--
-- Missing final report status is expected source sparsity and
-- must not be interpreted as proof that a player was healthy.
--
-- The 2025 feed has no source update timestamp, preventing a
-- precise same-week intraday as-of join.
-- ============================================================

SELECT
    season,
    COUNT(*) AS injury_rows,
    SUM(
        CASE
            WHEN has_final_report_status = 0 THEN 1
            ELSE 0
        END
    ) AS missing_final_report_rows,
    ROUND(
        100.0
        * SUM(
            CASE
                WHEN has_final_report_status = 0 THEN 1
                ELSE 0
            END
        )
        / NULLIF(COUNT(*), 0),
        2
    ) AS missing_final_report_pct,
    SUM(
        CASE
            WHEN has_practice_status = 0 THEN 1
            ELSE 0
        END
    ) AS missing_practice_status_rows,
    ROUND(
        100.0
        * SUM(
            CASE
                WHEN has_practice_status = 0 THEN 1
                ELSE 0
            END
        )
        / NULLIF(COUNT(*), 0),
        2
    ) AS missing_practice_status_pct,
    SUM(
        CASE
            WHEN has_update_timestamp = 0 THEN 1
            ELSE 0
        END
    ) AS missing_update_timestamp_rows
FROM injury_player_weeks
GROUP BY season
ORDER BY season;

-- ============================================================
-- 15. INJURY UPDATE-TIME RISK
--
-- Expected definitely-after-game-date rows: 23
--
-- These are late updates or corrections and cannot be used as
-- pregame features for the corresponding game.
--
-- Same-date records still require a correctly aligned kickoff
-- timestamp before they can be considered safe.
-- ============================================================

SELECT
    COUNT(*) AS dated_injury_rows,
    SUM(
        CASE
            WHEN DATE(ipw.date_modified_utc) > tw.game_date
            THEN 1
            ELSE 0
        END
    ) AS definitely_after_game_date_rows,
    CASE
        WHEN SUM(
            CASE
                WHEN DATE(ipw.date_modified_utc) > tw.game_date
                THEN 1
                ELSE 0
            END
        ) = 23
        THEN 'EXPECTED_TEMPORAL_RISK'
        ELSE 'REVIEW'
    END AS assessment
FROM injury_player_weeks AS ipw
JOIN team_weeks AS tw
    ON tw.season = ipw.season
    AND tw.week = ipw.week
    AND tw.team = ipw.team
WHERE ipw.date_modified_utc IS NOT NULL;

-- ============================================================
-- 16. LEGACY DEPTH WEEK-19 SOURCE CONDITION
--
-- Expected: 7,221 rows across 2021-2024.
--
-- These records are retained as valid source snapshots but must
-- not join to a game week unless a corresponding game exists.
-- ============================================================

SELECT
    season,
    week,
    COUNT(*) AS depth_rows
FROM depth_chart_legacy_weeks
WHERE week = 19
GROUP BY
    season,
    week
ORDER BY season;

-- ============================================================
-- 17. TIMESTAMPED DEPTH-CHART RANGE
--
-- Expected:
-- minimum snapshot     = 2025-08-03 10:09:07
-- maximum snapshot     = 2026-03-14 07:32:09
-- rows after final regular-season game date = 183,817
--
-- The large post-season/offseason snapshot count proves that a
-- global latest-record join would leak future information.
-- ============================================================

SELECT
    MIN(snapshot_at_utc) AS minimum_snapshot_at_utc,
    MAX(snapshot_at_utc) AS maximum_snapshot_at_utc,
    (
        SELECT MAX(game_date)
        FROM games
    ) AS maximum_regular_season_game_date,
    SUM(
        CASE
            WHEN DATE(snapshot_at_utc) >
                (
                    SELECT MAX(game_date)
                    FROM games
                )
            THEN 1
            ELSE 0
        END
    ) AS rows_after_final_regular_season_game_date
FROM depth_chart_snapshots;

-- ============================================================
-- 18. MODELING LEAKAGE RISK REGISTER
--
-- These are feature-engineering requirements, not load errors.
-- Each source must be filtered or shifted before modeling.
-- ============================================================

SELECT
    'current-week fantasy outcome'
        AS risk_name,
    COUNT(*) AS affected_rows,
    'Shift the observed PPR result forward to become the next-week target.'
        AS required_action
FROM player_weeks
UNION ALL
SELECT
    'same-week snap counts',
    COUNT(*),
    'Use only snaps from games completed before the prediction cutoff.'
FROM snap_player_weeks
UNION ALL
SELECT
    '2025 injuries without update timestamps',
    COUNT(*),
    'Use a conservative prior-week rule or exclude same-week injury features.'
FROM injury_player_weeks
WHERE season = 2025
AND has_update_timestamp = 0
UNION ALL
SELECT
    'injury updates definitely after game date',
    COUNT(*),
    'Exclude these records from pregame features.'
FROM injury_player_weeks AS ipw
JOIN team_weeks AS tw
    ON tw.season = ipw.season
    AND tw.week = ipw.week
    AND tw.team = ipw.team
WHERE ipw.date_modified_utc IS NOT NULL
AND DATE(ipw.date_modified_utc) > tw.game_date
UNION ALL
SELECT
    'depth snapshots after the final regular-season game',
    COUNT(*),
    'Join only the latest snapshot available at or before each game cutoff.'
FROM depth_chart_snapshots
WHERE DATE(snapshot_at_utc) >
    (
        SELECT MAX(game_date)
        FROM games
    )
UNION ALL
SELECT
    'legacy week-19 depth rows',
    COUNT(*),
    'Do not join them to weeks without a corresponding scheduled game.'
FROM depth_chart_legacy_weeks
WHERE week = 19;