USE nfl_fantasy_advisor;

-- ============================================================
-- 1. TABLE-TOTAL RECONCILIATION
-- Every difference should be zero and every status should PASS.
-- Expected counts come from the validated extraction manifest.
-- ============================================================

WITH expected_rows AS (
    SELECT 'stg_schedules' AS table_name, 2127 AS expected_rows
    UNION ALL
    SELECT 'stg_weekly_rosters', 362959
    UNION ALL
    SELECT 'stg_injuries', 43561
    UNION ALL
    SELECT 'stg_depth_charts', 796273
    UNION ALL
    SELECT 'stg_snap_counts', 196130
    UNION ALL
    SELECT 'stg_weekly_player_stats', 45693
),
actual_rows AS (
    SELECT
        'stg_schedules' AS table_name,
        COUNT(*) AS actual_rows
    FROM stg_schedules

    UNION ALL

    SELECT
        'stg_weekly_rosters',
        COUNT(*)
    FROM stg_weekly_rosters

    UNION ALL

    SELECT
        'stg_injuries',
        COUNT(*)
    FROM stg_injuries

    UNION ALL

    SELECT
        'stg_depth_charts',
        COUNT(*)
    FROM stg_depth_charts

    UNION ALL

    SELECT
        'stg_snap_counts',
        COUNT(*)
    FROM stg_snap_counts

    UNION ALL

    SELECT
        'stg_weekly_player_stats',
        COUNT(*)
    FROM stg_weekly_player_stats
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
FROM expected_rows AS e
INNER JOIN actual_rows AS a
    ON a.table_name = e.table_name
ORDER BY e.table_name;


-- ============================================================
-- 2. SEASON AND CHRONOLOGICAL SPLIT CONTROL
-- 2018-2023: training
-- 2024: validation
-- 2025: test
-- Every status should PASS.
-- ============================================================

WITH season_splits AS (
    SELECT
        'schedules' AS dataset_name,
        season,
        data_split,
        COUNT(*) AS row_count
    FROM stg_schedules
    GROUP BY season, data_split

    UNION ALL

    SELECT
        'weekly_rosters',
        season,
        data_split,
        COUNT(*)
    FROM stg_weekly_rosters
    GROUP BY season, data_split

    UNION ALL

    SELECT
        'injuries',
        season,
        data_split,
        COUNT(*)
    FROM stg_injuries
    GROUP BY season, data_split

    UNION ALL

    SELECT
        'depth_charts',
        source_season,
        data_split,
        COUNT(*)
    FROM stg_depth_charts
    GROUP BY source_season, data_split

    UNION ALL

    SELECT
        'snap_counts',
        season,
        data_split,
        COUNT(*)
    FROM stg_snap_counts
    GROUP BY season, data_split

    UNION ALL

    SELECT
        'weekly_player_stats',
        season,
        data_split,
        COUNT(*)
    FROM stg_weekly_player_stats
    GROUP BY season, data_split
),
labeled_splits AS (
    SELECT
        dataset_name,
        season,
        data_split,
        row_count,
        CASE
            WHEN season BETWEEN 2018 AND 2023 THEN 'training'
            WHEN season = 2024 THEN 'validation'
            WHEN season = 2025 THEN 'test'
            ELSE 'unexpected'
        END AS expected_split
    FROM season_splits
)
SELECT
    dataset_name,
    season,
    data_split,
    expected_split,
    row_count,
    CASE
        WHEN data_split = expected_split THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM labeled_splits
ORDER BY dataset_name, season;


-- ============================================================
-- 3. PRIMARY GRAIN AND KEY AVAILABILITY
-- Duplicate key groups should be zero.
-- Unavailable roster identifiers may be nonzero.
-- ============================================================

SELECT
    'weekly_player_stats' AS dataset_name,
    COUNT(*) AS total_rows,
    COALESCE(
        SUM(
            CASE
                WHEN player_id IS NULL
                OR TRIM(player_id) = ''
                    THEN 1
                ELSE 0
            END
        ),
        0
    ) AS unavailable_key_rows,
    (
        SELECT COUNT(*)
        FROM (
            SELECT
                season,
                week,
                player_id
            FROM stg_weekly_player_stats
            WHERE player_id IS NOT NULL
            AND TRIM(player_id) <> ''
            GROUP BY
                season,
                week,
                player_id
            HAVING COUNT(*) > 1
        ) AS duplicate_groups
    ) AS duplicate_key_groups
FROM stg_weekly_player_stats

UNION ALL

SELECT
    'schedules',
    COUNT(*),
    COALESCE(
        SUM(
            CASE
                WHEN game_id IS NULL
                OR TRIM(game_id) = ''
                    THEN 1
                ELSE 0
            END
        ),
        0
    ),
    (
        SELECT COUNT(*)
        FROM (
            SELECT game_id
            FROM stg_schedules
            WHERE game_id IS NOT NULL
            AND TRIM(game_id) <> ''
            GROUP BY game_id
            HAVING COUNT(*) > 1
        ) AS duplicate_groups
    )
FROM stg_schedules

UNION ALL

SELECT
    'weekly_rosters',
    COUNT(*),
    COALESCE(
        SUM(
            CASE
                WHEN gsis_id IS NULL
                OR TRIM(gsis_id) = ''
                    THEN 1
                ELSE 0
            END
        ),
        0
    ),
    (
        SELECT COUNT(*)
        FROM (
            SELECT
                season,
                week,
                team,
                gsis_id
            FROM stg_weekly_rosters
            WHERE gsis_id IS NOT NULL
            AND TRIM(gsis_id) <> ''
            GROUP BY
                season,
                week,
                team,
                gsis_id
            HAVING COUNT(*) > 1
        ) AS duplicate_groups
    )
FROM stg_weekly_rosters

UNION ALL

SELECT
    'injuries',
    COUNT(*),
    COALESCE(
        SUM(
            CASE
                WHEN gsis_id IS NULL
                OR TRIM(gsis_id) = ''
                    THEN 1
                ELSE 0
            END
        ),
        0
    ),
    (
        SELECT COUNT(*)
        FROM (
            SELECT
                season,
                week,
                team,
                gsis_id
            FROM stg_injuries
            WHERE gsis_id IS NOT NULL
            AND TRIM(gsis_id) <> ''
            GROUP BY
                season,
                week,
                team,
                gsis_id
            HAVING COUNT(*) > 1
        ) AS duplicate_groups
    )
FROM stg_injuries

UNION ALL

SELECT
    'snap_counts',
    COUNT(*),
    COALESCE(
        SUM(
            CASE
                WHEN pfr_player_id IS NULL
                OR TRIM(pfr_player_id) = ''
                    THEN 1
                ELSE 0
            END
        ),
        0
    ),
    (
        SELECT COUNT(*)
        FROM (
            SELECT
                season,
                week,
                game_id,
                team,
                pfr_player_id
            FROM stg_snap_counts
            WHERE pfr_player_id IS NOT NULL
            AND TRIM(pfr_player_id) <> ''
            GROUP BY
                season,
                week,
                game_id,
                team,
                pfr_player_id
            HAVING COUNT(*) > 1
        ) AS duplicate_groups
    )
FROM stg_snap_counts;


-- ============================================================
-- 4. DEPTH-CHART FORMAT AND KEY CONTROLS
-- 2018-2024 should be legacy_weekly.
-- 2025 should be timestamped.
-- Unavailable 2025 GSIS IDs are retained and reported.
-- ============================================================

SELECT
    source_season,
    depth_source_format,
    COUNT(*) AS row_count,
    SUM(
        CASE
            WHEN gsis_id IS NULL
            OR TRIM(gsis_id) = ''
                THEN 1
            ELSE 0
        END
    ) AS unavailable_gsis_rows,
    SUM(
        CASE
            WHEN depth_source_format = 'legacy_weekly'
            AND (
                    season IS NULL
                OR week IS NULL
                OR team IS NULL
                OR TRIM(team) = ''
                OR pos_grp IS NULL
                OR TRIM(pos_grp) = ''
                OR pos_abb IS NULL
                OR TRIM(pos_abb) = ''
                OR pos_rank IS NULL
            )
                THEN 1
            ELSE 0
        END
    ) AS legacy_missing_key_parts,
    SUM(
        CASE
            WHEN depth_source_format = 'timestamped'
            AND (
                    dt IS NULL
                OR TRIM(dt) = ''
                OR team IS NULL
                OR TRIM(team) = ''
                OR pos_abb IS NULL
                OR TRIM(pos_abb) = ''
                OR pos_slot IS NULL
            )
                THEN 1
            ELSE 0
        END
    ) AS timestamped_missing_key_parts,
    SUM(
        CASE
            WHEN depth_source_format NOT IN (
                'legacy_weekly',
                'timestamped'
            )
                THEN 1
            ELSE 0
        END
    ) AS unexpected_format_rows
FROM stg_depth_charts
GROUP BY
    source_season,
    depth_source_format
ORDER BY source_season;


-- Both duplicate counts should be zero.

select
	'legacy_weekly' AS depth_source_format,
	COUNT(*) AS duplicate_key_groups
FROM (
    SELECT
        season,
        week,
        team,
        gsis_id,
        pos_grp,
        pos_abb,
        pos_rank
    FROM stg_depth_charts
    WHERE depth_source_format = 'legacy_weekly'
    AND gsis_id IS NOT NULL
    AND TRIM(gsis_id) <> ''
    GROUP BY
        season,
        week,
        team,
        gsis_id,
        pos_grp,
        pos_abb,
        pos_rank
    HAVING COUNT(*) > 1
) AS duplicate_groups
UNION ALL
SELECT
    'timestamped' AS depth_source_format,
    COUNT(*) AS duplicate_key_groups
FROM (
    SELECT
        dt,
        team,
        gsis_id,
        pos_abb,
        pos_slot
    FROM stg_depth_charts
    WHERE depth_source_format = 'timestamped'
    AND gsis_id IS NOT NULL
    AND TRIM(gsis_id) <> ''
    GROUP BY
        dt,
        team,
        gsis_id,
        pos_abb,
        pos_slot
    HAVING COUNT(*) > 1
) AS duplicate_groups;


-- ============================================================
-- 5. DOCUMENTED ROSTER IDENTITY EXCEPTIONS
-- Expected:
-- multi_team_player_week_groups = 13
-- conflicting_crosswalk_groups = 0
-- flagged conflicts are retained for auditability.
-- ============================================================

SELECT
    (
        SELECT COUNT(*)
        FROM (
            SELECT
                season,
                week,
                gsis_id
            FROM stg_weekly_rosters
            WHERE gsis_id IS NOT NULL
            AND TRIM(gsis_id) <> ''
            GROUP BY
                season,
                week,
                gsis_id
            HAVING COUNT(DISTINCT team) > 1
        ) AS multi_team_groups
    ) AS multi_team_player_week_groups,
    (
        SELECT COUNT(*)
        FROM (
            SELECT
                season,
                week,
                team,
                gsis_id
            FROM stg_weekly_rosters
            WHERE gsis_id IS NOT NULL
            AND TRIM(gsis_id) <> ''
            AND pfr_id IS NOT NULL
            AND TRIM(pfr_id) <> ''
            GROUP BY
                season,
                week,
                team,
                gsis_id
            HAVING COUNT(DISTINCT pfr_id) > 1
        ) AS conflicting_groups
    ) AS conflicting_crosswalk_groups,
    SUM(
        CASE
            WHEN pfr_id_conflict = 1 THEN 1
            ELSE 0
        END
    ) AS flagged_pfr_conflict_rows
FROM stg_weekly_rosters;


-- ============================================================
-- 6. CORE PLAYER-STAT DOMAIN CONTROLS
-- Every invalid or unavailable count should be zero.
-- ============================================================

SELECT
    COUNT(*) AS player_week_rows,
    SUM(
        CASE
            WHEN player_id IS NULL
            OR TRIM(player_id) = ''
                THEN 1
            ELSE 0
        END
    ) AS unavailable_player_ids,
    SUM(
        CASE
            WHEN game_id IS NULL
            OR TRIM(game_id) = ''
                THEN 1
            ELSE 0
        END
    ) AS unavailable_game_ids,
    SUM(
        CASE
            WHEN team IS NULL
            OR TRIM(team) = ''
                THEN 1
            ELSE 0
        END
    ) AS unavailable_teams,
    SUM(
        CASE
            WHEN opponent_team IS NULL
            OR TRIM(opponent_team) = ''
                THEN 1
            ELSE 0
        END
    ) AS unavailable_opponents,
    SUM(
        CASE
            WHEN position IS NULL
            OR position NOT IN ('QB', 'RB', 'WR', 'TE')
                THEN 1
            ELSE 0
        END
    ) AS invalid_position_rows,
    SUM(
        CASE
            WHEN season_type IS NULL
            OR season_type <> 'REG'
                THEN 1
            ELSE 0
        END
    ) AS invalid_season_type_rows,
    SUM(
        CASE
            WHEN week IS NULL
            OR week NOT BETWEEN 1 AND 18
                THEN 1
            ELSE 0
        END
    ) AS invalid_week_rows
FROM stg_weekly_player_stats;


-- Expected positions: QB, RB, TE, and WR only.

SELECT
    position,
    COUNT(*) AS player_week_rows,
    COUNT(DISTINCT player_id) AS distinct_players
FROM stg_weekly_player_stats
GROUP BY position
ORDER BY position;


-- ============================================================
-- 7. PLAYER-STATS JOIN COVERAGE
-- Schedule and roster coverage must equal 100%.
-- Snap coverage must remain at or above 98%.
-- ============================================================

WITH schedule_keys AS (
    SELECT DISTINCT game_id
    FROM stg_schedules
),
roster_keys AS (
    SELECT DISTINCT
        season,
        week,
        team,
        gsis_id AS player_id
    FROM stg_weekly_rosters
    WHERE gsis_id IS NOT NULL
    AND TRIM(gsis_id) <> ''
),
roster_crosswalk AS (
    SELECT
        season,
        week,
        team,
        gsis_id AS player_id,
        MIN(pfr_id) AS pfr_player_id
    FROM stg_weekly_rosters
    WHERE gsis_id IS NOT NULL
    AND TRIM(gsis_id) <> ''
    AND pfr_id IS NOT NULL
    AND TRIM(pfr_id) <> ''
    GROUP BY
        season,
        week,
        team,
        gsis_id
),
snap_keys AS (
    SELECT DISTINCT
        season,
        week,
        team,
        pfr_player_id
    FROM stg_snap_counts
)
SELECT
    p.season,
    COUNT(*) AS player_week_rows,
    SUM(
        CASE
            WHEN s.game_id IS NOT NULL THEN 1
            ELSE 0
        END
    ) AS schedule_matched_rows,
    ROUND(
        100.0
        * SUM(
            CASE
                WHEN s.game_id IS NOT NULL THEN 1
                ELSE 0
            END
        )
        / COUNT(*),
        2
    ) AS schedule_match_pct,
    SUM(
        CASE
            WHEN r.player_id IS NOT NULL THEN 1
            ELSE 0
        END
    ) AS roster_matched_rows,
    ROUND(
        100.0
        * SUM(
            CASE
                WHEN r.player_id IS NOT NULL THEN 1
                ELSE 0
            END
        )
        / COUNT(*),
        2
    ) AS roster_match_pct,
    SUM(
        CASE
            WHEN sn.pfr_player_id IS NOT NULL THEN 1
            ELSE 0
        END
    ) AS snap_matched_rows,
    ROUND(
        100.0
        * SUM(
            CASE
                WHEN sn.pfr_player_id IS NOT NULL THEN 1
                ELSE 0
            END
        )
        / COUNT(*),
        2
    ) AS snap_match_pct,
    CASE
        WHEN
            ROUND(
                100.0
                * SUM(
                    CASE
                        WHEN s.game_id IS NOT NULL THEN 1
                        ELSE 0
                    END
                )
                / COUNT(*),
                2
            ) = 100.00
        AND
            ROUND(
                100.0
                * SUM(
                    CASE
                        WHEN r.player_id IS NOT NULL THEN 1
                        ELSE 0
                    END
                )
                / COUNT(*),
                2
            ) = 100.00
        AND
            ROUND(
                100.0
                * SUM(
                    CASE
                        WHEN sn.pfr_player_id IS NOT NULL THEN 1
                        ELSE 0
                    END
                )
                / COUNT(*),
                2
            ) >= 98.00
            THEN 'PASS'
        ELSE 'FAIL'
    END AS coverage_status
FROM stg_weekly_player_stats AS p
LEFT JOIN schedule_keys AS s
    ON s.game_id = p.game_id
LEFT JOIN roster_keys AS r
    ON r.season = p.season
    AND r.week = p.week
    AND r.team = p.team
    AND r.player_id = p.player_id
LEFT JOIN roster_crosswalk AS x
    ON x.season = p.season
    AND x.week = p.week
    AND x.team = p.team
    AND x.player_id = p.player_id
LEFT JOIN snap_keys AS sn
    ON sn.season = p.season
    AND sn.week = p.week
    AND sn.team = p.team
    AND sn.pfr_player_id = x.pfr_player_id
GROUP BY p.season
ORDER BY p.season;


-- ============================================================
-- 8. CONFIGURED FULL-PPR RECONCILIATION
-- Mismatch rows must be zero.
-- Maximum absolute difference must not exceed 0.01.
-- ============================================================

SELECT
    season,
    COUNT(*) AS player_week_rows,
    SUM(
        CASE
            WHEN fantasy_point_difference IS NULL
            OR ABS(fantasy_point_difference) > 0.01
                THEN 1
            ELSE 0
        END
    ) AS ppr_mismatch_rows,
    ROUND(
        MAX(ABS(fantasy_point_difference)),
        6
    ) AS maximum_absolute_difference,
    CASE
        WHEN
            SUM(
                CASE
                    WHEN fantasy_point_difference IS NULL
                    OR ABS(fantasy_point_difference) > 0.01
                        THEN 1
                    ELSE 0
                END
            ) = 0
            THEN 'PASS'
        ELSE 'FAIL'
    END AS reconciliation_status
FROM stg_weekly_player_stats
GROUP BY season
ORDER BY season;


-- ============================================================
-- 9. INJURY-FIELD COMPLETENESS
-- Missing report status is expected and is not automatically an error.
-- These rates must inform feature availability and leakage controls.
-- ============================================================

SELECT
    season,
    COUNT(*) AS injury_rows,
    SUM(
        CASE
            WHEN report_status IS NULL
            OR TRIM(report_status) = ''
                THEN 1
            ELSE 0
        END
    ) AS missing_report_status_rows,
    ROUND(
        100.0
        * SUM(
            CASE
                WHEN report_status IS NULL
                OR TRIM(report_status) = ''
                    THEN 1
                ELSE 0
            END
        )
        / COUNT(*),
        2
    ) AS missing_report_status_pct,
    SUM(
        CASE
            WHEN practice_status IS NULL
            OR TRIM(practice_status) = ''
                THEN 1
            ELSE 0
        END
    ) AS missing_practice_status_rows,
    ROUND(
        100.0
        * SUM(
            CASE
                WHEN practice_status IS NULL
                OR TRIM(practice_status) = ''
                    THEN 1
                ELSE 0
            END
        )
        / COUNT(*),
        2
    ) AS missing_practice_status_pct,
    SUM(
        CASE
            WHEN date_modified IS NOT NULL THEN 1
            ELSE 0
        END
    ) AS timestamped_injury_rows
FROM stg_injuries
GROUP BY season
ORDER BY season;


-- ============================================================
-- 10. INJURY TEXT-WIDTH REGRESSION CONTROL
-- The earlier 150-character definition failed on a 154-character value.
-- The final 255-character definition should have positive headroom.
-- ============================================================

SELECT
    MAX(
        CHAR_LENGTH(report_primary_injury)
    ) AS maximum_observed_length,
    255 AS configured_character_limit,
    255
        - MAX(
            CHAR_LENGTH(report_primary_injury)
        ) AS remaining_character_headroom,
    CASE
        WHEN MAX(
            CHAR_LENGTH(report_primary_injury)
        ) <= 255
            THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM stg_injuries;