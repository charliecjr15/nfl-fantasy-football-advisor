USE nfl_fantasy_advisor;

-- ============================================================
-- CLEAN ANALYTICAL LAYER
--
-- This script rebuilds derived clean tables from the reproducible
-- stg_ tables. It does not delete or modify staging data.
-- ============================================================

DROP TABLE IF EXISTS depth_chart_snapshots;
DROP TABLE IF EXISTS depth_chart_legacy_weeks;
DROP TABLE IF EXISTS snap_player_weeks;
DROP TABLE IF EXISTS injury_player_weeks;
DROP TABLE IF EXISTS player_week_id_crosswalk;
DROP TABLE IF EXISTS players;
DROP TABLE IF EXISTS roster_player_weeks;
DROP TABLE IF EXISTS player_weeks;
DROP TABLE IF EXISTS team_weeks;
DROP TABLE IF EXISTS games;


-- ============================================================
-- 1. GAMES
-- Grain: one regular-season NFL game
-- Expected rows: 2,127
-- ============================================================

CREATE TABLE games (
    game_id VARCHAR(30) NOT NULL,
    season SMALLINT UNSIGNED NOT NULL,
    game_type VARCHAR(10) NOT NULL,
    week TINYINT UNSIGNED NOT NULL,
    game_date DATE NOT NULL,
    weekday VARCHAR(12),
    game_time TIME,
    away_team VARCHAR(5) NOT NULL,
    away_score INT,
    home_team VARCHAR(5) NOT NULL,
    home_score INT,
    location VARCHAR(30),
    result INT,
    total INT,
    overtime TINYINT,
    away_rest SMALLINT,
    home_rest SMALLINT,
    spread_line DOUBLE,
    total_line DOUBLE,
    div_game TINYINT,
    roof VARCHAR(40),
    surface VARCHAR(60),
    temp INT,
    wind INT,
    stadium_id VARCHAR(30),
    stadium VARCHAR(200),
    data_split VARCHAR(12) NOT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (game_id),
    UNIQUE KEY uq_games_matchup (
        season,
        week,
        away_team,
        home_team
    ),
    INDEX idx_games_season_week (season, week),
    INDEX idx_games_away_team (away_team, season, week),
    INDEX idx_games_home_team (home_team, season, week),

    CONSTRAINT chk_games_split
        CHECK (
            data_split IN ('training', 'validation', 'test')
        ),
    CONSTRAINT chk_games_week
        CHECK (week BETWEEN 1 AND 18)
) ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


INSERT INTO games (
    game_id,
    season,
    game_type,
    week,
    game_date,
    weekday,
    game_time,
    away_team,
    away_score,
    home_team,
    home_score,
    location,
    result,
    total,
    overtime,
    away_rest,
    home_rest,
    spread_line,
    total_line,
    div_game,
    roof,
    surface,
    temp,
    wind,
    stadium_id,
    stadium,
    data_split
)
SELECT
    TRIM(game_id),
    season,
    TRIM(game_type),
    week,
    gameday,
    NULLIF(TRIM(weekday), ''),
    gametime,
    TRIM(away_team),
    away_score,
    TRIM(home_team),
    home_score,
    NULLIF(TRIM(location), ''),
    result,
    total,
    overtime,
    away_rest,
    home_rest,
    spread_line,
    total_line,
    div_game,
    NULLIF(TRIM(roof), ''),
    NULLIF(TRIM(surface), ''),
    temp,
    wind,
    NULLIF(TRIM(stadium_id), ''),
    NULLIF(TRIM(stadium), ''),
    TRIM(data_split)
FROM stg_schedules;


-- ============================================================
-- 2. TEAM WEEKS
-- Grain: one team per regular-season game week
-- Expected rows: 4,254
--
-- spread_line is preserved as the source game-level spread.
-- It is not yet renamed or interpreted as a team-relative spread.
-- ============================================================

