-- ============================================================
-- NFL Fantasy Football Advisor
-- Leakage-Safe Model Feature Pipeline
--
-- Phase 1: Read-only source preflight
--
-- This section does not create or modify any tables.
-- It profiles the validated clean sources before feature
-- engineering decisions are implemented.
-- ============================================================

USE nfl_fantasy_advisor;

SELECT
    DATABASE() AS active_database;

-- ============================================================
-- 1. PLAYER-WEEK GRAIN AND REQUIRED VALUES
-- ============================================================

SELECT
    COUNT(*) AS player_week_rows,
    COUNT(
        DISTINCT CONCAT_WS(
            '|',
            season,
            week,
            player_id
        )
    ) AS distinct_player_week_keys,
    SUM(
        player_id IS NULL
        OR TRIM(player_id) = ''
    ) AS unavailable_player_ids,
    SUM(
        game_id IS NULL
        OR TRIM(game_id) = ''
    ) AS unavailable_game_ids,
    SUM(
        team IS NULL
        OR TRIM(team) = ''
    ) AS unavailable_teams,
    SUM(
        opponent_team IS NULL
        OR TRIM(opponent_team) = ''
    ) AS unavailable_opponents,
    SUM(fantasy_points_ppr IS NULL) AS missing_ppr_targets
FROM player_weeks;

-- ============================================================
-- 2. BOX-SCORE MISSINGNESS BY POSITION
--
-- This determines whether observed counting-stat zeros are
-- already represented as zero or appear as NULL.
-- ============================================================

SELECT
    position,
    COUNT(*) AS player_week_rows,
    SUM(attempts IS NULL) AS missing_attempts,
    SUM(carries IS NULL) AS missing_carries,
    SUM(targets IS NULL) AS missing_targets,
    SUM(receptions IS NULL) AS missing_receptions,
    SUM(passing_yards IS NULL) AS missing_passing_yards,
    SUM(rushing_yards IS NULL) AS missing_rushing_yards,
    SUM(receiving_yards IS NULL) AS missing_receiving_yards,
    SUM(fantasy_points_ppr IS NULL) AS missing_ppr_targets
FROM player_weeks
GROUP BY
    position
ORDER BY
    FIELD(position, 'QB', 'RB', 'WR', 'TE');

-- ============================================================
-- 3. USAGE-SHARE AVAILABILITY BY POSITION
-- ============================================================

SELECT
    position,
    COUNT(*) AS player_week_rows,
    SUM(target_share IS NOT NULL) AS published_target_share_rows,
    ROUND(
        100.0 * SUM(target_share IS NOT NULL) / COUNT(*),
        2
    ) AS target_share_coverage_pct,
    SUM(air_yards_share IS NOT NULL)
        AS published_air_yards_share_rows,
    ROUND(
        100.0 * SUM(air_yards_share IS NOT NULL) / COUNT(*),
        2
    ) AS air_yards_share_coverage_pct,
    SUM(wopr IS NOT NULL) AS published_wopr_rows,
    ROUND(
        100.0 * SUM(wopr IS NOT NULL) / COUNT(*),
        2
    ) AS wopr_coverage_pct
FROM player_weeks
GROUP BY
    position
ORDER BY
    FIELD(position, 'QB', 'RB', 'WR', 'TE');

-- ============================================================
-- 4. SNAP-COUNT GSIS GRAIN
--
-- If repeated GSIS player-week groups exist, snap records must
-- be reduced to one GSIS row before joining to player_weeks.
-- ============================================================

WITH snap_gsis_groups AS (
    SELECT
        season,
        week,
        team,
        player_id,
        COUNT(*) AS source_rows
    FROM snap_player_weeks
    WHERE player_id IS NOT NULL
    GROUP BY
        season,
        week,
        team,
        player_id
)
SELECT
    COUNT(*) AS matched_gsis_player_week_groups,
    SUM(source_rows) AS matched_snap_source_rows,
    SUM(source_rows > 1) AS repeated_gsis_groups,
    SUM(source_rows - 1) AS duplicate_rows_above_gsis_grain,
    MAX(source_rows) AS maximum_rows_in_one_gsis_group
FROM snap_gsis_groups;

-- ============================================================
-- 5. PLAYER-WEEK TO SNAP COVERAGE
--
-- The grouped CTE guarantees that this diagnostic join cannot
-- multiply player-week rows.
-- ============================================================

WITH snap_gsis AS (
    SELECT
        season,
        week,
        team,
        player_id,
        MAX(offense_snaps) AS offense_snaps,
        MAX(offense_pct) AS offense_pct
    FROM snap_player_weeks
    WHERE player_id IS NOT NULL
    GROUP BY
        season,
        week,
        team,
        player_id
)
SELECT
    pw.position,
    COUNT(*) AS player_week_rows,
    SUM(s.player_id IS NOT NULL) AS snap_matched_rows,
    SUM(s.player_id IS NULL) AS snap_unmatched_rows,
    ROUND(
        100.0 * SUM(s.player_id IS NOT NULL) / COUNT(*),
        2
    ) AS snap_match_pct,
    SUM(s.offense_snaps IS NOT NULL)
        AS published_offense_snap_rows,
    SUM(s.offense_pct IS NOT NULL)
        AS published_offense_pct_rows
FROM player_weeks AS pw
LEFT JOIN snap_gsis AS s
    ON s.season = pw.season
    AND s.week = pw.week
    AND s.team = pw.team
    AND s.player_id = pw.player_id
GROUP BY
    pw.position
ORDER BY
    FIELD(pw.position, 'QB', 'RB', 'WR', 'TE');

-- ============================================================
-- 6. TARGET-GAME CONTEXT AVAILABILITY
-- ============================================================

SELECT
    pw.season,
    COUNT(*) AS player_week_rows,
    SUM(tw.game_id IS NOT NULL) AS schedule_matched_rows,
    SUM(tw.source_spread_line IS NOT NULL)
        AS published_spread_rows,
    SUM(tw.total_line IS NOT NULL)
        AS published_total_line_rows,
    SUM(tw.roof IS NOT NULL) AS published_roof_rows,
    SUM(tw.surface IS NOT NULL) AS published_surface_rows,
    SUM(tw.temp IS NOT NULL) AS published_temperature_rows,
    SUM(tw.wind IS NOT NULL) AS published_wind_rows
FROM player_weeks AS pw
LEFT JOIN team_weeks AS tw
    ON tw.season = pw.season
    AND tw.week = pw.week
    AND tw.team = pw.team
GROUP BY
    pw.season
ORDER BY
    pw.season;

-- ============================================================
-- 7. BUILD PLAYER GAME HISTORY
--
-- Grain: one observed core fantasy player per regular-season
-- game.
--
-- Expected rows: 45,693
--
-- WARNING:
-- This is a postgame history table. Its current-row statistics,
-- fantasy result, and snap values must not be used directly to
-- predict that same game.
-- ============================================================

DROP TABLE IF EXISTS model_player_weeks;
DROP TABLE IF EXISTS opponent_position_week_history;
DROP TABLE IF EXISTS player_game_history;

CREATE TABLE player_game_history (
    season SMALLINT UNSIGNED NOT NULL,
    week TINYINT UNSIGNED NOT NULL,
    game_id VARCHAR(30) NOT NULL,
    game_date DATE NOT NULL,
    game_time TIME,

    player_id VARCHAR(20) NOT NULL,
    player_name VARCHAR(100),
    player_display_name VARCHAR(150),
    position VARCHAR(10) NOT NULL,
    team VARCHAR(5) NOT NULL,
    opponent VARCHAR(5) NOT NULL,

    game_location VARCHAR(4) NOT NULL,
    is_home TINYINT(1) NOT NULL,
    team_rest SMALLINT,
    opponent_rest SMALLINT,
    source_spread_line DOUBLE,
    total_line DOUBLE,
    div_game TINYINT,
    roof VARCHAR(40),
    surface VARCHAR(60),

    completions INT NOT NULL,
    attempts INT NOT NULL,
    passing_yards INT NOT NULL,
    passing_tds INT NOT NULL,
    passing_interceptions INT NOT NULL,

    carries INT NOT NULL,
    rushing_yards INT NOT NULL,
    rushing_tds INT NOT NULL,

    receptions INT NOT NULL,
    targets INT NOT NULL,
    receiving_yards INT NOT NULL,
    receiving_tds INT NOT NULL,

    target_share DOUBLE NOT NULL,
    air_yards_share DOUBLE NOT NULL,
    wopr DOUBLE NOT NULL,

    touches INT NOT NULL,
    position_adjusted_opportunities INT NOT NULL,
    yards_from_scrimmage INT NOT NULL,
    total_offensive_yards INT NOT NULL,
    total_offensive_tds INT NOT NULL,

    offense_snaps DOUBLE,
    offense_pct DOUBLE,
    has_snap_record TINYINT(1) NOT NULL,

    target_fantasy_points_ppr DOUBLE NOT NULL,
    calculated_fantasy_points_ppr DOUBLE NOT NULL,
    fantasy_point_difference DOUBLE NOT NULL,

    data_split VARCHAR(12) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (
        season,
        week,
        player_id
    ),

    UNIQUE KEY uq_player_game_history_game_player (
        game_id,
        player_id
    ),

    INDEX idx_player_game_history_player (
        player_id,
        season,
        week
    ),

    INDEX idx_player_game_history_player_date (
        player_id,
        game_date
    ),

    INDEX idx_player_game_history_team (
        team,
        season,
        week
    ),

    INDEX idx_player_game_history_opponent_position (
        opponent,
        position,
        season,
        week
    ),

    CONSTRAINT chk_player_game_history_position
        CHECK (position IN ('QB', 'RB', 'WR', 'TE')),

    CONSTRAINT chk_player_game_history_week
        CHECK (week BETWEEN 1 AND 18),

    CONSTRAINT chk_player_game_history_location
        CHECK (game_location IN ('HOME', 'AWAY')),

    CONSTRAINT chk_player_game_history_is_home
        CHECK (is_home IN (0, 1)),

    CONSTRAINT chk_player_game_history_snap_flag
        CHECK (has_snap_record IN (0, 1)),

    CONSTRAINT chk_player_game_history_split
        CHECK (
            data_split IN ('training', 'validation', 'test')
        ),

    CONSTRAINT chk_player_game_history_volume
        CHECK (
            attempts >= 0
            AND carries >= 0
            AND targets >= 0
            AND receptions >= 0
            AND touches >= 0
            AND position_adjusted_opportunities >= 0
        )
) ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;

