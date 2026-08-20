USE nfl_fantasy_advisor;

-- ============================================================
-- 1. WEEKLY PLAYER STATISTICS
-- Grain: one core fantasy player per regular-season week
-- ============================================================

CREATE TABLE IF NOT EXISTS stg_weekly_player_stats (
    staging_row_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    player_id VARCHAR(20),
    player_name VARCHAR(100),
    player_display_name VARCHAR(150),
    position VARCHAR(10),
    position_group VARCHAR(20),
    headshot_url VARCHAR(1000),
    season SMALLINT UNSIGNED,
    week TINYINT UNSIGNED,
    season_type VARCHAR(10),
    game_id VARCHAR(30),
    team VARCHAR(5),
    opponent_team VARCHAR(5),

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
    data_split VARCHAR(12),
    calculated_fantasy_points_ppr DOUBLE,
    fantasy_point_difference DOUBLE,

    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (staging_row_id),
    INDEX idx_stg_stats_player_week (player_id, season, week),
    INDEX idx_stg_stats_team_week (team, season, week),
    INDEX idx_stg_stats_position (position, season, week),
    INDEX idx_stg_stats_game (game_id)
) ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


-- ============================================================
-- 2. NFL SCHEDULES
-- Grain: one regular-season game
-- ============================================================

CREATE TABLE IF NOT EXISTS stg_schedules (
    staging_row_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    game_id VARCHAR(30),
    season SMALLINT UNSIGNED,
    game_type VARCHAR(10),
    week TINYINT UNSIGNED,
    gameday DATE,
    weekday VARCHAR(12),
    gametime TIME,
    away_team VARCHAR(5),
    away_score INT,
    home_team VARCHAR(5),
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
    data_split VARCHAR(12),

    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (staging_row_id),
    INDEX idx_stg_schedule_game (game_id),
    INDEX idx_stg_schedule_season_week (season, week),
    INDEX idx_stg_schedule_away_team (away_team, season, week),
    INDEX idx_stg_schedule_home_team (home_team, season, week)
) ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


-- ============================================================
-- 3. WEEKLY ROSTERS
-- Grain: one player-team-week roster record
-- ============================================================

CREATE TABLE IF NOT EXISTS stg_weekly_rosters (
    staging_row_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    season SMALLINT UNSIGNED,
    week TINYINT UNSIGNED,
    game_type VARCHAR(10),
    team VARCHAR(5),
    position VARCHAR(20),
    depth_chart_position VARCHAR(20),
    jersey_number SMALLINT,
    status VARCHAR(40),
    status_description_abbr VARCHAR(20),
    full_name VARCHAR(150),
    football_name VARCHAR(100),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    gsis_id VARCHAR(20),
    pfr_id VARCHAR(30),
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
    pfr_id_conflict TINYINT(1),
    pfr_id_source VARCHAR(40),
    data_split VARCHAR(12),

    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (staging_row_id),
    INDEX idx_stg_roster_gsis_week (gsis_id, season, week),
    INDEX idx_stg_roster_pfr_week (pfr_id, season, week),
    INDEX idx_stg_roster_team_week (team, season, week),
    INDEX idx_stg_roster_position (position, season, week)
) ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


-- ============================================================
-- 4. WEEKLY INJURY REPORTS
-- Grain: one player-team-week injury record
-- ============================================================

CREATE TABLE IF NOT EXISTS stg_injuries (
    staging_row_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    season SMALLINT UNSIGNED,
    week TINYINT UNSIGNED,
    season_type VARCHAR(10),
    game_type VARCHAR(10),
    team VARCHAR(5),
    gsis_id VARCHAR(20),
    position VARCHAR(20),
    full_name VARCHAR(150),
    report_primary_injury VARCHAR(255),
    report_secondary_injury VARCHAR(150),
    report_status VARCHAR(40),
    practice_primary_injury VARCHAR(150),
    practice_secondary_injury VARCHAR(150),
    practice_status VARCHAR(80),
    date_modified DATETIME(6),
    data_split VARCHAR(12),

    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (staging_row_id),
    INDEX idx_stg_injury_player_week (gsis_id, season, week),
    INDEX idx_stg_injury_team_week (team, season, week),
    INDEX idx_stg_injury_status (report_status, season, week)
) ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


-- ============================================================
-- 5. DEPTH CHARTS
-- Legacy grain: player-position-week
-- Current grain: player-position-timestamp
-- ============================================================

CREATE TABLE IF NOT EXISTS stg_depth_charts (
    staging_row_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_season SMALLINT UNSIGNED,
    depth_source_format VARCHAR(30),
    season SMALLINT UNSIGNED,
    week TINYINT UNSIGNED,
    game_type VARCHAR(10),
    dt VARCHAR(40),
    depth_timestamp DATETIME(6),
    team VARCHAR(5),
    player_name VARCHAR(150),
    espn_id VARCHAR(30),
    gsis_id VARCHAR(20),
    roster_position VARCHAR(20),
    pos_grp_id VARCHAR(20),
    pos_grp VARCHAR(40),
    pos_id VARCHAR(20),
    pos_name VARCHAR(100),
    pos_abb VARCHAR(20),
    pos_slot INT,
    pos_rank INT,
    data_split VARCHAR(12),

    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (staging_row_id),
    INDEX idx_stg_depth_gsis_week (gsis_id, season, week),
    INDEX idx_stg_depth_gsis_timestamp (
        gsis_id,
        team,
        depth_timestamp
    ),
    INDEX idx_stg_depth_team_week (team, season, week),
    INDEX idx_stg_depth_team_timestamp (team, depth_timestamp),
    INDEX idx_stg_depth_source_format (
        depth_source_format,
        source_season
    )
) ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


-- ============================================================
-- 6. PLAYER SNAP COUNTS
-- Grain: one player-game snap record
-- ============================================================

CREATE TABLE IF NOT EXISTS stg_snap_counts (
    staging_row_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    game_id VARCHAR(30),
    pfr_game_id VARCHAR(30),
    season SMALLINT UNSIGNED,
    game_type VARCHAR(10),
    week TINYINT UNSIGNED,
    player VARCHAR(150),
    pfr_player_id VARCHAR(30),
    position VARCHAR(20),
    team VARCHAR(5),
    opponent VARCHAR(5),
    offense_snaps DOUBLE,
    offense_pct DOUBLE,
    defense_snaps DOUBLE,
    defense_pct DOUBLE,
    st_snaps DOUBLE,
    st_pct DOUBLE,
    data_split VARCHAR(12),

    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (staging_row_id),
    INDEX idx_stg_snaps_pfr_week (
        pfr_player_id,
        season,
        week
    ),
    INDEX idx_stg_snaps_game (game_id),
    INDEX idx_stg_snaps_team_week (team, season, week),
    INDEX idx_stg_snaps_position (position, season, week)
) ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


-- ============================================================
-- VALIDATION CONTROLS
-- Six staging tables should appear.
-- All row counts should initially be zero.
-- ============================================================

SELECT
    table_name,
    table_rows
FROM information_schema.tables
WHERE table_schema = DATABASE()
AND table_name LIKE 'stg\_%'
ORDER BY table_name;

SELECT
    'stg_weekly_player_stats' AS table_name,
    COUNT(*) AS row_count
FROM stg_weekly_player_stats

UNION ALL

SELECT
    'stg_schedules',
    COUNT(*)
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
FROM stg_snap_counts;