CREATE TABLE team_weeks (
    season SMALLINT UNSIGNED NOT NULL,
    week TINYINT UNSIGNED NOT NULL,
    team VARCHAR(5) NOT NULL,
    game_id VARCHAR(30) NOT NULL,
    opponent VARCHAR(5) NOT NULL,
    game_location VARCHAR(4) NOT NULL,
    is_home TINYINT(1) NOT NULL,
    game_date DATE NOT NULL,
    game_time TIME,
    points_for INT,
    points_against INT,
    result_margin INT,
    team_rest SMALLINT,
    opponent_rest SMALLINT,
    source_spread_line DOUBLE,
    total_line DOUBLE,
    overtime TINYINT,
    div_game TINYINT,
    roof VARCHAR(40),
    surface VARCHAR(60),
    temp INT,
    wind INT,
    stadium_id VARCHAR(30),
    stadium VARCHAR(200),
    data_split VARCHAR(12) NOT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (season, week, team),
    UNIQUE KEY uq_team_weeks_game_team (game_id, team),
    INDEX idx_team_weeks_game (game_id),
    INDEX idx_team_weeks_opponent (
        opponent,
        season,
        week
    ),

    CONSTRAINT chk_team_weeks_location
        CHECK (game_location IN ('HOME', 'AWAY')),
    CONSTRAINT chk_team_weeks_is_home
        CHECK (is_home IN (0, 1)),
    CONSTRAINT chk_team_weeks_split
        CHECK (
            data_split IN ('training', 'validation', 'test')
        )
) ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


INSERT INTO team_weeks (
    season,
    week,
    team,
    game_id,
    opponent,
    game_location,
    is_home,
    game_date,
    game_time,
    points_for,
    points_against,
    result_margin,
    team_rest,
    opponent_rest,
    source_spread_line,
    total_line,
    overtime,
    div_game,
    roof,
    surface,
    temp,
    wind,
    stadium_id,
    stadium,
    data_split
)
SELECT
    season,
    week,
    home_team,
    game_id,
    away_team,
    'HOME',
    1,
    game_date,
    game_time,
    home_score,
    away_score,
    home_score - away_score,
    home_rest,
    away_rest,
    spread_line,
    total_line,
    overtime,
    div_game,
    roof,
    surface,
    temp,
    wind,
    stadium_id,
    stadium,
    data_split
FROM games

UNION ALL

SELECT
    season,
    week,
    away_team,
    game_id,
    home_team,
    'AWAY',
    0,
    game_date,
    game_time,
    away_score,
    home_score,
    away_score - home_score,
    away_rest,
    home_rest,
    spread_line,
    total_line,
    overtime,
    div_game,
    roof,
    surface,
    temp,
    wind,
    stadium_id,
    stadium,
    data_split
FROM games;


-- ============================================================
-- 3. CORE PLAYER WEEKS
-- Grain: one QB, RB, WR, or TE per regular-season week
-- Expected rows: 45,693
--
-- fantasy_points_ppr is the observed outcome for that week.
-- It must be shifted forward before it becomes a model target.
-- ============================================================

CREATE TABLE player_weeks (
    player_id VARCHAR(20) NOT NULL,
    player_name VARCHAR(100),
    player_display_name VARCHAR(150),
    position VARCHAR(10) NOT NULL,
    position_group VARCHAR(20),
    headshot_url VARCHAR(1000),

    season SMALLINT UNSIGNED NOT NULL,
    week TINYINT UNSIGNED NOT NULL,
    season_type VARCHAR(10) NOT NULL,
    game_id VARCHAR(30) NOT NULL,
    team VARCHAR(5) NOT NULL,
    opponent_team VARCHAR(5) NOT NULL,

    completions INT,
    attempts INT,
    passing_yards INT,
    passing_tds INT,
    passing_interceptions INT,
    sacks_suffered INT,
    sack_yards_lost INT,
    sack_fumbles INT,
    sack_fumbles_lost INT,
    passing_air_yards INT,
    passing_yards_after_catch INT,
    passing_first_downs INT,
    passing_epa DOUBLE,
    passing_cpoe DOUBLE,
    passing_2pt_conversions INT,

    carries INT,
    rushing_yards INT,
    rushing_tds INT,
    rushing_fumbles INT,
    rushing_fumbles_lost INT,
    rushing_first_downs INT,
    rushing_epa DOUBLE,
    rushing_2pt_conversions INT,

    receptions INT,
    targets INT,
    receiving_yards INT,
    receiving_tds INT,
    receiving_fumbles INT,
    receiving_fumbles_lost INT,
    receiving_air_yards INT,
    receiving_yards_after_catch INT,
    receiving_first_downs INT,
    receiving_epa DOUBLE,
    receiving_2pt_conversions INT,

    target_share DOUBLE,
    air_yards_share DOUBLE,
    wopr DOUBLE,
    special_teams_tds INT,
    fumbles_lost_total INT,

    fantasy_points DOUBLE,
    fantasy_points_ppr DOUBLE,
    calculated_fantasy_points_ppr DOUBLE,
    fantasy_point_difference DOUBLE,
    data_split VARCHAR(12) NOT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (season, week, player_id),
    UNIQUE KEY uq_player_weeks_game_player (
        game_id,
        player_id
    ),
    INDEX idx_player_weeks_player (
        player_id,
        season,
        week
    ),
    INDEX idx_player_weeks_team (
        team,
        season,
        week
    ),
    INDEX idx_player_weeks_position (
        position,
        season,
        week
    ),
    INDEX idx_player_weeks_game (game_id),

    CONSTRAINT chk_player_weeks_position
        CHECK (position IN ('QB', 'RB', 'WR', 'TE')),
    CONSTRAINT chk_player_weeks_season_type
        CHECK (season_type = 'REG'),
    CONSTRAINT chk_player_weeks_split
        CHECK (
            data_split IN ('training', 'validation', 'test')
        ),
    CONSTRAINT chk_player_weeks_week
        CHECK (week BETWEEN 1 AND 18)
) ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