INSERT INTO player_game_history (
    season,
    week,
    game_id,
    game_date,
    game_time,
    player_id,
    player_name,
    player_display_name,
    position,
    team,
    opponent,
    game_location,
    is_home,
    team_rest,
    opponent_rest,
    source_spread_line,
    total_line,
    div_game,
    roof,
    surface,
    completions,
    attempts,
    passing_yards,
    passing_tds,
    passing_interceptions,
    carries,
    rushing_yards,
    rushing_tds,
    receptions,
    targets,
    receiving_yards,
    receiving_tds,
    target_share,
    air_yards_share,
    wopr,
    touches,
    position_adjusted_opportunities,
    yards_from_scrimmage,
    total_offensive_yards,
    total_offensive_tds,
    offense_snaps,
    offense_pct,
    has_snap_record,
    target_fantasy_points_ppr,
    calculated_fantasy_points_ppr,
    fantasy_point_difference,
    data_split
)
SELECT
    pw.season,
    pw.week,
    pw.game_id,
    tw.game_date,
    tw.game_time,
    pw.player_id,
    pw.player_name,
    pw.player_display_name,
    pw.position,
    pw.team,
    pw.opponent_team,
    tw.game_location,
    tw.is_home,
    tw.team_rest,
    tw.opponent_rest,
    tw.source_spread_line,
    tw.total_line,
    tw.div_game,
    tw.roof,
    tw.surface,
    pw.completions,
    pw.attempts,
    pw.passing_yards,
    pw.passing_tds,
    pw.passing_interceptions,
    pw.carries,
    pw.rushing_yards,
    pw.rushing_tds,
    pw.receptions,
    pw.targets,
    pw.receiving_yards,
    pw.receiving_tds,
    pw.target_share,
    pw.air_yards_share,
    pw.wopr,
    pw.carries + pw.receptions,
    CASE
        WHEN pw.position = 'QB'
            THEN pw.attempts + pw.carries
        WHEN pw.position = 'RB'
            THEN pw.carries + pw.targets
        WHEN pw.position IN ('WR', 'TE')
            THEN pw.targets
    END,
    pw.rushing_yards + pw.receiving_yards,
    (
        pw.passing_yards
        + pw.rushing_yards
        + pw.receiving_yards
    ),
    (
        pw.passing_tds
        + pw.rushing_tds
        + pw.receiving_tds
    ),
    s.offense_snaps,
    s.offense_pct,
    CASE
        WHEN s.player_id IS NOT NULL THEN 1
        ELSE 0
    END,
    pw.fantasy_points_ppr,
    pw.calculated_fantasy_points_ppr,
    pw.fantasy_point_difference,
    pw.data_split
FROM player_weeks AS pw
INNER JOIN team_weeks AS tw
    ON tw.season = pw.season
    AND tw.week = pw.week
    AND tw.team = pw.team
LEFT JOIN (
    SELECT
        season,
        week,
        team,
        player_id,
        MAX(offense_snaps) AS offense_snaps,
        MAX(offense_pct) AS offense_pct
    FROM snap_player_weeks
    WHERE player_id IS NOT NULL
    GROUP BY
        season,
        week,
        team,
        player_id
) AS s
    ON s.season = pw.season
    AND s.week = pw.week
    AND s.team = pw.team
    AND s.player_id = pw.player_id;

-- ============================================================
-- 8. PLAYER GAME HISTORY RECONCILIATION
-- ============================================================

WITH row_counts AS (
    SELECT
        (SELECT COUNT(*) FROM player_weeks)
            AS source_player_week_rows,
        (SELECT COUNT(*) FROM player_game_history)
            AS history_rows,
        (
            SELECT COUNT(*)
            FROM (
                SELECT
                    season,
                    week,
                    player_id
                FROM player_game_history
                GROUP BY
                    season,
                    week,
                    player_id
            ) AS distinct_history_keys
        ) AS distinct_history_keys
)
SELECT
    source_player_week_rows,
    history_rows,
    distinct_history_keys,
    history_rows - source_player_week_rows
        AS row_difference,
    CASE
        WHEN history_rows = source_player_week_rows
            AND distinct_history_keys = history_rows
        THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM row_counts;

SELECT
    COUNT(*) AS history_rows,
    SUM(has_snap_record = 1) AS snap_matched_rows,
    SUM(has_snap_record = 0) AS snap_unmatched_rows,
    ROUND(
        100.0 * SUM(has_snap_record = 1) / COUNT(*),
        2
    ) AS snap_match_pct,
    SUM(
        ABS(
            target_fantasy_points_ppr
            - calculated_fantasy_points_ppr
        ) > 0.01
    ) AS ppr_mismatch_rows,
    MAX(
        ABS(
            target_fantasy_points_ppr
            - calculated_fantasy_points_ppr
        )
    ) AS maximum_absolute_ppr_difference
FROM player_game_history;

-- ============================================================
-- 9. BUILD OPPONENT POSITION-WEEK HISTORY
--
-- Grain:
-- season + week + defensive_team + position
--
-- Each row describes the completed fantasy production allowed
-- by one defense to one core fantasy position in one game.
--
-- WARNING:
-- Same-week values are postgame evidence. The final model table
-- may use only lagged or earlier rolling values.
-- ============================================================

DROP TABLE IF EXISTS model_player_weeks;
DROP TABLE IF EXISTS opponent_position_week_history;

CREATE TABLE opponent_position_week_history (
    season SMALLINT UNSIGNED NOT NULL,
    week TINYINT UNSIGNED NOT NULL,
    game_id VARCHAR(30) NOT NULL,
    game_date DATE NOT NULL,

    defensive_team VARCHAR(5) NOT NULL,
    offensive_team VARCHAR(5) NOT NULL,
    position VARCHAR(10) NOT NULL,

    player_rows INT NOT NULL,
    fantasy_points_ppr_allowed DOUBLE NOT NULL,

    completions_allowed INT NOT NULL,
    passing_attempts_allowed INT NOT NULL,
    passing_yards_allowed INT NOT NULL,
    passing_tds_allowed INT NOT NULL,

    carries_allowed INT NOT NULL,
    rushing_yards_allowed INT NOT NULL,
    rushing_tds_allowed INT NOT NULL,

    receptions_allowed INT NOT NULL,
    targets_allowed INT NOT NULL,
    receiving_yards_allowed INT NOT NULL,
    receiving_tds_allowed INT NOT NULL,

    touches_allowed INT NOT NULL,
    position_adjusted_opportunities_allowed INT NOT NULL,
    yards_from_scrimmage_allowed INT NOT NULL,
    total_offensive_yards_allowed INT NOT NULL,
    total_offensive_tds_allowed INT NOT NULL,

    data_split VARCHAR(12) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (
        season,
        week,
        defensive_team,
        position
    ),

    UNIQUE KEY uq_opponent_position_game (
        game_id,
        defensive_team,
        position
    ),

    INDEX idx_opponent_position_history_team (
        defensive_team,
        position,
        season,
        week
    ),

    INDEX idx_opponent_position_history_date (
        defensive_team,
        position,
        game_date
    ),

    CONSTRAINT chk_opponent_position_history_position
        CHECK (position IN ('QB', 'RB', 'WR', 'TE')),

    CONSTRAINT chk_opponent_position_history_week
        CHECK (week BETWEEN 1 AND 18),

    CONSTRAINT chk_opponent_position_history_players
        CHECK (player_rows > 0),

    CONSTRAINT chk_opponent_position_history_split
        CHECK (
            data_split IN ('training', 'validation', 'test')
        )
) ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;

INSERT INTO opponent_position_week_history (
    season,
    week,
    game_id,
    game_date,
    defensive_team,
    offensive_team,
    position,
    player_rows,
    fantasy_points_ppr_allowed,
    completions_allowed,
    passing_attempts_allowed,
    passing_yards_allowed,
    passing_tds_allowed,
    carries_allowed,
    rushing_yards_allowed,
    rushing_tds_allowed,
    receptions_allowed,
    targets_allowed,
    receiving_yards_allowed,
    receiving_tds_allowed,
    touches_allowed,
    position_adjusted_opportunities_allowed,
    yards_from_scrimmage_allowed,
    total_offensive_yards_allowed,
    total_offensive_tds_allowed,
    data_split
)
SELECT
    h.season,
    h.week,
    h.game_id,
    h.game_date,
    h.opponent,
    h.team,
    h.position,
    COUNT(*) AS player_rows,
    SUM(h.target_fantasy_points_ppr),
    SUM(h.completions),
    SUM(h.attempts),
    SUM(h.passing_yards),
    SUM(h.passing_tds),
    SUM(h.carries),
    SUM(h.rushing_yards),
    SUM(h.rushing_tds),
    SUM(h.receptions),
    SUM(h.targets),
    SUM(h.receiving_yards),
    SUM(h.receiving_tds),
    SUM(h.touches),
    SUM(h.position_adjusted_opportunities),
    SUM(h.yards_from_scrimmage),
    SUM(h.total_offensive_yards),
    SUM(h.total_offensive_tds),
    h.data_split
FROM player_game_history AS h
GROUP BY
    h.season,
    h.week,
    h.game_id,
    h.game_date,
    h.opponent,
    h.team,
    h.position,
    h.data_split;

-- ============================================================
-- 10. OPPONENT HISTORY GRAIN RECONCILIATION
-- ============================================================

WITH expected_rows AS (
    SELECT
        COUNT(*) AS expected_history_rows
    FROM (
        SELECT
            season,
            week,
            opponent,
            position
        FROM player_game_history
        GROUP BY
            season,
            week,
            opponent,
            position
    ) AS expected_groups
),
actual_rows AS (
    SELECT
        COUNT(*) AS actual_history_rows,
        COUNT(
            DISTINCT CONCAT_WS(
                '|',
                season,
                week,
                defensive_team,
                position
            )
        ) AS distinct_history_keys
    FROM opponent_position_week_history
)
SELECT
    e.expected_history_rows,
    a.actual_history_rows,
    a.distinct_history_keys,
    a.actual_history_rows - e.expected_history_rows
        AS row_difference,
    CASE
        WHEN a.actual_history_rows = e.expected_history_rows
            AND a.distinct_history_keys = a.actual_history_rows
        THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM expected_rows AS e