INSERT INTO player_weeks (
    player_id,
    player_name,
    player_display_name,
    position,
    position_group,
    headshot_url,
    season,
    week,
    season_type,
    game_id,
    team,
    opponent_team,
    completions,
    attempts,
    passing_yards,
    passing_tds,
    passing_interceptions,
    sacks_suffered,
    sack_yards_lost,
    sack_fumbles,
    sack_fumbles_lost,
    passing_air_yards,
    passing_yards_after_catch,
    passing_first_downs,
    passing_epa,
    passing_cpoe,
    passing_2pt_conversions,
    carries,
    rushing_yards,
    rushing_tds,
    rushing_fumbles,
    rushing_fumbles_lost,
    rushing_first_downs,
    rushing_epa,
    rushing_2pt_conversions,
    receptions,
    targets,
    receiving_yards,
    receiving_tds,
    receiving_fumbles,
    receiving_fumbles_lost,
    receiving_air_yards,
    receiving_yards_after_catch,
    receiving_first_downs,
    receiving_epa,
    receiving_2pt_conversions,
    target_share,
    air_yards_share,
    wopr,
    special_teams_tds,
    fumbles_lost_total,
    fantasy_points,
    fantasy_points_ppr,
    calculated_fantasy_points_ppr,
    fantasy_point_difference,
    data_split
)
SELECT
    TRIM(player_id),
    NULLIF(TRIM(player_name), ''),
    NULLIF(TRIM(player_display_name), ''),
    TRIM(position),
    NULLIF(TRIM(position_group), ''),
    NULLIF(TRIM(headshot_url), ''),
    season,
    week,
    TRIM(season_type),
    TRIM(game_id),
    TRIM(team),
    TRIM(opponent_team),
    completions,
    attempts,
    passing_yards,
    passing_tds,
    passing_interceptions,
    sacks_suffered,
    sack_yards_lost,
    sack_fumbles,
    sack_fumbles_lost,
    passing_air_yards,
    passing_yards_after_catch,
    passing_first_downs,
    passing_epa,
    passing_cpoe,
    passing_2pt_conversions,
    carries,
    rushing_yards,
    rushing_tds,
    rushing_fumbles,
    rushing_fumbles_lost,
    rushing_first_downs,
    rushing_epa,
    rushing_2pt_conversions,
    receptions,
    targets,
    receiving_yards,
    receiving_tds,
    receiving_fumbles,
    receiving_fumbles_lost,
    receiving_air_yards,
    receiving_yards_after_catch,
    receiving_first_downs,
    receiving_epa,
    receiving_2pt_conversions,
    target_share,
    air_yards_share,
    wopr,
    special_teams_tds,
    fumbles_lost_total,
    fantasy_points,
    fantasy_points_ppr,
    calculated_fantasy_points_ppr,
    fantasy_point_difference,
    TRIM(data_split)
FROM stg_weekly_player_stats;

-- ============================================================
-- 4. WEEKLY ROSTERS
-- Grain: one player-team roster record per regular-season week
-- Expected rows: 362,828
--
-- Rows without a usable GSIS player ID are excluded because they
-- cannot support reliable player-level joins.
-- ============================================================

CREATE TABLE roster_player_weeks (
    season SMALLINT UNSIGNED NOT NULL,
    week TINYINT UNSIGNED NOT NULL,
    game_type VARCHAR(10) NOT NULL,
    team VARCHAR(5) NOT NULL,
    position VARCHAR(20),
    depth_chart_position VARCHAR(20),
    jersey_number SMALLINT,
    status VARCHAR(40),
    status_description_abbr VARCHAR(20),
    full_name VARCHAR(150),
    football_name VARCHAR(100),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    player_id VARCHAR(20) NOT NULL,
    pfr_player_id VARCHAR(30),
    espn_id VARCHAR(30),
    sleeper_id VARCHAR(30),
    years_exp SMALLINT,
    rookie_year SMALLINT,
    birth_date DATE,
    height DECIMAL(6,2),
    weight SMALLINT,
    college VARCHAR(200),
    entry_year SMALLINT,
    draft_club VARCHAR(5),
    draft_number SMALLINT,
    pfr_id_conflict TINYINT(1) NOT NULL,
    pfr_id_source VARCHAR(40),
    pfr_id_available TINYINT(1) NOT NULL,
    data_split VARCHAR(12) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (
        season,
        week,
        team,
        player_id
    ),
    INDEX idx_roster_player_weeks_player (
        player_id,
        season,
        week
    ),
    INDEX idx_roster_player_weeks_pfr (
        pfr_player_id,
        season,
        week
    ),
    INDEX idx_roster_player_weeks_team (
        team,
        season,
        week
    ),
    INDEX idx_roster_player_weeks_position (
        position,
        season,
        week
    ),
    CONSTRAINT chk_roster_pfr_conflict
        CHECK (pfr_id_conflict IN (0, 1)),
    CONSTRAINT chk_roster_pfr_available
        CHECK (pfr_id_available IN (0, 1)),
    CONSTRAINT chk_roster_game_type
        CHECK (game_type = 'REG'),
    CONSTRAINT chk_roster_split
        CHECK (
            data_split IN ('training', 'validation', 'test')
        ),
    CONSTRAINT chk_roster_week
        CHECK (week BETWEEN 1 AND 18)
) ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;
INSERT INTO roster_player_weeks (
    season,
    week,
    game_type,
    team,
    position,
    depth_chart_position,
    jersey_number,
    status,
    status_description_abbr,
    full_name,
    football_name,
    first_name,
    last_name,
    player_id,
    pfr_player_id,
    espn_id,
    sleeper_id,
    years_exp,
    rookie_year,
    birth_date,
    height,
    weight,
    college,
    entry_year,
    draft_club,
    draft_number,
    pfr_id_conflict,
    pfr_id_source,
    pfr_id_available,
    data_split
)
SELECT
    season,
    week,
    TRIM(game_type),
    TRIM(team),
    NULLIF(TRIM(position), ''),
    NULLIF(TRIM(depth_chart_position), ''),
    jersey_number,
    NULLIF(TRIM(status), ''),
    NULLIF(TRIM(status_description_abbr), ''),
    NULLIF(TRIM(full_name), ''),
    NULLIF(TRIM(football_name), ''),
    NULLIF(TRIM(first_name), ''),
    NULLIF(TRIM(last_name), ''),
    TRIM(gsis_id),
    NULLIF(TRIM(pfr_id), ''),
    NULLIF(TRIM(espn_id), ''),
    NULLIF(TRIM(sleeper_id), ''),
    years_exp,
    rookie_year,
    birth_date,
    height,
    weight,
    NULLIF(TRIM(college), ''),
    entry_year,
    NULLIF(TRIM(draft_club), ''),
    draft_number,
    COALESCE(pfr_id_conflict, 0),
    NULLIF(TRIM(pfr_id_source), ''),
    CASE
        WHEN pfr_id IS NOT NULL
        AND TRIM(pfr_id) <> ''
        THEN 1
        ELSE 0
    END,
    TRIM(data_split)
FROM stg_weekly_rosters
WHERE gsis_id IS NOT NULL
AND TRIM(gsis_id) <> '';

-- ============================================================
-- 5. PLAYERS
-- Grain: one descriptive identity record per GSIS player ID
-- Expected rows: 7,920
--
-- This table uses the latest available roster record for display
-- and identity fields. Time-varying model features must come from
-- roster_player_weeks, not this latest-record table.
-- ============================================================