CROSS JOIN actual_rows AS a;

-- ============================================================
-- 11. OPPONENT HISTORY MEASURE RECONCILIATION
-- ============================================================

WITH source_totals AS (
    SELECT
        COUNT(*) AS source_player_rows,
        SUM(target_fantasy_points_ppr)
            AS source_fantasy_points_ppr,
        SUM(passing_yards) AS source_passing_yards,
        SUM(rushing_yards) AS source_rushing_yards,
        SUM(receiving_yards) AS source_receiving_yards
    FROM player_game_history
),
history_totals AS (
    SELECT
        SUM(player_rows) AS history_player_rows,
        SUM(fantasy_points_ppr_allowed)
            AS history_fantasy_points_ppr,
        SUM(passing_yards_allowed)
            AS history_passing_yards,
        SUM(rushing_yards_allowed)
            AS history_rushing_yards,
        SUM(receiving_yards_allowed)
            AS history_receiving_yards
    FROM opponent_position_week_history
)
SELECT
    s.source_player_rows,
    h.history_player_rows,
    h.history_player_rows - s.source_player_rows AS player_row_difference,
    s.source_fantasy_points_ppr,
    h.history_fantasy_points_ppr,
    h.history_fantasy_points_ppr
        - s.source_fantasy_points_ppr
        AS fantasy_point_difference,
    h.history_passing_yards
        - s.source_passing_yards
        AS passing_yard_difference,
    h.history_rushing_yards
        - s.source_rushing_yards
        AS rushing_yard_difference,
    h.history_receiving_yards
        - s.source_receiving_yards
        AS receiving_yard_difference,
    CASE
        WHEN h.history_player_rows = s.source_player_rows
            AND ABS(
                h.history_fantasy_points_ppr
                - s.source_fantasy_points_ppr
            ) <= 0.01
            AND h.history_passing_yards
                = s.source_passing_yards
            AND h.history_rushing_yards
                = s.source_rushing_yards
            AND h.history_receiving_yards
                = s.source_receiving_yards
        THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM source_totals AS s
CROSS JOIN history_totals AS h;

-- ============================================================
-- 12. PLAYER HISTORY WINDOW PREFLIGHT
--
-- This confirms that season-week ordering also preserves true
-- chronological game-date ordering before it is used in model
-- features.
-- ============================================================

WITH player_windows AS (
    SELECT
        h.season,
        h.week,
        h.game_id,
        h.game_date,
        h.player_id,
        h.position,
        ROW_NUMBER() OVER (
            PARTITION BY h.player_id
            ORDER BY
                h.season,
                h.week,
                h.game_date,
                h.game_id
        ) - 1 AS prior_games_count,
        ROW_NUMBER() OVER (
            PARTITION BY
                h.player_id,
                h.season
            ORDER BY
                h.week,
                h.game_date,
                h.game_id
        ) - 1 AS prior_games_current_season,
        LAG(h.season) OVER (
            PARTITION BY h.player_id
            ORDER BY
                h.season,
                h.week,
                h.game_date,
                h.game_id
        ) AS previous_game_season,
        LAG(h.week) OVER (
            PARTITION BY h.player_id
            ORDER BY
                h.season,
                h.week,
                h.game_date,
                h.game_id
        ) AS previous_game_week,
        LAG(h.game_date) OVER (
            PARTITION BY h.player_id
            ORDER BY
                h.season,
                h.week,
                h.game_date,
                h.game_id
        ) AS previous_game_date
    FROM player_game_history AS h
)
SELECT
    COUNT(*) AS player_week_rows,
    SUM(prior_games_count = 0)
        AS first_observed_game_rows,
    SUM(prior_games_count >= 1)
        AS rows_with_previous_game,
    SUM(prior_games_count >= 3)
        AS rows_with_3_prior_games,
    SUM(prior_games_count >= 5)
        AS rows_with_5_prior_games,
    SUM(prior_games_current_season = 0)
        AS first_observed_game_of_season_rows,
    SUM(
        previous_game_season < season
    ) AS rows_using_prior_season_history,
    SUM(
        week = 1
        AND previous_game_season < season
    ) AS week_1_rows_with_prior_season_history,
    SUM(
        previous_game_date >= game_date
    ) AS nonchronological_previous_game_rows,
    SUM(
        previous_game_season = season
        AND previous_game_week >= week
    ) AS nonprior_same_season_week_rows,
    SUM(
        previous_game_season = season
        AND DATEDIFF(
            game_date,
            previous_game_date
        ) > 10
    ) AS same_season_rows_after_extended_gap,
    MIN(
        CASE
            WHEN previous_game_date IS NOT NULL
            THEN DATEDIFF(
                game_date,
                previous_game_date
            )
        END
    ) AS minimum_days_since_previous_game,
    MAX(
        CASE
            WHEN previous_game_date IS NOT NULL
            THEN DATEDIFF(
                game_date,
                previous_game_date
            )
        END
    ) AS maximum_days_since_previous_game
FROM player_windows;

-- ============================================================
-- 13. OPPONENT HISTORY WINDOW PREFLIGHT
-- ============================================================

WITH opponent_windows AS (
	select
		o.season,
        o.week,
        o.game_id,
        o.game_date,
        o.defensive_team,
        o.position,
        ROW_NUMBER() OVER (
            PARTITION BY
                o.defensive_team,
                o.position
            ORDER BY
                o.season,
                o.week,
                o.game_date,
                o.game_id
        ) - 1 AS prior_position_games,
        ROW_NUMBER() OVER (
            PARTITION BY
                o.defensive_team,
                o.position,
                o.season
            ORDER BY
                o.week,
                o.game_date,
                o.game_id
        ) - 1 AS prior_position_games_current_season,
        LAG(o.game_date) OVER (
            PARTITION BY
                o.defensive_team,
                o.position
            ORDER BY
                o.season,
                o.week,
                o.game_date,
                o.game_id
        ) AS previous_position_game_date
    FROM opponent_position_week_history AS o
)
SELECT
    COUNT(*) AS opponent_position_week_rows,
    SUM(prior_position_games = 0)
        AS first_observed_defense_position_rows,
    SUM(prior_position_games >= 1)
        AS rows_with_prior_defense_position_game,
    SUM(prior_position_games >= 3)
        AS rows_with_3_prior_defense_position_games,
    SUM(prior_position_games_current_season = 0)
        AS first_defense_position_row_of_season,
    SUM(
        previous_position_game_date >= game_date
    ) AS nonchronological_opponent_rows
FROM opponent_windows;

-- ============================================================
-- 14. TARGET ROW TO OPPONENT HISTORY COVERAGE
--
-- The same-week history row is used only as the anchor for
-- lagged windows. Its current values will not be predictors.
-- ============================================================

SELECT
    COUNT(*) AS player_week_rows,
    SUM(o.defensive_team IS NOT NULL)
        AS opponent_history_anchor_matched_rows,
    SUM(o.defensive_team IS NULL)
        AS opponent_history_anchor_unmatched_rows,
    ROUND(
        100.0
        * SUM(o.defensive_team IS NOT NULL)
        / COUNT(*),
        2
    ) AS opponent_history_anchor_match_pct
FROM player_game_history AS h
LEFT JOIN opponent_position_week_history AS o
    ON o.season = h.season
    AND o.week = h.week
    AND o.defensive_team = h.opponent
    AND o.position = h.position;

-- ============================================================
-- 15. CREATE FINAL MODEL PLAYER-WEEK TABLE
--
-- Grain: season + week + player_id
--
-- This step creates the empty schema only. The next section will
-- populate it with windows that end before each target game.
-- ============================================================

DROP TABLE IF EXISTS model_player_weeks;