CREATE TABLE players (
    player_id VARCHAR(20) NOT NULL,
    full_name VARCHAR(150),
    football_name VARCHAR(100),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    latest_position VARCHAR(20),
    latest_team VARCHAR(5),
    latest_status VARCHAR(40),
    pfr_player_id VARCHAR(30),
    espn_id VARCHAR(30),
    sleeper_id VARCHAR(30),
    birth_date DATE,
    height DECIMAL(6,2),
    weight SMALLINT,
    college VARCHAR(200),
    entry_year SMALLINT,
    rookie_year SMALLINT,
    draft_club VARCHAR(5),
    draft_number SMALLINT,
    latest_roster_season SMALLINT UNSIGNED NOT NULL,
    latest_roster_week TINYINT UNSIGNED NOT NULL,
    pfr_id_conflict TINYINT(1) NOT NULL,
    identity_data_split VARCHAR(12) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (player_id),
    INDEX idx_players_name (full_name),
    INDEX idx_players_pfr (pfr_player_id),
    INDEX idx_players_position (latest_position),
    INDEX idx_players_team (latest_team),
    CONSTRAINT chk_players_pfr_conflict
        CHECK (pfr_id_conflict IN (0, 1)),
    CONSTRAINT chk_players_identity_split
        CHECK (
            identity_data_split
            IN ('training', 'validation', 'test')
        )
) ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;
INSERT INTO players (
    player_id,
    full_name,
    football_name,
    first_name,
    last_name,
    latest_position,
    latest_team,
    latest_status,
    pfr_player_id,
    espn_id,
    sleeper_id,
    birth_date,
    height,
    weight,
    college,
    entry_year,
    rookie_year,
    draft_club,
    draft_number,
    latest_roster_season,
    latest_roster_week,
    pfr_id_conflict,
    identity_data_split
)
SELECT
    player_id,
    full_name,
    football_name,
    first_name,
    last_name,
    position,
    team,
    status,
    pfr_player_id,
    espn_id,
    sleeper_id,
    birth_date,
    height,
    weight,
    college,
    entry_year,
    rookie_year,
    draft_club,
    draft_number,
    season,
    week,
    pfr_id_conflict,
    data_split
FROM (
    SELECT
        r.*,
        ROW_NUMBER() OVER (
            PARTITION BY player_id
            ORDER BY
                season DESC,
                week DESC,
                pfr_id_available DESC,
                pfr_id_conflict ASC,
                CASE
                    WHEN status IN ('ACT', 'Active') THEN 0
                    ELSE 1
                END,
                team ASC
        ) AS identity_rank
    FROM roster_player_weeks AS r
) AS ranked_rosters
WHERE identity_rank = 1;

-- ============================================================
-- 6. PLAYER-WEEK ID CROSSWALK
-- Grain: one GSIS-to-PFR mapping per player-team-week
-- Expected rows: 352,455
--
-- The weekly grain prevents a current player identity from being
-- incorrectly applied to an earlier team or season.
-- ============================================================

CREATE TABLE player_week_id_crosswalk (
    season SMALLINT UNSIGNED NOT NULL,
    week TINYINT UNSIGNED NOT NULL,
    team VARCHAR(5) NOT NULL,
    player_id VARCHAR(20) NOT NULL,
    pfr_player_id VARCHAR(30) NOT NULL,
    pfr_id_source VARCHAR(40),
    pfr_id_conflict TINYINT(1) NOT NULL,
    data_split VARCHAR(12) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (
        season,
        week,
        team,
        player_id
    ),
    UNIQUE KEY uq_crosswalk_pfr_week (
        season,
        week,
        team,
        pfr_player_id
    ),
    INDEX idx_crosswalk_player (
        player_id,
        season,
        week
    ),
    INDEX idx_crosswalk_pfr (
        pfr_player_id,
        season,
        week
    ),
    CONSTRAINT chk_crosswalk_pfr_conflict
        CHECK (pfr_id_conflict IN (0, 1)),
    CONSTRAINT chk_crosswalk_split
        CHECK (
            data_split IN ('training', 'validation', 'test')
        ),
    CONSTRAINT chk_crosswalk_week
        CHECK (week BETWEEN 1 AND 18)
) ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;
INSERT INTO player_week_id_crosswalk (
    season,
    week,
    team,
    player_id,
    pfr_player_id,
    pfr_id_source,
    pfr_id_conflict,
    data_split
)
SELECT
    season,
    week,
    team,
    player_id,
    pfr_player_id,
    pfr_id_source,
    pfr_id_conflict,
    data_split
FROM roster_player_weeks
WHERE pfr_player_id IS NOT NULL
    AND TRIM(pfr_player_id) <> '';

-- ============================================================
-- 7. WEEKLY INJURY REPORTS
-- Grain: one player-team injury record per regular-season week
-- Expected rows: 43,561
--
-- A missing final report status does not mean the player was
-- healthy. The source commonly omits that field.
--
-- date_modified_utc is populated for 2018-2024 but unavailable
-- for 2025, limiting precise intraday as-of filtering in 2025.
-- ============================================================