CREATE TABLE model_player_weeks (
    season SMALLINT UNSIGNED NOT NULL,
    week TINYINT UNSIGNED NOT NULL,
    game_id VARCHAR(30) NOT NULL,
    game_date DATE NOT NULL,
    player_id VARCHAR(20) NOT NULL,
    player_name VARCHAR(100),
    player_display_name VARCHAR(150),
    position VARCHAR(10) NOT NULL,
    team VARCHAR(5) NOT NULL,
    opponent VARCHAR(5) NOT NULL,
    game_location VARCHAR(4) NOT NULL,
    is_home TINYINT(1) NOT NULL,
    team_rest SMALLINT,
    opponent_rest SMALLINT,
    source_spread_line DOUBLE,
    total_line DOUBLE,
    div_game TINYINT,
    roof VARCHAR(40),
    surface VARCHAR(60),
    target_fantasy_points_ppr DOUBLE NOT NULL,
    data_split VARCHAR(12) NOT NULL,
    feature_version VARCHAR(30) NOT NULL,
    prior_games_count INT NOT NULL,
    prior_games_current_season INT NOT NULL,
    previous_game_season SMALLINT UNSIGNED,
    previous_game_week TINYINT UNSIGNED,
    previous_game_date DATE,
    previous_team VARCHAR(5),
    days_since_previous_game INT,
    is_first_observed_game TINYINT(1) NOT NULL,
    is_first_observed_game_of_season TINYINT(1) NOT NULL,
    has_previous_game TINYINT(1) NOT NULL,
    has_3_prior_games TINYINT(1) NOT NULL,
    has_5_prior_games TINYINT(1) NOT NULL,
    team_changed_since_previous_game TINYINT(1) NOT NULL,
    fantasy_points_ppr_prev_game DOUBLE,
    fantasy_points_ppr_avg_last_3_games DOUBLE,
    fantasy_points_ppr_avg_last_5_games DOUBLE,
    fantasy_points_ppr_stddev_last_5_games DOUBLE,
    fantasy_points_ppr_min_last_5_games DOUBLE,
    fantasy_points_ppr_max_last_5_games DOUBLE,
    fantasy_points_ppr_season_to_date DOUBLE,
    fantasy_points_ppr_stddev_season_to_date DOUBLE,
    attempts_prev_game INT,
    attempts_avg_last_3_games DOUBLE,
    attempts_avg_last_5_games DOUBLE,
    attempts_season_to_date DOUBLE,
    carries_prev_game INT,
    carries_avg_last_3_games DOUBLE,
    carries_avg_last_5_games DOUBLE,
    carries_season_to_date DOUBLE,
    targets_prev_game INT,
    targets_avg_last_3_games DOUBLE,
    targets_avg_last_5_games DOUBLE,
    targets_season_to_date DOUBLE,
    receptions_prev_game INT,
    receptions_avg_last_3_games DOUBLE,
    receptions_avg_last_5_games DOUBLE,
    touches_prev_game INT,
    touches_avg_last_3_games DOUBLE,
    touches_avg_last_5_games DOUBLE,
    opportunities_prev_game INT,
    opportunities_avg_last_3_games DOUBLE,
    opportunities_avg_last_5_games DOUBLE,
    opportunities_season_to_date DOUBLE,
    passing_yards_prev_game INT,
    passing_yards_avg_last_3_games DOUBLE,
    rushing_yards_prev_game INT,
    rushing_yards_avg_last_3_games DOUBLE,
    receiving_yards_prev_game INT,
    receiving_yards_avg_last_3_games DOUBLE,
    yards_from_scrimmage_prev_game INT,
    yards_from_scrimmage_avg_last_3_games DOUBLE,
    total_offensive_tds_prev_game INT,
    total_offensive_tds_avg_last_3_games DOUBLE,
    target_share_prev_game DOUBLE,
    target_share_avg_last_3_games DOUBLE,
    target_share_avg_last_5_games DOUBLE,
    target_share_season_to_date DOUBLE,
    air_yards_share_prev_game DOUBLE,
    air_yards_share_avg_last_3_games DOUBLE,
    air_yards_share_avg_last_5_games DOUBLE,
    wopr_prev_game DOUBLE,
    wopr_avg_last_3_games DOUBLE,
    wopr_avg_last_5_games DOUBLE,
    has_previous_snap_record TINYINT(1) NOT NULL,
    snap_records_last_3_games INT NOT NULL,
    snap_records_last_5_games INT NOT NULL,
    offense_snaps_prev_game DOUBLE,
    offense_snaps_avg_last_3_games DOUBLE,
    offense_snaps_avg_last_5_games DOUBLE,
    offense_pct_prev_game DOUBLE,
    offense_pct_avg_last_3_games DOUBLE,
    offense_pct_avg_last_5_games DOUBLE,
    completion_pct_avg_last_3_games DOUBLE,
    passing_yards_per_attempt_avg_last_3_games DOUBLE,
    rushing_yards_per_carry_avg_last_3_games DOUBLE,
    receiving_yards_per_target_avg_last_3_games DOUBLE,
    receiving_yards_per_reception_avg_last_3_games DOUBLE,
    fantasy_points_per_opportunity_avg_last_3_games DOUBLE,
    total_yards_per_opportunity_avg_last_3_games DOUBLE,
    opponent_prior_position_games INT NOT NULL,
    opponent_prior_position_games_current_season INT NOT NULL,
    has_opponent_history TINYINT(1) NOT NULL,
    opp_ppr_allowed_prev_game DOUBLE,
    opp_ppr_allowed_avg_last_3_games DOUBLE,
    opp_ppr_allowed_avg_last_5_games DOUBLE,
    opp_ppr_allowed_season_to_date DOUBLE,
    opp_opportunities_allowed_prev_game INT,
    opp_opportunities_allowed_avg_last_3_games DOUBLE,
    opp_opportunities_allowed_season_to_date DOUBLE,
    opp_passing_yards_allowed_season_to_date DOUBLE,
    opp_rushing_yards_allowed_season_to_date DOUBLE,
    opp_receiving_yards_allowed_season_to_date DOUBLE,
    opp_offensive_tds_allowed_season_to_date DOUBLE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (
        season,
        week,
        player_id
    ),
    UNIQUE KEY uq_model_player_game (
        game_id,
        player_id
    ),
    INDEX idx_model_player_weeks_player (
        player_id,
        season,
        week
    ),
    INDEX idx_model_player_weeks_position (
        position,
        season,
        week
    ),
    INDEX idx_model_player_weeks_split (
        data_split,
        position,
        season,
        week
    ),
    INDEX idx_model_player_weeks_opponent (
        opponent,
        position,
        season,
        week
    ),
    CONSTRAINT chk_model_player_weeks_position
        CHECK (position IN ('QB', 'RB', 'WR', 'TE')),
    CONSTRAINT chk_model_player_weeks_week
        CHECK (week BETWEEN 1 AND 18),
    CONSTRAINT chk_model_player_weeks_location
        CHECK (game_location IN ('HOME', 'AWAY')),
    CONSTRAINT chk_model_player_weeks_is_home
        CHECK (is_home IN (0, 1)),
    CONSTRAINT chk_model_player_weeks_split
        CHECK (
            data_split IN ('training', 'validation', 'test')
        ),
    CONSTRAINT chk_model_player_weeks_history_counts
        CHECK (
            prior_games_count >= 0
            AND prior_games_current_season >= 0
            AND prior_games_current_season
                <= prior_games_count
            AND opponent_prior_position_games >= 0
            AND opponent_prior_position_games_current_season >= 0
            AND opponent_prior_position_games_current_season
                <= opponent_prior_position_games
            AND snap_records_last_3_games >= 0
            AND snap_records_last_5_games >= 0
        ),
    CONSTRAINT chk_model_player_weeks_flags
        CHECK (
            is_first_observed_game IN (0, 1)
            AND is_first_observed_game_of_season IN (0, 1)
            AND has_previous_game IN (0, 1)
            AND has_3_prior_games IN (0, 1)
            AND has_5_prior_games IN (0, 1)
            AND team_changed_since_previous_game IN (0, 1)
            AND has_previous_snap_record IN (0, 1)
            AND has_opponent_history IN (0, 1)
        ),
    CONSTRAINT chk_model_player_weeks_previous_date
        CHECK (
            previous_game_date IS NULL
            OR previous_game_date < game_date
        ),
    CONSTRAINT chk_model_player_weeks_days_since
        CHECK (
            days_since_previous_game IS NULL
            OR days_since_previous_game > 0
        )
) ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;

SELECT
    TABLE_NAME AS table_name,
    COUNT(*) AS column_count
FROM information_schema.columns
WHERE table_schema = DATABASE()
AND table_name = 'model_player_weeks'
GROUP BY
    TABLE_NAME;

SELECT
    COUNT(*) AS initial_row_count
FROM model_player_weeks;

-- ============================================================
-- 16. POPULATE MODEL ROWS AND TEMPORAL ANCHORS
--
-- This first insert populates:
-- - Row identifiers
-- - Target values
-- - Pregame schedule context
-- - Player-history counts and flags
-- - Prior snap availability
-- - Opponent-history counts and flags
--
-- Nullable numerical feature columns are populated afterward.
-- ============================================================

TRUNCATE TABLE model_player_weeks;

INSERT INTO model_player_weeks (
    season,
    week,
    game_id,
    game_date,
    player_id,
    player_name,
    player_display_name,
    position,
    team,
    opponent,
    game_location,
    is_home,
    team_rest,
    opponent_rest,
    source_spread_line,
    total_line,
    div_game,
    roof,
    surface,
    target_fantasy_points_ppr,
    data_split,
    feature_version,
    prior_games_count,
    prior_games_current_season,
    previous_game_season,
    previous_game_week,
    previous_game_date,
    previous_team,
    days_since_previous_game,
    is_first_observed_game,
    is_first_observed_game_of_season,
    has_previous_game,
    has_3_prior_games,
    has_5_prior_games,
    team_changed_since_previous_game,
    has_previous_snap_record,
    snap_records_last_3_games,
    snap_records_last_5_games,
    opponent_prior_position_games,
    opponent_prior_position_games_current_season,
    has_opponent_history
)
SELECT
    p.season,
    p.week,
    p.game_id,
    p.game_date,
    p.player_id,
    p.player_name,
    p.player_display_name,
    p.position,
    p.team,
    p.opponent,
    p.game_location,
    p.is_home,
    p.team_rest,
    p.opponent_rest,
    p.source_spread_line,
    p.total_line,
    p.div_game,
    p.roof,
    p.surface,
    p.target_fantasy_points_ppr,
    p.data_split,
    'v1_prior_game',
    p.prior_games_count,
    p.prior_games_current_season,
    p.previous_game_season,
    p.previous_game_week,
    p.previous_game_date,
    p.previous_team,
    CASE
        WHEN p.previous_game_date IS NOT NULL
        THEN DATEDIFF(
            p.game_date,
            p.previous_game_date
        )
    END,
    CASE
        WHEN p.prior_games_count = 0 THEN 1
        ELSE 0
    END,
    CASE
        WHEN p.prior_games_current_season = 0 THEN 1
        ELSE 0
    END,
    CASE
        WHEN p.prior_games_count >= 1 THEN 1
        ELSE 0
    END,
    CASE
        WHEN p.prior_games_count >= 3 THEN 1
        ELSE 0
    END,
    CASE
        WHEN p.prior_games_count >= 5 THEN 1
        ELSE 0
    END,
    CASE
        WHEN p.previous_team IS NOT NULL
            AND p.previous_team <> p.team
        THEN 1
        ELSE 0
    END,
    CASE
        WHEN COALESCE(
            p.previous_game_has_snap_record,
            0
        ) = 1
        THEN 1
        ELSE 0
    END,
    COALESCE(
        p.snap_records_last_3_games,
        0
    ),
    COALESCE(
        p.snap_records_last_5_games,
        0
    ),
    o.opponent_prior_position_games,
    o.opponent_prior_position_games_current_season,
    CASE
        WHEN o.opponent_prior_position_games >= 1 THEN 1
        ELSE 0
    END
FROM (
    SELECT
        h.*,
        ROW_NUMBER() OVER (
            PARTITION BY h.player_id
            ORDER BY
                h.season,
                h.week,
                h.game_date,
                h.game_id
        ) - 1 AS prior_games_count,
        ROW_NUMBER() OVER (
            PARTITION BY
                h.player_id,
                h.season
            ORDER BY
                h.week,
                h.game_date,
                h.game_id
        ) - 1 AS prior_games_current_season,
        LAG(h.season) OVER (
            PARTITION BY h.player_id
            ORDER BY
                h.season,
                h.week,
                h.game_date,
                h.game_id
        ) AS previous_game_season,
        LAG(h.week) OVER (
            PARTITION BY h.player_id
            ORDER BY
                h.season,
                h.week,
                h.game_date,
                h.game_id
        ) AS previous_game_week,
        LAG(h.game_date) OVER (
            PARTITION BY h.player_id
            ORDER BY
                h.season,
                h.week,
                h.game_date,
                h.game_id
        ) AS previous_game_date,
        LAG(h.team) OVER (
            PARTITION BY h.player_id
            ORDER BY
                h.season,
                h.week,
                h.game_date,
                h.game_id
        ) AS previous_team,
        LAG(h.has_snap_record) OVER (
            PARTITION BY h.player_id
            ORDER BY
                h.season,
                h.week,
                h.game_date,
                h.game_id
        ) AS previous_game_has_snap_record,
        SUM(h.has_snap_record) OVER (
            PARTITION BY h.player_id
            ORDER BY
                h.season,
                h.week,
                h.game_date,
                h.game_id
            ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
        ) AS snap_records_last_3_games,
        SUM(h.has_snap_record) OVER (
            PARTITION BY h.player_id
            ORDER BY
                h.season,
                h.week,
                h.game_date,
                h.game_id
            ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
        ) AS snap_records_last_5_games
    FROM player_game_history AS h
) AS p
INNER JOIN (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY
                o.defensive_team,
                o.position
            ORDER BY
                o.season,
                o.week,
                o.game_date,
                o.game_id
        ) - 1 AS opponent_prior_position_games,
        ROW_NUMBER() OVER (
            PARTITION BY
                o.defensive_team,
                o.position,
                o.season
            ORDER BY
                o.week,
                o.game_date,
                o.game_id
        ) - 1
            AS opponent_prior_position_games_current_season
    FROM opponent_position_week_history AS o
) AS o
    ON o.season = p.season
    AND o.week = p.week
    AND o.defensive_team = p.opponent
    AND o.position = p.position;

-- ============================================================
-- 17. MODEL ROW AND HISTORY-FLAG RECONCILIATION
-- ============================================================

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
    COUNT(*) - COUNT(
        DISTINCT CONCAT_WS(
            '|',
            season,
            week,
            player_id
        )
    ) AS duplicate_rows_above_grain,
    SUM(is_first_observed_game = 1)
        AS first_observed_game_rows,
    SUM(has_previous_game = 1)
        AS rows_with_previous_game,
    SUM(has_3_prior_games = 1)
        AS rows_with_3_prior_games,
    SUM(has_5_prior_games = 1)
        AS rows_with_5_prior_games,
    SUM(is_first_observed_game_of_season = 1)
        AS first_observed_game_of_season_rows,
    SUM(
        previous_game_date IS NOT NULL
        AND previous_game_date >= game_date
    ) AS nonchronological_previous_game_rows
FROM model_player_weeks;

SELECT
    position,
    COUNT(*) AS model_rows,
    SUM(has_previous_game = 1)
        AS rows_with_previous_game,
    SUM(has_3_prior_games = 1)
        AS rows_with_3_prior_games,
    SUM(has_5_prior_games = 1)
        AS rows_with_5_prior_games,
    SUM(has_previous_snap_record = 1)
        AS rows_with_previous_snap,
    SUM(has_opponent_history = 1)
        AS rows_with_opponent_history
FROM model_player_weeks
GROUP BY
    position
ORDER BY
    FIELD(position, 'QB', 'RB', 'WR', 'TE');

-- ============================================================
-- 18. POPULATE LAGGED PLAYER FEATURES
--
-- Every LAG uses the previous observed game.
-- Every rolling frame ends at 1 PRECEDING.
-- The target row is therefore excluded from every predictor.
-- ============================================================

UPDATE model_player_weeks AS m
INNER JOIN (
    SELECT
        h.season,
        h.week,
        h.player_id,
        LAG(h.target_fantasy_points_ppr)
            OVER w_player
            AS fantasy_points_ppr_prev_game,
        AVG(h.target_fantasy_points_ppr)
            OVER w_last_3
            AS fantasy_points_ppr_avg_last_3_games,
        AVG(h.target_fantasy_points_ppr)
            OVER w_last_5
            AS fantasy_points_ppr_avg_last_5_games,
        STDDEV_SAMP(h.target_fantasy_points_ppr)
            OVER w_last_5
            AS fantasy_points_ppr_stddev_last_5_games,
        MIN(h.target_fantasy_points_ppr)
            OVER w_last_5
            AS fantasy_points_ppr_min_last_5_games,
        MAX(h.target_fantasy_points_ppr)
            OVER w_last_5
            AS fantasy_points_ppr_max_last_5_games,
        AVG(h.target_fantasy_points_ppr)
            OVER w_season
            AS fantasy_points_ppr_season_to_date,
        STDDEV_SAMP(h.target_fantasy_points_ppr)
            OVER w_season
            AS fantasy_points_ppr_stddev_season_to_date,
        LAG(h.attempts)
            OVER w_player
            AS attempts_prev_game,
        AVG(h.attempts)
            OVER w_last_3
            AS attempts_avg_last_3_games,
        AVG(h.attempts)
            OVER w_last_5
            AS attempts_avg_last_5_games,
        AVG(h.attempts)
            OVER w_season
            AS attempts_season_to_date,
        LAG(h.carries)
            OVER w_player
            AS carries_prev_game,
        AVG(h.carries)
            OVER w_last_3
            AS carries_avg_last_3_games,
        AVG(h.carries)
            OVER w_last_5
            AS carries_avg_last_5_games,
        AVG(h.carries)
            OVER w_season
            AS carries_season_to_date,
        LAG(h.targets)
            OVER w_player
            AS targets_prev_game,
        AVG(h.targets)
            OVER w_last_3
            AS targets_avg_last_3_games,
        AVG(h.targets)
            OVER w_last_5
            AS targets_avg_last_5_games,
        AVG(h.targets)
            OVER w_season
            AS targets_season_to_date,
        LAG(h.receptions)
            OVER w_player
            AS receptions_prev_game,
        AVG(h.receptions)
            OVER w_last_3
            AS receptions_avg_last_3_games,
        AVG(h.receptions)
            OVER w_last_5
            AS receptions_avg_last_5_games,
        LAG(h.touches)
            OVER w_player
            AS touches_prev_game,
        AVG(h.touches)
            OVER w_last_3
            AS touches_avg_last_3_games,
        AVG(h.touches)
            OVER w_last_5
            AS touches_avg_last_5_games,
        LAG(h.position_adjusted_opportunities)
            OVER w_player
            AS opportunities_prev_game,
        AVG(h.position_adjusted_opportunities)
            OVER w_last_3
            AS opportunities_avg_last_3_games,
        AVG(h.position_adjusted_opportunities)
            OVER w_last_5
            AS opportunities_avg_last_5_games,
        AVG(h.position_adjusted_opportunities)
            OVER w_season
            AS opportunities_season_to_date,
        LAG(h.passing_yards)
            OVER w_player
            AS passing_yards_prev_game,
        AVG(h.passing_yards)
            OVER w_last_3
            AS passing_yards_avg_last_3_games,
        LAG(h.rushing_yards)
            OVER w_player
            AS rushing_yards_prev_game,
        AVG(h.rushing_yards)
            OVER w_last_3
            AS rushing_yards_avg_last_3_games,
        LAG(h.receiving_yards)
            OVER w_player
            AS receiving_yards_prev_game,
        AVG(h.receiving_yards)
            OVER w_last_3
            AS receiving_yards_avg_last_3_games,
        LAG(h.yards_from_scrimmage)
            OVER w_player
            AS yards_from_scrimmage_prev_game,
        AVG(h.yards_from_scrimmage)
            OVER w_last_3
            AS yards_from_scrimmage_avg_last_3_games,
        LAG(h.total_offensive_tds)
            OVER w_player
            AS total_offensive_tds_prev_game,
        AVG(h.total_offensive_tds)
            OVER w_last_3
            AS total_offensive_tds_avg_last_3_games,
        LAG(h.target_share)
            OVER w_player
            AS target_share_prev_game,
        AVG(h.target_share)
            OVER w_last_3
            AS target_share_avg_last_3_games,
        AVG(h.target_share)
            OVER w_last_5
            AS target_share_avg_last_5_games,
        AVG(h.target_share)
            OVER w_season
            AS target_share_season_to_date,
        LAG(h.air_yards_share)
            OVER w_player
            AS air_yards_share_prev_game,
        AVG(h.air_yards_share)
            OVER w_last_3
            AS air_yards_share_avg_last_3_games,
        AVG(h.air_yards_share)
            OVER w_last_5
            AS air_yards_share_avg_last_5_games,
        LAG(h.wopr)
            OVER w_player
            AS wopr_prev_game,
        AVG(h.wopr)
            OVER w_last_3
            AS wopr_avg_last_3_games,
        AVG(h.wopr)
            OVER w_last_5
            AS wopr_avg_last_5_games,
        LAG(h.offense_snaps)
            OVER w_player
            AS offense_snaps_prev_game,
        AVG(h.offense_snaps)
            OVER w_last_3
            AS offense_snaps_avg_last_3_games,
        AVG(h.offense_snaps)
            OVER w_last_5
            AS offense_snaps_avg_last_5_games,
        LAG(h.offense_pct)
            OVER w_player
            AS offense_pct_prev_game,
        AVG(h.offense_pct)
            OVER w_last_3
            AS offense_pct_avg_last_3_games,
        AVG(h.offense_pct)
            OVER w_last_5
            AS offense_pct_avg_last_5_games
    FROM player_game_history AS h
    WINDOW
        w_player AS (
            PARTITION BY h.player_id
            ORDER BY
                h.season,
                h.week,
                h.game_date,
                h.game_id
        ),
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
) AS f
    ON f.season = m.season
    AND f.week = m.week
    AND f.player_id = m.player_id