CREATE TABLE injury_player_weeks (
    season SMALLINT UNSIGNED NOT NULL,
    week TINYINT UNSIGNED NOT NULL,
    season_type VARCHAR(10),
    game_type VARCHAR(10) NOT NULL,
    team VARCHAR(5) NOT NULL,
    player_id VARCHAR(20) NOT NULL,
    position VARCHAR(20),
    full_name VARCHAR(150),
    report_primary_injury VARCHAR(255),
    report_secondary_injury VARCHAR(150),
    report_status VARCHAR(40),
    practice_primary_injury VARCHAR(150),
    practice_secondary_injury VARCHAR(150),
    practice_status VARCHAR(80),
    date_modified_utc DATETIME(6),
    has_final_report_status TINYINT(1) NOT NULL,
    has_practice_status TINYINT(1) NOT NULL,
    has_update_timestamp TINYINT(1) NOT NULL,
    data_split VARCHAR(12) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (
        season,
        week,
        team,
        player_id
    ),
    INDEX idx_injury_player_weeks_player (
        player_id,
        season,
        week
    ),
    INDEX idx_injury_player_weeks_team (
        team,
        season,
        week
    ),
    INDEX idx_injury_player_weeks_report (
        report_status,
        season,
        week
    ),
    CONSTRAINT chk_injury_final_report_flag
        CHECK (has_final_report_status IN (0, 1)),
    CONSTRAINT chk_injury_practice_flag
        CHECK (has_practice_status IN (0, 1)),
    CONSTRAINT chk_injury_timestamp_flag
        CHECK (has_update_timestamp IN (0, 1)),
    CONSTRAINT chk_injury_game_type
        CHECK (game_type = 'REG'),
    CONSTRAINT chk_injury_split
        CHECK (
            data_split IN ('training', 'validation', 'test')
        ),
    CONSTRAINT chk_injury_week
        CHECK (week BETWEEN 1 AND 18)
) ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;
INSERT INTO injury_player_weeks (
    season,
    week,
    season_type,
    game_type,
    team,
    player_id,
    position,
    full_name,
    report_primary_injury,
    report_secondary_injury,
    report_status,
    practice_primary_injury,
    practice_secondary_injury,
    practice_status,
    date_modified_utc,
    has_final_report_status,
    has_practice_status,
    has_update_timestamp,
    data_split
)
SELECT
    season,
    week,
    NULLIF(TRIM(season_type), ''),
    TRIM(game_type),
    TRIM(team),
    TRIM(gsis_id),
    NULLIF(TRIM(position), ''),
    NULLIF(TRIM(full_name), ''),
    NULLIF(TRIM(report_primary_injury), ''),
    NULLIF(TRIM(report_secondary_injury), ''),
    NULLIF(TRIM(report_status), ''),
    NULLIF(TRIM(practice_primary_injury), ''),
    NULLIF(TRIM(practice_secondary_injury), ''),
    NULLIF(TRIM(practice_status), ''),
    date_modified,
    CASE
        WHEN report_status IS NOT NULL
        AND TRIM(report_status) <> ''
        THEN 1
        ELSE 0
    END,
    CASE
        WHEN practice_status IS NOT NULL
        AND TRIM(practice_status) <> ''
        THEN 1
        ELSE 0
    END,
    CASE
        WHEN date_modified IS NOT NULL THEN 1
        ELSE 0
    END,
    TRIM(data_split)
FROM stg_injuries
WHERE gsis_id IS NOT NULL
AND TRIM(gsis_id) <> '';

-- ============================================================
-- 8. WEEKLY SNAP COUNTS
-- Grain: one player-team snap record per regular-season week
-- Expected rows: 196,130
-- Expected GSIS-matched rows: 195,781
-- Expected unmatched rows: 349
--
-- Snap counts are observed after the game. They must be shifted
-- to prior weeks before being used as prediction features.
-- ============================================================