SET
    m.fantasy_points_ppr_prev_game =
        f.fantasy_points_ppr_prev_game,
    m.fantasy_points_ppr_avg_last_3_games =
        f.fantasy_points_ppr_avg_last_3_games,
    m.fantasy_points_ppr_avg_last_5_games =
        f.fantasy_points_ppr_avg_last_5_games,
    m.fantasy_points_ppr_stddev_last_5_games =
        f.fantasy_points_ppr_stddev_last_5_games,
    m.fantasy_points_ppr_min_last_5_games =
        f.fantasy_points_ppr_min_last_5_games,
    m.fantasy_points_ppr_max_last_5_games =
        f.fantasy_points_ppr_max_last_5_games,
    m.fantasy_points_ppr_season_to_date =
        f.fantasy_points_ppr_season_to_date,
    m.fantasy_points_ppr_stddev_season_to_date =
        f.fantasy_points_ppr_stddev_season_to_date,
    m.attempts_prev_game =
        f.attempts_prev_game,
    m.attempts_avg_last_3_games =
        f.attempts_avg_last_3_games,
    m.attempts_avg_last_5_games =
        f.attempts_avg_last_5_games,
    m.attempts_season_to_date =
        f.attempts_season_to_date,
    m.carries_prev_game =
        f.carries_prev_game,
    m.carries_avg_last_3_games =
        f.carries_avg_last_3_games,
    m.carries_avg_last_5_games =
        f.carries_avg_last_5_games,
    m.carries_season_to_date =
        f.carries_season_to_date,
    m.targets_prev_game =
        f.targets_prev_game,
    m.targets_avg_last_3_games =
        f.targets_avg_last_3_games,
    m.targets_avg_last_5_games =
        f.targets_avg_last_5_games,
    m.targets_season_to_date =
        f.targets_season_to_date,
    m.receptions_prev_game =
        f.receptions_prev_game,
    m.receptions_avg_last_3_games =
        f.receptions_avg_last_3_games,
    m.receptions_avg_last_5_games =
        f.receptions_avg_last_5_games,
    m.touches_prev_game =
        f.touches_prev_game,
    m.touches_avg_last_3_games =
        f.touches_avg_last_3_games,
    m.touches_avg_last_5_games =
        f.touches_avg_last_5_games,
    m.opportunities_prev_game =
        f.opportunities_prev_game,
    m.opportunities_avg_last_3_games =
        f.opportunities_avg_last_3_games,
    m.opportunities_avg_last_5_games =
        f.opportunities_avg_last_5_games,
    m.opportunities_season_to_date =
        f.opportunities_season_to_date,
    m.passing_yards_prev_game =
        f.passing_yards_prev_game,
    m.passing_yards_avg_last_3_games =
        f.passing_yards_avg_last_3_games,
    m.rushing_yards_prev_game =
        f.rushing_yards_prev_game,
    m.rushing_yards_avg_last_3_games =
        f.rushing_yards_avg_last_3_games,
    m.receiving_yards_prev_game =
        f.receiving_yards_prev_game,
    m.receiving_yards_avg_last_3_games =
        f.receiving_yards_avg_last_3_games,
    m.yards_from_scrimmage_prev_game =
        f.yards_from_scrimmage_prev_game,
    m.yards_from_scrimmage_avg_last_3_games =
        f.yards_from_scrimmage_avg_last_3_games,
    m.total_offensive_tds_prev_game =
        f.total_offensive_tds_prev_game,
    m.total_offensive_tds_avg_last_3_games =
        f.total_offensive_tds_avg_last_3_games,
    m.target_share_prev_game =
        f.target_share_prev_game,
    m.target_share_avg_last_3_games =
        f.target_share_avg_last_3_games,
    m.target_share_avg_last_5_games =
        f.target_share_avg_last_5_games,
    m.target_share_season_to_date =
        f.target_share_season_to_date,
    m.air_yards_share_prev_game =
        f.air_yards_share_prev_game,
    m.air_yards_share_avg_last_3_games =
        f.air_yards_share_avg_last_3_games,
    m.air_yards_share_avg_last_5_games =
        f.air_yards_share_avg_last_5_games,
    m.wopr_prev_game =
        f.wopr_prev_game,
    m.wopr_avg_last_3_games =
        f.wopr_avg_last_3_games,
    m.wopr_avg_last_5_games =
        f.wopr_avg_last_5_games,
    m.offense_snaps_prev_game =
        f.offense_snaps_prev_game,
    m.offense_snaps_avg_last_3_games =
        f.offense_snaps_avg_last_3_games,
    m.offense_snaps_avg_last_5_games =
        f.offense_snaps_avg_last_5_games,
    m.offense_pct_prev_game =
        f.offense_pct_prev_game,
    m.offense_pct_avg_last_3_games =
        f.offense_pct_avg_last_3_games,
    m.offense_pct_avg_last_5_games =
        f.offense_pct_avg_last_5_games;

-- ============================================================
-- 19. PLAYER FEATURE COMPLETENESS AND LAG RECONCILIATION
-- ============================================================

SELECT
    COUNT(*) AS model_rows,
    SUM(
        prior_games_count = 0
        AND (
            fantasy_points_ppr_prev_game IS NOT NULL
            OR fantasy_points_ppr_avg_last_3_games
                IS NOT NULL
            OR attempts_prev_game IS NOT NULL
            OR opportunities_prev_game IS NOT NULL
            OR target_share_prev_game IS NOT NULL
            OR offense_snaps_prev_game IS NOT NULL
        )
    ) AS first_game_rows_with_leaked_history,
    SUM(
        has_previous_game = 1
        AND fantasy_points_ppr_prev_game IS NULL
    ) AS missing_previous_ppr_when_expected,
    SUM(
        has_3_prior_games = 1
        AND fantasy_points_ppr_avg_last_3_games
            IS NULL
    ) AS missing_3_game_ppr_when_expected,
    SUM(
        has_5_prior_games = 1
        AND fantasy_points_ppr_avg_last_5_games
            IS NULL
    ) AS missing_5_game_ppr_when_expected,
    SUM(
        has_previous_snap_record = 1
        AND offense_pct_prev_game IS NULL
    ) AS missing_previous_snap_when_expected
FROM model_player_weeks;

SELECT
    COUNT(*) AS rows_with_previous_game,
    SUM(
        ABS(
            m.fantasy_points_ppr_prev_game
            - h.target_fantasy_points_ppr
        ) <= 0.01
    ) AS exact_previous_ppr_matches,
    SUM(
        ABS(
            m.fantasy_points_ppr_prev_game
            - h.target_fantasy_points_ppr
        ) > 0.01
    ) AS previous_ppr_mismatch_rows,
    MAX(
        ABS(
            m.fantasy_points_ppr_prev_game
            - h.target_fantasy_points_ppr
        )
    ) AS maximum_previous_ppr_difference
FROM model_player_weeks AS m
INNER JOIN player_game_history AS h
    ON h.season = m.previous_game_season
    AND h.week = m.previous_game_week
    AND h.player_id = m.player_id
WHERE m.has_previous_game = 1;

SELECT
    position,
    COUNT(*) AS model_rows,
    SUM(fantasy_points_ppr_prev_game IS NOT NULL)
        AS published_previous_ppr_rows,
    SUM(fantasy_points_ppr_avg_last_3_games IS NOT NULL)
        AS published_3_game_ppr_rows,
    SUM(fantasy_points_ppr_avg_last_5_games IS NOT NULL)
        AS published_5_game_ppr_rows,
    SUM(offense_pct_prev_game IS NOT NULL)
        AS published_previous_snap_pct_rows
FROM model_player_weeks
GROUP BY
    position
ORDER BY
    FIELD(position, 'QB', 'RB', 'WR', 'TE');

-- ============================================================
-- 20. POPULATE LAGGED EFFICIENCY FEATURES
--
-- Each ratio uses totals from the previous three observed games.
-- Rolling numerators and denominators are aggregated separately.
-- Zero denominators produce NULL.
--
-- completion_pct is stored as a decimal rate:
-- 0.6500 means 65.00%.
-- ============================================================

UPDATE model_player_weeks AS m
INNER JOIN (
    SELECT
        h.season,
        h.week,
        h.player_id,
        1E0 * SUM(h.completions) OVER w_last_3
            / NULLIF(
                SUM(h.attempts) OVER w_last_3,
                0
            )
            AS completion_pct_avg_last_3_games,
        1E0 * SUM(h.passing_yards) OVER w_last_3
            / NULLIF(
                SUM(h.attempts) OVER w_last_3,
                0
            )
            AS passing_yards_per_attempt_avg_last_3_games,
        1E0 * SUM(h.rushing_yards) OVER w_last_3
            / NULLIF(
                SUM(h.carries) OVER w_last_3,
                0
            )
            AS rushing_yards_per_carry_avg_last_3_games,
        1E0 * SUM(h.receiving_yards) OVER w_last_3
            / NULLIF(
                SUM(h.targets) OVER w_last_3,
                0
            )
            AS receiving_yards_per_target_avg_last_3_games,
        1E0 * SUM(h.receiving_yards) OVER w_last_3
            / NULLIF(
                SUM(h.receptions) OVER w_last_3,
                0
            )
            AS receiving_yards_per_reception_avg_last_3_games,
        SUM(h.target_fantasy_points_ppr) OVER w_last_3
            / NULLIF(
                SUM(
                    h.position_adjusted_opportunities
                ) OVER w_last_3,
                0
            )
            AS fantasy_points_per_opportunity_avg_last_3_games,
        1E0 * SUM(h.total_offensive_yards) OVER w_last_3
            / NULLIF(
                SUM(
                    h.position_adjusted_opportunities
                ) OVER w_last_3,
                0
            )
            AS total_yards_per_opportunity_avg_last_3_games
    FROM player_game_history AS h
    WINDOW w_last_3 AS (
        PARTITION BY h.player_id
        ORDER BY
            h.season,
            h.week,
            h.game_date,
            h.game_id
        ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
    )
) AS e
    ON e.season = m.season
    AND e.week = m.week
    AND e.player_id = m.player_id
SET
    m.completion_pct_avg_last_3_games =
        e.completion_pct_avg_last_3_games,
    m.passing_yards_per_attempt_avg_last_3_games =
        e.passing_yards_per_attempt_avg_last_3_games,
    m.rushing_yards_per_carry_avg_last_3_games =
        e.rushing_yards_per_carry_avg_last_3_games,
    m.receiving_yards_per_target_avg_last_3_games =
        e.receiving_yards_per_target_avg_last_3_games,
    m.receiving_yards_per_reception_avg_last_3_games =
        e.receiving_yards_per_reception_avg_last_3_games,
    m.fantasy_points_per_opportunity_avg_last_3_games =
        e.fantasy_points_per_opportunity_avg_last_3_games,
    m.total_yards_per_opportunity_avg_last_3_games =
        e.total_yards_per_opportunity_avg_last_3_games;

-- ============================================================
-- 21. VALIDATE EFFICIENCY FEATURES
-- ============================================================

WITH rolling_totals AS (
    SELECT
        h.season,
        h.week,
        h.player_id,
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
            AS total_yards_last_3
    FROM player_game_history AS h
    WINDOW w_last_3 AS (
        PARTITION BY h.player_id
        ORDER BY
            h.season,
            h.week,
            h.game_date,
            h.game_id
        ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
    )
),
expected AS (
    SELECT
        season,
        week,
        player_id,
        1E0 * completions_last_3
            / NULLIF(attempts_last_3, 0)
            AS expected_completion_pct,
        1E0 * passing_yards_last_3
            / NULLIF(attempts_last_3, 0)
            AS expected_passing_yards_per_attempt,
        1E0 * rushing_yards_last_3
            / NULLIF(carries_last_3, 0)
            AS expected_rushing_yards_per_carry,
        1E0 * receiving_yards_last_3
            / NULLIF(targets_last_3, 0)
            AS expected_receiving_yards_per_target,
        1E0 * receiving_yards_last_3
            / NULLIF(receptions_last_3, 0)
            AS expected_receiving_yards_per_reception,
        fantasy_points_last_3
            / NULLIF(opportunities_last_3, 0)
            AS expected_fantasy_points_per_opportunity,
        1E0 * total_yards_last_3
            / NULLIF(opportunities_last_3, 0)
            AS expected_total_yards_per_opportunity
    FROM rolling_totals
)
SELECT
    COUNT(*) AS model_rows,
    SUM(
        m.prior_games_count = 0
        AND (
            m.completion_pct_avg_last_3_games IS NOT NULL
            OR m.passing_yards_per_attempt_avg_last_3_games
                IS NOT NULL
            OR m.rushing_yards_per_carry_avg_last_3_games
                IS NOT NULL
            OR m.receiving_yards_per_target_avg_last_3_games
                IS NOT NULL
            OR m.receiving_yards_per_reception_avg_last_3_games
                IS NOT NULL
            OR m.fantasy_points_per_opportunity_avg_last_3_games
                IS NOT NULL
            OR m.total_yards_per_opportunity_avg_last_3_games
                IS NOT NULL
        )
    ) AS first_game_rows_with_leaked_efficiency,
    SUM(
        NOT (
            (
                m.completion_pct_avg_last_3_games IS NULL
                AND e.expected_completion_pct IS NULL
            )
            OR ABS(
                m.completion_pct_avg_last_3_games
                - e.expected_completion_pct
            ) <= 0.0000000001
        )
    ) AS completion_pct_mismatch_rows,
    SUM(
        NOT (
            (
                m.passing_yards_per_attempt_avg_last_3_games
                    IS NULL
                AND e.expected_passing_yards_per_attempt
                    IS NULL
            )
            OR ABS(
                m.passing_yards_per_attempt_avg_last_3_games
                - e.expected_passing_yards_per_attempt
            ) <= 0.0000000001
        )
    ) AS passing_efficiency_mismatch_rows,
    SUM(
        NOT (
            (
                m.rushing_yards_per_carry_avg_last_3_games
                    IS NULL
                AND e.expected_rushing_yards_per_carry
                    IS NULL
            )
            OR ABS(
                m.rushing_yards_per_carry_avg_last_3_games
                - e.expected_rushing_yards_per_carry
            ) <= 0.0000000001
        )
    ) AS rushing_efficiency_mismatch_rows,
    SUM(
        NOT (
            (
                m.receiving_yards_per_target_avg_last_3_games
                    IS NULL
                AND e.expected_receiving_yards_per_target
                    IS NULL
            )
            OR ABS(
                m.receiving_yards_per_target_avg_last_3_games
                - e.expected_receiving_yards_per_target
            ) <= 0.0000000001
        )
    ) AS receiving_target_efficiency_mismatch_rows,
    SUM(
        NOT (
            (
                m.receiving_yards_per_reception_avg_last_3_games
                    IS NULL
                AND e.expected_receiving_yards_per_reception
                    IS NULL
            )
            OR ABS(
                m.receiving_yards_per_reception_avg_last_3_games
                - e.expected_receiving_yards_per_reception
            ) <= 0.0000000001
        )
    ) AS receiving_reception_efficiency_mismatch_rows,
    SUM(
        NOT (
            (
                m.fantasy_points_per_opportunity_avg_last_3_games
                    IS NULL
                AND e.expected_fantasy_points_per_opportunity
                    IS NULL
            )
            OR ABS(
                m.fantasy_points_per_opportunity_avg_last_3_games
                - e.expected_fantasy_points_per_opportunity
            ) <= 0.0000000001
        )
    ) AS fantasy_efficiency_mismatch_rows,
    SUM(
        NOT (
            (
                m.total_yards_per_opportunity_avg_last_3_games
                    IS NULL
                AND e.expected_total_yards_per_opportunity
                    IS NULL
            )
            OR ABS(
                m.total_yards_per_opportunity_avg_last_3_games
                - e.expected_total_yards_per_opportunity
            ) <= 0.0000000001
        )
    ) AS total_yards_efficiency_mismatch_rows,
    SUM(
        m.completion_pct_avg_last_3_games < 0
        OR m.completion_pct_avg_last_3_games > 1
    ) AS completion_pct_out_of_range_rows
FROM model_player_weeks AS m
INNER JOIN expected AS e
    ON e.season = m.season
    AND e.week = m.week
    AND e.player_id = m.player_id;

SELECT
    position,
    COUNT(*) AS model_rows,
    SUM(has_3_prior_games = 1)
        AS rows_with_3_prior_games,
    SUM(completion_pct_avg_last_3_games IS NOT NULL)
        AS published_completion_pct_rows,
    SUM(
        passing_yards_per_attempt_avg_last_3_games
            IS NOT NULL
    ) AS published_passing_efficiency_rows,
    SUM(
        rushing_yards_per_carry_avg_last_3_games
            IS NOT NULL
    ) AS published_rushing_efficiency_rows,
    SUM(
        receiving_yards_per_target_avg_last_3_games
            IS NOT NULL
    ) AS published_receiving_target_efficiency_rows,
    SUM(
        receiving_yards_per_reception_avg_last_3_games
            IS NOT NULL
    ) AS published_receiving_reception_efficiency_rows,
    SUM(
        fantasy_points_per_opportunity_avg_last_3_games
            IS NOT NULL
    ) AS published_fantasy_efficiency_rows,
    SUM(
        total_yards_per_opportunity_avg_last_3_games
            IS NOT NULL
    ) AS published_total_yards_efficiency_rows
FROM model_player_weeks
GROUP BY
    position
ORDER BY
    FIELD(position, 'QB', 'RB', 'WR', 'TE');

-- ============================================================
-- 22. POPULATE LAGGED OPPONENT-STRENGTH FEATURES
--
-- The same-week opponent row is only the window anchor.
-- Every feature below ends at 1 PRECEDING, so the target
-- game is excluded.
--
-- Last-three and last-five features may cross a season
-- boundary. Season-to-date features reset each season.
-- ============================================================

UPDATE model_player_weeks AS m
INNER JOIN (
    SELECT
        o.season,
        o.week,
        o.defensive_team,
        o.position,
        LAG(o.fantasy_points_ppr_allowed)
            OVER w_opponent
            AS opp_ppr_allowed_prev_game,
        AVG(o.fantasy_points_ppr_allowed)
            OVER w_last_3
            AS opp_ppr_allowed_avg_last_3_games,
        AVG(o.fantasy_points_ppr_allowed)
            OVER w_last_5
            AS opp_ppr_allowed_avg_last_5_games,
        AVG(o.fantasy_points_ppr_allowed)
            OVER w_season
            AS opp_ppr_allowed_season_to_date,
        LAG(
            o.position_adjusted_opportunities_allowed
        ) OVER w_opponent
            AS opp_opportunities_allowed_prev_game,
        AVG(
            1E0
            * o.position_adjusted_opportunities_allowed
        ) OVER w_last_3
            AS opp_opportunities_allowed_avg_last_3_games,
        AVG(
            1E0
            * o.position_adjusted_opportunities_allowed
        ) OVER w_season
            AS opp_opportunities_allowed_season_to_date,
        AVG(
            1E0 * o.passing_yards_allowed
        ) OVER w_season
            AS opp_passing_yards_allowed_season_to_date,
        AVG(
            1E0 * o.rushing_yards_allowed
        ) OVER w_season
            AS opp_rushing_yards_allowed_season_to_date,
        AVG(
            1E0 * o.receiving_yards_allowed
        ) OVER w_season
            AS opp_receiving_yards_allowed_season_to_date,
        AVG(
            1E0 * o.total_offensive_tds_allowed
        ) OVER w_season
            AS opp_offensive_tds_allowed_season_to_date
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
) AS f
    ON f.season = m.season
    AND f.week = m.week
    AND f.defensive_team = m.opponent
    AND f.position = m.position
SET
    m.opp_ppr_allowed_prev_game =
        f.opp_ppr_allowed_prev_game,
    m.opp_ppr_allowed_avg_last_3_games =
        f.opp_ppr_allowed_avg_last_3_games,
    m.opp_ppr_allowed_avg_last_5_games =
        f.opp_ppr_allowed_avg_last_5_games,
    m.opp_ppr_allowed_season_to_date =
        f.opp_ppr_allowed_season_to_date,
    m.opp_opportunities_allowed_prev_game =
        f.opp_opportunities_allowed_prev_game,
    m.opp_opportunities_allowed_avg_last_3_games =
        f.opp_opportunities_allowed_avg_last_3_games,
    m.opp_opportunities_allowed_season_to_date =
        f.opp_opportunities_allowed_season_to_date,
    m.opp_passing_yards_allowed_season_to_date =
        f.opp_passing_yards_allowed_season_to_date,
    m.opp_rushing_yards_allowed_season_to_date =
        f.opp_rushing_yards_allowed_season_to_date,
    m.opp_receiving_yards_allowed_season_to_date =
        f.opp_receiving_yards_allowed_season_to_date,
    m.opp_offensive_tds_allowed_season_to_date =
        f.opp_offensive_tds_allowed_season_to_date;

-- ============================================================
-- 23. VALIDATE OPPONENT-STRENGTH FEATURES
-- ============================================================