CREATE TABLE snap_player_weeks (
    game_id VARCHAR(30) NOT NULL,
    pfr_game_id VARCHAR(30),
    season SMALLINT UNSIGNED NOT NULL,
    game_type VARCHAR(10) NOT NULL,
    week TINYINT UNSIGNED NOT NULL,
    player_name VARCHAR(150),
    pfr_player_id VARCHAR(30) NOT NULL,
    player_id VARCHAR(20),
    player_id_match_status VARCHAR(20) NOT NULL,
    position VARCHAR(20),
    team VARCHAR(5) NOT NULL,
    opponent VARCHAR(5) NOT NULL,
    offense_snaps DOUBLE,
    offense_pct DOUBLE,
    defense_snaps DOUBLE,
    defense_pct DOUBLE,
    st_snaps DOUBLE,
    st_pct DOUBLE,
    data_split VARCHAR(12) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (
        season,
        week,
        team,
        pfr_player_id
    ),
    UNIQUE KEY uq_snap_player_game (
        game_id,
        pfr_player_id
    ),
    INDEX idx_snap_player_weeks_player (
        player_id,
        season,
        week
    ),
    INDEX idx_snap_player_weeks_pfr (
        pfr_player_id,
        season,
        week
    ),
    INDEX idx_snap_player_weeks_team (
        team,
        season,
        week
    ),
    INDEX idx_snap_player_weeks_position (
        position,
        season,
        week
    ),
    CONSTRAINT chk_snap_match_status
        CHECK (
            player_id_match_status IN ('matched', 'unmatched')
        ),
    CONSTRAINT chk_snap_game_type
        CHECK (game_type = 'REG'),
    CONSTRAINT chk_snap_split
        CHECK (
            data_split IN ('training', 'validation', 'test')
        ),
    CONSTRAINT chk_snap_week
        CHECK (week BETWEEN 1 AND 18)
) ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;
INSERT INTO snap_player_weeks (
    game_id,
    pfr_game_id,
    season,
    game_type,
    week,
    player_name,
    pfr_player_id,
    player_id,
    player_id_match_status,
    position,
    team,
    opponent,
    offense_snaps,
    offense_pct,
    defense_snaps,
    defense_pct,
    st_snaps,
    st_pct,
    data_split
)
SELECT
    TRIM(s.game_id),
    NULLIF(TRIM(s.pfr_game_id), ''),
    s.season,
    TRIM(s.game_type),
    s.week,
    NULLIF(TRIM(s.player), ''),
    TRIM(s.pfr_player_id),
    x.player_id,
    CASE
        WHEN x.player_id IS NOT NULL THEN 'matched'
        ELSE 'unmatched'
    END,
    NULLIF(TRIM(s.position), ''),
    TRIM(s.team),
    TRIM(s.opponent),
    s.offense_snaps,
    s.offense_pct,
    s.defense_snaps,
    s.defense_pct,
    s.st_snaps,
    s.st_pct,
    TRIM(s.data_split)
FROM stg_snap_counts AS s
LEFT JOIN player_week_id_crosswalk AS x
    ON x.season = s.season
    AND x.week = s.week
    AND x.team = TRIM(s.team)
    AND x.pfr_player_id = TRIM(s.pfr_player_id);

-- ============================================================
-- 9. LEGACY WEEKLY DEPTH CHARTS
-- Grain: one player-position-rank record per week
-- Source seasons: 2018-2024
-- Expected rows: 242,058
--
-- The legacy feed does not provide a precise within-week update
-- timestamp. It must not be treated as known pregame evidence
-- without an additional conservative as-of rule.
-- ============================================================

CREATE TABLE depth_chart_legacy_weeks (
    season SMALLINT UNSIGNED NOT NULL,
    week TINYINT UNSIGNED NOT NULL,
    game_type VARCHAR(10) NOT NULL,
    team VARCHAR(5) NOT NULL,
    player_name VARCHAR(150),
    espn_id VARCHAR(30),
    player_id VARCHAR(20) NOT NULL,
    roster_position VARCHAR(20),
    pos_grp VARCHAR(40) NOT NULL,
    pos_name VARCHAR(100),
    pos_abb VARCHAR(20) NOT NULL,
    pos_rank INT NOT NULL,
    data_split VARCHAR(12) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (
        season,
        week,
        team,
        player_id,
        pos_grp,
        pos_abb,
        pos_rank
    ),
    INDEX idx_legacy_depth_player (
        player_id,
        season,
        week
    ),
    INDEX idx_legacy_depth_team (
        team,
        season,
        week
    ),
    INDEX idx_legacy_depth_position (
        pos_abb,
        season,
        week
    ),
    CONSTRAINT chk_legacy_depth_game_type
        CHECK (game_type = 'REG'),
    CONSTRAINT chk_legacy_depth_split
        CHECK (
            data_split IN ('training', 'validation', 'test')
        ),
-- The legacy source includes week 19 depth snapshots for
-- 2021-2024. Actual regular-season game facts end at week 18.
    CONSTRAINT chk_legacy_depth_week
        CHECK (week BETWEEN 1 AND 19)
) ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;
INSERT INTO depth_chart_legacy_weeks (
    season,
    week,
    game_type,
    team,
    player_name,
    espn_id,
    player_id,
    roster_position,
    pos_grp,
    pos_name,
    pos_abb,
    pos_rank,
    data_split
)
SELECT
    season,
    week,
    TRIM(game_type),
    TRIM(team),
    NULLIF(TRIM(player_name), ''),
    NULLIF(TRIM(espn_id), ''),
    TRIM(gsis_id),
    NULLIF(TRIM(roster_position), ''),
    TRIM(pos_grp),
    NULLIF(TRIM(pos_name), ''),
    TRIM(pos_abb),
    pos_rank,
    TRIM(data_split)
FROM stg_depth_charts
WHERE depth_source_format = 'legacy_weekly'
AND gsis_id IS NOT NULL
AND TRIM(gsis_id) <> ''
AND season IS NOT NULL
AND week IS NOT NULL
AND game_type IS NOT NULL
AND TRIM(game_type) <> ''
AND team IS NOT NULL
AND TRIM(team) <> ''
AND pos_grp IS NOT NULL
AND TRIM(pos_grp) <> ''
AND pos_abb IS NOT NULL
AND TRIM(pos_abb) <> ''
AND pos_rank IS NOT NULL;

-- ============================================================
-- 10. TIMESTAMPED DEPTH-CHART SNAPSHOTS
-- Grain: one player-position-slot record per source timestamp
-- Source season: 2025
-- Expected rows: 548,638
--
-- These records support an as-of join using the latest snapshot
-- at or before the relevant game time.
-- ============================================================

CREATE TABLE depth_chart_snapshots (
    source_season SMALLINT UNSIGNED NOT NULL,
    snapshot_text VARCHAR(40) NOT NULL,
    snapshot_at_utc DATETIME(6) NOT NULL,
    team VARCHAR(5) NOT NULL,
    player_name VARCHAR(150),
    espn_id VARCHAR(30),
    player_id VARCHAR(20) NOT NULL,
    roster_position VARCHAR(20),
    pos_grp_id VARCHAR(20),
    pos_grp VARCHAR(40),
    pos_id VARCHAR(20),
    pos_name VARCHAR(100),
    pos_abb VARCHAR(20) NOT NULL,
    pos_slot INT NOT NULL,
    pos_rank INT,
    data_split VARCHAR(12) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (
        snapshot_at_utc,
        team,
        player_id,
        pos_abb,
        pos_slot
    ),
    INDEX idx_depth_snapshot_player (
        player_id,
        snapshot_at_utc
    ),
    INDEX idx_depth_snapshot_team (
        team,
        snapshot_at_utc
    ),
    INDEX idx_depth_snapshot_position (
        pos_abb,
        snapshot_at_utc
    ),
    CONSTRAINT chk_depth_snapshot_split
        CHECK (
            data_split IN ('training', 'validation', 'test')
        )
) ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;
INSERT INTO depth_chart_snapshots (
    source_season,
    snapshot_text,
    snapshot_at_utc,
    team,
    player_name,
    espn_id,
    player_id,
    roster_position,
    pos_grp_id,
    pos_grp,
    pos_id,
    pos_name,
    pos_abb,
    pos_slot,
    pos_rank,
    data_split
)
SELECT
    source_season,
    TRIM(dt),
    depth_timestamp,
    TRIM(team),
    NULLIF(TRIM(player_name), ''),
    NULLIF(TRIM(espn_id), ''),
    TRIM(gsis_id),
    NULLIF(TRIM(roster_position), ''),
    NULLIF(TRIM(pos_grp_id), ''),
    NULLIF(TRIM(pos_grp), ''),
    NULLIF(TRIM(pos_id), ''),
    NULLIF(TRIM(pos_name), ''),
    TRIM(pos_abb),
    pos_slot,
    pos_rank,
    TRIM(data_split)
FROM stg_depth_charts
WHERE depth_source_format = 'timestamped'
AND gsis_id IS NOT NULL
AND TRIM(gsis_id) <> ''
AND dt IS NOT NULL
AND TRIM(dt) <> ''
AND depth_timestamp IS NOT NULL
AND team IS NOT NULL
AND TRIM(team) <> ''
AND pos_abb IS NOT NULL
AND TRIM(pos_abb) <> ''
AND pos_slot IS NOT NULL;

-- ============================================================
-- CLEAN TABLE ROW-COUNT RECONCILIATION
--
-- All ten rows should return validation_status = PASS.
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
-- SNAP-COUNT PLAYER-ID COVERAGE
--
-- Expected:
-- total_snap_rows       = 196,130
-- matched_player_rows   = 195,781
-- unmatched_player_rows = 349
-- player_match_pct      = 99.82
-- ============================================================

SELECT
    COUNT(*) AS total_snap_rows,
    SUM(
        CASE
            WHEN player_id_match_status = 'matched' THEN 1
            ELSE 0
        END
    ) AS matched_player_rows,
    SUM(
        CASE
            WHEN player_id_match_status = 'unmatched' THEN 1
            ELSE 0
        END
    ) AS unmatched_player_rows,
    ROUND(
        100.0
        * SUM(
            CASE
                WHEN player_id_match_status = 'matched' THEN 1
                ELSE 0
            END
        )
        / NULLIF(COUNT(*), 0),
        2
    ) AS player_match_pct
FROM snap_player_weeks;