SELECT
    COUNT(*) AS model_rows,
    SUM(
        opponent_prior_position_games = 0
        AND (
            opp_ppr_allowed_prev_game IS NOT NULL
            OR opp_ppr_allowed_avg_last_3_games IS NOT NULL
            OR opp_ppr_allowed_avg_last_5_games IS NOT NULL
            OR opp_opportunities_allowed_prev_game IS NOT NULL
        )
    ) AS first_opponent_rows_with_leaked_history,
    SUM(
        has_opponent_history = 1
        AND opp_ppr_allowed_prev_game IS NULL
    ) AS missing_previous_opponent_ppr_when_expected,
    SUM(
        opponent_prior_position_games >= 3
        AND opp_ppr_allowed_avg_last_3_games IS NULL
    ) AS missing_3_game_opponent_ppr_when_expected,
    SUM(
        opponent_prior_position_games >= 5
        AND opp_ppr_allowed_avg_last_5_games IS NULL
    ) AS missing_5_game_opponent_ppr_when_expected,
    SUM(
        opponent_prior_position_games_current_season = 0
        AND (
            opp_ppr_allowed_season_to_date IS NOT NULL
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
    ) AS first_season_rows_with_leaked_opponent_history,
    SUM(
        opponent_prior_position_games_current_season >= 1
        AND opp_ppr_allowed_season_to_date IS NULL
    ) AS missing_opponent_season_ppr_when_expected
FROM model_player_weeks;

WITH opponent_windows AS (
    SELECT
        o.season,
        o.week,
        o.game_id,
        o.game_date,
        o.defensive_team,
        o.position,
        LAG(o.game_id) OVER w_opponent
            AS previous_opponent_game_id,
        LAG(o.game_date) OVER w_opponent
            AS previous_opponent_game_date,
        LAG(o.fantasy_points_ppr_allowed)
            OVER w_opponent
            AS expected_previous_ppr_allowed
    FROM opponent_position_week_history AS o
    WINDOW w_opponent AS (
        PARTITION BY
            o.defensive_team,
            o.position
        ORDER BY
            o.season,
            o.week,
            o.game_date,
            o.game_id
    )
)
SELECT
    COUNT(*) AS rows_with_opponent_history,
    SUM(
        ABS(
            m.opp_ppr_allowed_prev_game
            - o.expected_previous_ppr_allowed
        ) <= 0.0000000001
    ) AS exact_previous_opponent_ppr_matches,
    SUM(
        ABS(
            m.opp_ppr_allowed_prev_game
            - o.expected_previous_ppr_allowed
        ) > 0.0000000001
    ) AS previous_opponent_ppr_mismatch_rows,
    SUM(
        o.previous_opponent_game_id = m.game_id
    ) AS rows_using_target_game_as_previous_history,
    SUM(
        o.previous_opponent_game_date >= m.game_date
    ) AS nonprior_opponent_history_rows,
    MAX(
        o.previous_opponent_game_date
    ) AS maximum_previous_opponent_game_date,
    MAX(m.game_date) AS maximum_target_game_date
FROM model_player_weeks AS m
INNER JOIN opponent_windows AS o
    ON o.season = m.season
    AND o.week = m.week
    AND o.defensive_team = m.opponent
    AND o.position = m.position
WHERE m.has_opponent_history = 1;

SELECT
    position,
    COUNT(*) AS model_rows,
    SUM(has_opponent_history = 1)
        AS rows_with_opponent_history,
    SUM(
        opponent_prior_position_games_current_season >= 1
    ) AS rows_with_current_season_opponent_history,
    SUM(opp_ppr_allowed_prev_game IS NOT NULL)
        AS published_previous_opponent_ppr_rows,
    SUM(
        opp_ppr_allowed_avg_last_3_games IS NOT NULL
    ) AS published_3_game_opponent_ppr_rows,
    SUM(
        opp_ppr_allowed_avg_last_5_games IS NOT NULL
    ) AS published_5_game_opponent_ppr_rows,
    SUM(
        opp_ppr_allowed_season_to_date IS NOT NULL
    ) AS published_season_opponent_ppr_rows,
    SUM(
        opp_opportunities_allowed_season_to_date
            IS NOT NULL
    ) AS published_season_opponent_opportunity_rows
FROM model_player_weeks
GROUP BY
    position
ORDER BY
    FIELD(position, 'QB', 'RB', 'WR', 'TE');

-- ============================================================
-- 24. FINAL MODEL FEATURE-TABLE RECONCILIATION
-- ============================================================

WITH source_counts AS (
    SELECT
        COUNT(*) AS source_player_week_rows
    FROM player_weeks
)
SELECT
    COUNT(*) AS model_rows,
    MAX(sc.source_player_week_rows)
        AS source_player_week_rows,
    COUNT(
        DISTINCT CONCAT_WS(
            '|',
            m.season,
            m.week,
            m.player_id
        )
    ) AS distinct_model_keys,
    COUNT(*) - COUNT(
        DISTINCT CONCAT_WS(
            '|',
            m.season,
            m.week,
            m.player_id
        )
    ) AS duplicate_rows_above_grain,
    SUM(pw.player_id IS NULL)
        AS unmatched_source_player_rows,
    SUM(
        pw.player_id IS NOT NULL
        AND ABS(
            m.target_fantasy_points_ppr
            - pw.fantasy_points_ppr
        ) > 0.0000000001
    ) AS target_mismatch_rows,
    SUM(
        m.feature_version <> 'v1_prior_game'
    ) AS unexpected_feature_version_rows,
    CASE
        WHEN COUNT(*) = MAX(sc.source_player_week_rows)
            AND COUNT(*) = COUNT(
                DISTINCT CONCAT_WS(
                    '|',
                    m.season,
                    m.week,
                    m.player_id
                )
            )
            AND SUM(pw.player_id IS NULL) = 0
            AND SUM(
                pw.player_id IS NOT NULL
                AND ABS(
                    m.target_fantasy_points_ppr
                    - pw.fantasy_points_ppr
                ) > 0.0000000001
            ) = 0
            AND SUM(
                m.feature_version <> 'v1_prior_game'
            ) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM model_player_weeks AS m
LEFT JOIN player_weeks AS pw
    ON pw.season = m.season
    AND pw.week = m.week
    AND pw.player_id = m.player_id
CROSS JOIN source_counts AS sc;

WITH split_check AS (
    SELECT
        season,
        data_split,
        CASE
            WHEN season BETWEEN 2018 AND 2023
                THEN 'training'
            WHEN season = 2024
                THEN 'validation'
            WHEN season = 2025
                THEN 'test'
        END AS expected_split
    FROM model_player_weeks
)
SELECT
    season,
    expected_split,

    GROUP_CONCAT(
        DISTINCT data_split
        ORDER BY data_split
    ) AS observed_splits,
    COUNT(*) AS model_rows,
    SUM(data_split <> expected_split)
        AS split_mismatch_rows,
    CASE
        WHEN SUM(data_split <> expected_split) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM split_check
GROUP BY
    season,
    expected_split
ORDER BY
    season;

SELECT
    COUNT(*) AS model_rows,
    SUM(
        is_first_observed_game
            <> (prior_games_count = 0)
    ) AS first_game_flag_mismatch_rows,
    SUM(
        has_previous_game
            <> (prior_games_count >= 1)
    ) AS previous_game_flag_mismatch_rows,
    SUM(
        has_3_prior_games
            <> (prior_games_count >= 3)
    ) AS three_game_flag_mismatch_rows,
    SUM(
        has_5_prior_games
            <> (prior_games_count >= 5)
    ) AS five_game_flag_mismatch_rows,
    SUM(
        is_first_observed_game_of_season
            <> (prior_games_current_season = 0)
    ) AS first_season_game_flag_mismatch_rows,
    SUM(
        has_opponent_history
            <> (opponent_prior_position_games >= 1)
    ) AS opponent_history_flag_mismatch_rows,
    SUM(
        previous_game_date IS NOT NULL
        AND previous_game_date >= game_date
    ) AS nonprior_player_history_rows,
    SUM(
        prior_games_count = 0
        AND (
            fantasy_points_ppr_prev_game IS NOT NULL
            OR fantasy_points_ppr_avg_last_3_games
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
    ) AS first_game_rows_with_player_feature_leakage,
    SUM(
        prior_games_current_season = 0
        AND (
            fantasy_points_ppr_season_to_date
                IS NOT NULL
            OR attempts_season_to_date IS NOT NULL
            OR carries_season_to_date IS NOT NULL
            OR targets_season_to_date IS NOT NULL
            OR opportunities_season_to_date IS NOT NULL
            OR target_share_season_to_date IS NOT NULL
        )
    ) AS first_season_game_rows_with_player_feature_leakage,
    SUM(
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
    ) AS first_opponent_rows_with_feature_leakage,
    SUM(
        opponent_prior_position_games_current_season = 0
        AND (
            opp_ppr_allowed_season_to_date IS NOT NULL
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
    ) AS first_opponent_season_rows_with_feature_leakage,
    SUM(
        prior_games_count < 0
        OR prior_games_current_season < 0
        OR opponent_prior_position_games < 0
        OR opponent_prior_position_games_current_season < 0
        OR snap_records_last_3_games < 0
        OR snap_records_last_5_games < 0
    ) AS invalid_history_count_rows
FROM model_player_weeks;

SELECT
    season,
    position,
    COUNT(*) AS model_rows,
    SUM(has_previous_game = 1)
        AS rows_with_previous_game,
    SUM(has_3_prior_games = 1)
        AS rows_with_3_prior_games,
    SUM(has_5_prior_games = 1)
        AS rows_with_5_prior_games,
    ROUND(
        100.0
        * SUM(has_previous_game = 1)
        / COUNT(*),
        2
    ) AS previous_game_coverage_pct,
    SUM(
        fantasy_points_ppr_prev_game IS NOT NULL
    ) AS published_previous_ppr_rows,
    SUM(
        offense_pct_prev_game IS NOT NULL
    ) AS published_previous_snap_pct_rows,
    SUM(
        fantasy_points_per_opportunity_avg_last_3_games
            IS NOT NULL
    ) AS published_fantasy_efficiency_rows,
    SUM(has_opponent_history = 1)
        AS rows_with_opponent_history,
    SUM(
        opp_ppr_allowed_prev_game IS NOT NULL
    ) AS published_previous_opponent_ppr_rows,
    SUM(
        opp_ppr_allowed_season_to_date IS NOT NULL
    ) AS published_season_opponent_ppr_rows
FROM model_player_weeks
GROUP BY
    season,
    position
ORDER BY
    season,
    FIELD(position, 'QB', 'RB', 'WR', 'TE');