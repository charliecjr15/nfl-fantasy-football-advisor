import argparse
import math
import os
import tomllib
from pathlib import Path

import nflreadpy as nfl
import polars as pl
from dotenv import load_dotenv
from nflreadpy.config import update_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]

TEAM_CODE_REPLACEMENTS = {
    "OAK": "LV",
}

TEAM_CODE_COLUMNS = {
    "team",
    "opponent_team",
    "away_team",
    "home_team",
    "club_code",
    "opponent",
}

PLAYER_IDENTITY_COLUMNS = [
    "gsis_id",
    "pfr_id",
]

PLAYER_IDENTITY_REQUIRED_COLUMNS = [
    "gsis_id",
    "pfr_id",
]

PLAYER_STAT_COLUMNS = [
    "player_id",
    "player_name",
    "player_display_name",
    "position",
    "position_group",
    "headshot_url",
    "season",
    "week",
    "season_type",
    "game_id",
    "team",
    "opponent_team",
    "completions",
    "attempts",
    "passing_yards",
    "passing_tds",
    "passing_interceptions",
    "sacks_suffered",
    "sack_yards_lost",
    "sack_fumbles",
    "sack_fumbles_lost",
    "passing_air_yards",
    "passing_yards_after_catch",
    "passing_first_downs",
    "passing_epa",
    "passing_cpoe",
    "passing_2pt_conversions",
    "carries",
    "rushing_yards",
    "rushing_tds",
    "rushing_fumbles",
    "rushing_fumbles_lost",
    "rushing_first_downs",
    "rushing_epa",
    "rushing_2pt_conversions",
    "receptions",
    "targets",
    "receiving_yards",
    "receiving_tds",
    "receiving_fumbles",
    "receiving_fumbles_lost",
    "receiving_air_yards",
    "receiving_yards_after_catch",
    "receiving_first_downs",
    "receiving_epa",
    "receiving_2pt_conversions",
    "target_share",
    "air_yards_share",
    "wopr",
    "special_teams_tds",
    "fumbles_lost_total",
    "fantasy_points",
    "fantasy_points_ppr",
]

PLAYER_STAT_REQUIRED_COLUMNS = [
    "player_id",
    "player_display_name",
    "position",
    "season",
    "week",
    "season_type",
    "game_id",
    "team",
    "opponent_team",
    "passing_yards",
    "passing_tds",
    "passing_interceptions",
    "sack_fumbles_lost",
    "passing_2pt_conversions",
    "rushing_yards",
    "rushing_tds",
    "rushing_fumbles_lost",
    "rushing_2pt_conversions",
    "receptions",
    "receiving_yards",
    "receiving_tds",
    "receiving_fumbles_lost",
    "receiving_2pt_conversions",
    "special_teams_tds",
    "fantasy_points_ppr",
]

SCHEDULE_COLUMNS = [
    "game_id",
    "season",
    "game_type",
    "week",
    "gameday",
    "weekday",
    "gametime",
    "away_team",
    "away_score",
    "home_team",
    "home_score",
    "location",
    "result",
    "total",
    "overtime",
    "away_rest",
    "home_rest",
    "spread_line",
    "total_line",
    "div_game",
    "roof",
    "surface",
    "temp",
    "wind",
    "stadium_id",
    "stadium",
]

SCHEDULE_REQUIRED_COLUMNS = [
    "game_id",
    "season",
    "game_type",
    "week",
    "gameday",
    "gametime",
    "away_team",
    "home_team",
]

ROSTER_COLUMNS = [
    "season",
    "week",
    "game_type",
    "team",
    "position",
    "depth_chart_position",
    "jersey_number",
    "status",
    "status_description_abbr",
    "full_name",
    "football_name",
    "first_name",
    "last_name",
    "gsis_id",
    "pfr_id",
    "espn_id",
    "sleeper_id",
    "years_exp",
    "rookie_year",
    "birth_date",
    "height",
    "weight",
    "college",
    "entry_year",
    "draft_club",
    "draft_number",
]

ROSTER_REQUIRED_COLUMNS = [
    "season",
    "week",
    "game_type",
    "team",
    "position",
    "full_name",
    "gsis_id",
    "pfr_id",
]

INJURY_COLUMNS = [
    "season",
    "week",
    "season_type",
    "game_type",
    "team",
    "gsis_id",
    "position",
    "full_name",
    "report_primary_injury",
    "report_secondary_injury",
    "report_status",
    "practice_primary_injury",
    "practice_secondary_injury",
    "practice_status",
    "date_modified",
]

INJURY_REQUIRED_COLUMNS = [
    "season",
    "week",
    "game_type",
    "team",
    "gsis_id",
    "position",
    "full_name",
    "report_status",
    "practice_status",
]

DEPTH_CHART_COLUMNS = [
    "dt",
    "team",
    "player_name",
    "espn_id",
    "gsis_id",
    "pos_grp_id",
    "pos_grp",
    "pos_id",
    "pos_name",
    "pos_abb",
    "pos_slot",
    "pos_rank",
]

DEPTH_CHART_REQUIRED_COLUMNS = [
    "dt",
    "team",
    "player_name",
    "gsis_id",
    "pos_abb",
    "pos_slot",
    "pos_rank",
]

LEGACY_DEPTH_CHART_COLUMNS = [
    "season",
    "week",
    "game_type",
    "club_code",
    "depth_team",
    "formation",
    "gsis_id",
    "position",
    "depth_position",
    "full_name",
]

LEGACY_DEPTH_CHART_REQUIRED_COLUMNS = [
    "season",
    "week",
    "game_type",
    "club_code",
    "depth_team",
    "formation",
    "gsis_id",
    "position",
    "depth_position",
    "full_name",
]

DEPTH_CHART_OUTPUT_COLUMNS = [
    "source_season",
    "depth_source_format",
    "season",
    "week",
    "game_type",
    "dt",
    "depth_timestamp",
    "team",
    "player_name",
    "espn_id",
    "gsis_id",
    "roster_position",
    "pos_grp_id",
    "pos_grp",
    "pos_id",
    "pos_name",
    "pos_abb",
    "pos_slot",
    "pos_rank",
]

SNAP_COUNT_COLUMNS = [
    "game_id",
    "pfr_game_id",
    "season",
    "game_type",
    "week",
    "player",
    "pfr_player_id",
    "position",
    "team",
    "opponent",
    "offense_snaps",
    "offense_pct",
    "defense_snaps",
    "defense_pct",
    "st_snaps",
    "st_pct",
]

SNAP_COUNT_REQUIRED_COLUMNS = [
    "game_id",
    "season",
    "game_type",
    "week",
    "player",
    "pfr_player_id",
    "position",
    "team",
    "opponent",
    "offense_snaps",
    "offense_pct",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Extract validated historical nflverse data into "
            "season-partitioned Parquet files."
        )
    )
    parser.add_argument(
        "--config",
        default="config/data_settings.toml",
        help=(
            "Path to the historical data configuration file. "
            "Defaults to config/data_settings.toml."
        ),
    )
    return parser.parse_args()


def print_section(title):
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def resolve_project_path(path_text):
    path = Path(path_text)

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    path = path.resolve()

    try:
        path.relative_to(PROJECT_ROOT)
    except ValueError as error:
        raise ValueError(
            f"Configured output path is outside the project: {path}"
        ) from error

    return path


def load_settings(config_path):
    path = Path(config_path)

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    path = path.resolve()

    with path.open("rb") as config_file:
        settings = tomllib.load(config_file)

    seasons = settings["data"]["seasons"]
    start_season = settings["data"]["start_season"]
    end_season = settings["data"]["end_season"]

    expected_seasons = list(
        range(start_season, end_season + 1)
    )

    if seasons != expected_seasons:
        raise ValueError(
            "Configured seasons must form a continuous range "
            "from start_season through end_season."
        )

    training = set(settings["split"]["training_seasons"])
    validation = set(settings["split"]["validation_seasons"])
    test = set(settings["split"]["test_seasons"])
    configured = set(seasons)

    if (
        not training.isdisjoint(validation)
        or not training.isdisjoint(test)
        or not validation.isdisjoint(test)
    ):
        raise ValueError(
            "Training, validation, and test seasons overlap."
        )

    if training | validation | test != configured:
        raise ValueError(
            "Training, validation, and test seasons must "
            "cover every configured season exactly once."
        )

    if not (
        max(training)
        < min(validation)
        <= max(validation)
        < min(test)
    ):
        raise ValueError(
            "The configured data split is not chronological."
        )

    if settings["split"]["allow_random_split"]:
        raise ValueError(
            "Random splitting is disabled for this project."
        )

    if settings["temporal"]["allow_future_features"]:
        raise ValueError(
            "Future features must remain disabled."
        )

    return settings, path


def load_league_scoring():
    settings_path = (
        PROJECT_ROOT
        / "config"
        / "league_settings.toml"
    )

    with settings_path.open("rb") as settings_file:
        settings = tomllib.load(settings_file)

    return settings["scoring"]


def configure_cache():
    load_dotenv(PROJECT_ROOT / ".env")

    configured_path = Path(
        os.getenv("NFL_CACHE_DIR", "data/cache")
    )

    if configured_path.is_absolute():
        cache_dir = configured_path
    else:
        cache_dir = PROJECT_ROOT / configured_path

    cache_dir = cache_dir.resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)

    update_config(
        cache_mode="filesystem",
        cache_dir=cache_dir,
        verbose=True,
    )

    print(f"Cache directory: {cache_dir}")


def split_name(season, settings):
    if season in settings["split"]["training_seasons"]:
        return "training"

    if season in settings["split"]["validation_seasons"]:
        return "validation"

    if season in settings["split"]["test_seasons"]:
        return "test"

    raise ValueError(
        f"Season {season} does not belong to a data split."
    )


def available_text(column):
    return (
        pl.col(column)
        .fill_null("")
        .str
        .strip_chars()
        != ""
    )


def normalize_text_columns(dataframe, columns):
    expressions = []

    for column in columns:
        if column not in dataframe.columns:
            continue

        normalized = (
            pl.when(
                pl.col(column)
                .fill_null("")
                .str
                .strip_chars()
                == ""
            )
            .then(None)
            .otherwise(
                pl.col(column)
                .str
                .strip_chars()
            )
        )

        if column in TEAM_CODE_COLUMNS:
            normalized = normalized.replace(
                TEAM_CODE_REPLACEMENTS
            )

        expressions.append(
            normalized.alias(column)
        )

    if not expressions:
        return dataframe

    return dataframe.with_columns(expressions)


def select_planned_columns(
    dataframe,
    dataset_name,
    planned_columns,
    required_columns,
):
    missing_required = [
        column
        for column in required_columns
        if column not in dataframe.columns
    ]

    if missing_required:
        raise ValueError(
            f"{dataset_name} is missing required columns: "
            + ", ".join(missing_required)
        )

    missing_optional = [
        column
        for column in planned_columns
        if column not in dataframe.columns
    ]

    expressions = []

    for column in planned_columns:
        if column in dataframe.columns:
            expressions.append(pl.col(column))
        else:
            expressions.append(
                pl.lit(None).alias(column)
            )

    selected = dataframe.select(expressions)

    return selected, missing_optional

def prepare_player_identity(source):
    selected, _ = select_planned_columns(
        source,
        "players",
        PLAYER_IDENTITY_COLUMNS,
        PLAYER_IDENTITY_REQUIRED_COLUMNS,
    )

    prepared = normalize_text_columns(
        selected,
        ["gsis_id", "pfr_id"],
    )

    unavailable_gsis_rows = (
        prepared.height
        - prepared.filter(
            available_text("gsis_id")
        ).height
    )

    if unavailable_gsis_rows:
        raise ValueError(
            "players contains "
            f"{unavailable_gsis_rows:,} rows with "
            "an unavailable GSIS ID."
        )

    duplicate_gsis_groups = (
        prepared
        .group_by("gsis_id")
        .len()
        .filter(pl.col("len") > 1)
        .height
    )

    if duplicate_gsis_groups:
        raise ValueError(
            "players contains "
            f"{duplicate_gsis_groups:,} duplicate "
            "GSIS ID groups."
        )

    prepared = (
        prepared
        .select(
            pl.col("gsis_id").alias("player_id"),
            pl.col("pfr_id").alias(
                "identity_pfr_id"
            ),
        )
        .sort("player_id")
    )

    return prepared

def add_data_split(dataframe, season, settings):
    return dataframe.with_columns(
        pl.lit(
            split_name(season, settings)
        ).alias("data_split")
    )


def calculate_fantasy_points(dataframe, scoring):
    calculated_points = (
        (
            pl.col("passing_yards").fill_null(0)
            * scoring["passing_yards"]
        )
        + (
            pl.col("passing_tds").fill_null(0)
            * scoring["passing_touchdowns"]
        )
        + (
            pl.col("passing_interceptions").fill_null(0)
            * scoring["interceptions"]
        )
        + (
            pl.col("rushing_yards").fill_null(0)
            * scoring["rushing_yards"]
        )
        + (
            pl.col("rushing_tds").fill_null(0)
            * scoring["rushing_touchdowns"]
        )
        + (
            pl.col("receptions").fill_null(0)
            * scoring["receptions"]
        )
        + (
            pl.col("receiving_yards").fill_null(0)
            * scoring["receiving_yards"]
        )
        + (
            pl.col("receiving_tds").fill_null(0)
            * scoring["receiving_touchdowns"]
        )
        + (
            pl.col("special_teams_tds").fill_null(0)
            * scoring["special_teams_touchdowns"]
        )
        + (
            (
                pl.col("passing_2pt_conversions").fill_null(0)
                + pl.col("rushing_2pt_conversions").fill_null(0)
                + pl.col("receiving_2pt_conversions").fill_null(0)
            )
            * scoring["two_point_conversions"]
        )
        + (
            (
                pl.col("sack_fumbles_lost").fill_null(0)
                + pl.col("rushing_fumbles_lost").fill_null(0)
                + pl.col("receiving_fumbles_lost").fill_null(0)
            )
            * scoring["fumbles_lost"]
        )
    )

    return (
        dataframe
        .with_columns(
            calculated_points
            .round(4)
            .alias("calculated_fantasy_points_ppr")
        )
        .with_columns(
            (
                pl.col("calculated_fantasy_points_ppr")
                - pl.col("fantasy_points_ppr")
            )
            .round(6)
            .alias("fantasy_point_difference")
        )
    )


def prepare_player_stats(
    source,
    season,
    settings,
    scoring,
):
    selected, missing_optional = select_planned_columns(
        source,
        "weekly_player_stats",
        PLAYER_STAT_COLUMNS,
        PLAYER_STAT_REQUIRED_COLUMNS,
    )

    prepared = (
        selected
        .filter(
            (pl.col("season_type")
            == settings["data"]["season_type"])
            & pl.col("position").is_in(
                settings["data"]["core_positions"]
            )
        )
    )

    prepared = normalize_text_columns(
        prepared,
        [
            "player_id",
            "game_id",
            "team",
            "opponent_team",
        ],
    )

    prepared = add_data_split(
        prepared,
        season,
        settings,
    )

    prepared = calculate_fantasy_points(
        prepared,
        scoring,
    )

    prepared = prepared.sort(
        ["season", "week", "player_id"]
    )

    return prepared, missing_optional


def prepare_schedules(source, season, settings):
    selected, missing_optional = select_planned_columns(
        source,
        "schedules",
        SCHEDULE_COLUMNS,
        SCHEDULE_REQUIRED_COLUMNS,
    )

    prepared = selected.filter(
        pl.col("game_type")
        == settings["data"]["season_type"]
    )

    prepared = normalize_text_columns(
        prepared,
        [
            "game_id",
            "away_team",
            "home_team",
        ],
    )

    prepared = add_data_split(
        prepared,
        season,
        settings,
    )

    prepared = prepared.sort(
        ["season", "week", "game_id"]
    )

    return prepared, missing_optional


def prepare_rosters(
    source,
    season,
    settings,
    player_identity,
):
    selected, missing_optional = select_planned_columns(
        source,
        "weekly_rosters",
        ROSTER_COLUMNS,
        ROSTER_REQUIRED_COLUMNS,
    )

    prepared = selected.filter(
        pl.col("game_type")
        == settings["data"]["season_type"]
    )

    prepared = normalize_text_columns(
        prepared,
        [
            "gsis_id",
            "pfr_id",
            "espn_id",
            "sleeper_id",
            "team",
        ],
    )
    rows_before_identity_join = prepared.height

    prepared = prepared.join(
        player_identity,
        left_on="gsis_id",
        right_on="player_id",
        how="left",
    )

    if prepared.height != rows_before_identity_join:
        raise ValueError(
            "Player identity join changed weekly "
            "roster row count."
        )

    prepared = prepared.with_columns(
        (
            available_text("pfr_id")
            & available_text("identity_pfr_id")
            & (
                pl.col("pfr_id")
                != pl.col("identity_pfr_id")
            )
        ).alias("pfr_id_conflict"),
        pl.when(
            available_text("identity_pfr_id")
        )
        .then(pl.lit("player_identity"))
        .when(available_text("pfr_id"))
        .then(pl.lit("weekly_roster"))
        .otherwise(pl.lit("unavailable"))
        .alias("pfr_id_source"),
    )

    prepared = (
        prepared
        .with_columns(
            pl.coalesce(
                "identity_pfr_id",
                "pfr_id",
            ).alias("pfr_id")
        )
        .drop("identity_pfr_id")
    )

    prepared = add_data_split(
        prepared,
        season,
        settings,
    )

    prepared = prepared.sort(
        [
            "season",
            "week",
            "team",
            "gsis_id",
            "full_name",
        ]
    )

    return prepared, missing_optional


def prepare_injuries(source, season, settings):
    selected, missing_optional = select_planned_columns(
        source,
        "injuries",
        INJURY_COLUMNS,
        INJURY_REQUIRED_COLUMNS,
    )

    prepared = selected.filter(
        pl.col("game_type")
        == settings["data"]["season_type"]
    )

    prepared = normalize_text_columns(
        prepared,
        [
            "gsis_id",
            "team",
            "position",
            "full_name",
            "report_primary_injury",
            "report_secondary_injury",
            "report_status",
            "practice_primary_injury",
            "practice_secondary_injury",
            "practice_status",
        ],
    )

    injury_key = [
        "season",
        "week",
        "team",
        "gsis_id",
    ]

    valid = prepared.filter(
        available_text("gsis_id")
    )

    unavailable = prepared.filter(
        ~available_text("gsis_id")
    )

    repeated_keys = (
        valid
        .group_by(injury_key)
        .len()
        .filter(pl.col("len") > 1)
        .select(injury_key)
    )

    if repeated_keys.height:
        repeated_rows = valid.join(
            repeated_keys,
            on=injury_key,
            how="inner",
        )

        undated_groups = (
            repeated_rows
            .group_by(injury_key)
            .agg(
                pl.col("date_modified")
                .is_not_null()
                .sum()
                .alias("dated_rows")
            )
            .filter(pl.col("dated_rows") == 0)
            .height
        )

        if undated_groups:
            raise ValueError(
                f"injuries {season} contains "
                f"{undated_groups:,} repeated key "
                "groups without update timestamps."
            )

        latest_timestamps = (
            repeated_rows
            .group_by(injury_key)
            .agg(
                pl.col("date_modified")
                .max()
                .alias("latest_date_modified")
            )
        )

        latest_rows = (
            repeated_rows
            .join(
                latest_timestamps,
                on=injury_key,
                how="inner",
            )
            .filter(
                pl.col("date_modified")
                == pl.col("latest_date_modified")
            )
        )

        tied_latest_groups = (
            latest_rows
            .group_by(injury_key)
            .len()
            .filter(pl.col("len") > 1)
            .height
        )

        if tied_latest_groups:
            raise ValueError(
                f"injuries {season} contains "
                f"{tied_latest_groups:,} repeated "
                "key groups with tied latest "
                "timestamps."
            )

        valid = (
            valid
            .sort(
                injury_key + ["date_modified"],
                descending=[
                    False,
                    False,
                    False,
                    False,
                    True,
                ],
                nulls_last=True,
            )
            .unique(
                subset=injury_key,
                keep="first",
                maintain_order=True,
            )
        )

    prepared = pl.concat(
        [valid, unavailable],
        how="diagonal_relaxed",
    )

    prepared = add_data_split(
        prepared,
        season,
        settings,
    )

    prepared = prepared.sort(
        [
            "season",
            "week",
            "team",
            "gsis_id",
            "full_name",
        ]
    )

    return prepared, missing_optional


def prepare_depth_charts(source, season, settings):
    if "dt" in source.columns:
        selected, missing_optional = select_planned_columns(
            source,
            "depth_charts",
            DEPTH_CHART_COLUMNS,
            DEPTH_CHART_REQUIRED_COLUMNS,
        )

        prepared = normalize_text_columns(
            selected,
            ["gsis_id", "espn_id", "team"],
        )

        prepared = prepared.with_columns(
            pl.lit(season)
            .cast(pl.Int32)
            .alias("source_season"),
            pl.lit("timestamped")
            .alias("depth_source_format"),
            pl.lit(season)
            .cast(pl.Int32)
            .alias("season"),
            pl.lit(None, dtype=pl.Int32)
            .alias("week"),
            pl.lit(None, dtype=pl.String)
            .alias("game_type"),
            pl.col("dt")
            .str
            .to_datetime(
                format="%Y-%m-%dT%H:%M:%SZ",
                time_zone=settings["temporal"]["timezone"],
                strict=False,
            )
            .alias("depth_timestamp"),
            pl.lit(None, dtype=pl.String)
            .alias("roster_position"),
        )

        invalid_timestamps = (
            prepared
            .get_column("depth_timestamp")
            .null_count()
        )

        if invalid_timestamps:
            raise ValueError(
                f"depth_charts {season} contains "
                f"{invalid_timestamps:,} invalid timestamps."
            )

        missing_optional = sorted(
            set(
                missing_optional
                + [
                    "season",
                    "week",
                    "game_type",
                    "roster_position",
                ]
            )
        )

        sort_columns = [
            "depth_timestamp",
            "team",
            "gsis_id",
            "pos_abb",
            "pos_slot",
        ]

    elif "week" in source.columns:
        selected, missing_optional = select_planned_columns(
            source,
            "depth_charts",
            LEGACY_DEPTH_CHART_COLUMNS,
            LEGACY_DEPTH_CHART_REQUIRED_COLUMNS,
        )

        selected = selected.filter(
            pl.col("game_type")
            == settings["data"]["season_type"]
        )

        selected = selected.unique(
            maintain_order=True
        )

        selected = normalize_text_columns(
            selected,
            ["gsis_id", "club_code"],
        )

        prepared = selected.select(
            pl.lit(season)
            .cast(pl.Int32)
            .alias("source_season"),
            pl.lit("legacy_weekly")
            .alias("depth_source_format"),
            pl.col("season"),
            pl.col("week"),
            pl.col("game_type"),
            pl.lit(None, dtype=pl.String)
            .alias("dt"),
            pl.lit(
                None,
                dtype=pl.Datetime(
                    time_zone=settings["temporal"]["timezone"]
                ),
            )
            .alias("depth_timestamp"),
            pl.col("club_code").alias("team"),
            pl.col("full_name").alias("player_name"),
            pl.lit(None, dtype=pl.String)
            .alias("espn_id"),
            pl.col("gsis_id"),
            pl.col("position")
            .alias("roster_position"),
            pl.lit(None, dtype=pl.String)
            .alias("pos_grp_id"),
            pl.col("formation").alias("pos_grp"),
            pl.lit(None, dtype=pl.String)
            .alias("pos_id"),
            pl.col("depth_position")
            .alias("pos_name"),
            pl.col("depth_position")
            .alias("pos_abb"),
            pl.lit(None, dtype=pl.Int32)
            .alias("pos_slot"),
            pl.col("depth_team")
            .cast(pl.Int32, strict=False)
            .alias("pos_rank"),
        )

        invalid_ranks = (
            prepared
            .get_column("pos_rank")
            .null_count()
        )

        if invalid_ranks:
            raise ValueError(
                f"depth_charts {season} contains "
                f"{invalid_ranks:,} invalid legacy depth ranks."
            )

        missing_optional = sorted(
            set(
                missing_optional
                + [
                    "dt",
                    "depth_timestamp",
                    "espn_id",
                    "pos_grp_id",
                    "pos_id",
                    "pos_slot",
                ]
            )
        )

        sort_columns = [
            "season",
            "week",
            "team",
            "gsis_id",
            "pos_grp",
            "pos_abb",
            "pos_rank",
        ]

    else:
        raise ValueError(
            f"depth_charts {season} uses an unsupported schema."
        )

    prepared = prepared.select(
        DEPTH_CHART_OUTPUT_COLUMNS
    )

    prepared = add_data_split(
        prepared,
        season,
        settings,
    )

    prepared = prepared.sort(sort_columns)

    return prepared, missing_optional

def prepare_snap_counts(source, season, settings):
    selected, missing_optional = select_planned_columns(
        source,
        "snap_counts",
        SNAP_COUNT_COLUMNS,
        SNAP_COUNT_REQUIRED_COLUMNS,
    )

    prepared = selected.filter(
        pl.col("game_type")
        == settings["data"]["season_type"]
    )

    prepared = normalize_text_columns(
        prepared,
        [
            "game_id",
            "pfr_player_id",
            "team",
            "opponent",
        ],
    )

    prepared = add_data_split(
        prepared,
        season,
        settings,
    )

    prepared = prepared.sort(
        [
            "season",
            "week",
            "game_id",
            "team",
            "pfr_player_id",
        ]
    )

    return prepared, missing_optional

def valid_key_rows(dataframe, key_columns):
    valid = dataframe

    for column in key_columns:
        if dataframe.schema[column] == pl.String:
            valid = valid.filter(
                available_text(column)
            )
        else:
            valid = valid.filter(
                pl.col(column).is_not_null()
            )

    return valid


def key_quality(
    dataframe,
    dataset_name,
    key_columns,
    fail_on_unavailable=False,
):
    valid = valid_key_rows(
        dataframe,
        key_columns,
    )

    unavailable_rows = (
        dataframe.height - valid.height
    )

    repeated_groups = (
        valid
        .group_by(key_columns)
        .len()
        .filter(pl.col("len") > 1)
        .height
    )

    if fail_on_unavailable and unavailable_rows:
        raise ValueError(
            f"{dataset_name} contains "
            f"{unavailable_rows:,} rows with an "
            f"unavailable required key."
        )

    if repeated_groups:
        raise ValueError(
            f"{dataset_name} contains "
            f"{repeated_groups:,} repeated key groups "
            f"for {key_columns}."
        )

    return {
        "unavailable_key_rows": unavailable_rows,
        "duplicate_key_groups": repeated_groups,
    }


def join_coverage(base, lookup, join_columns):
    lookup_keys = (
        lookup
        .select(join_columns)
        .unique()
        .with_columns(
            pl.lit(True).alias("__matched")
        )
    )

    joined = base.join(
        lookup_keys,
        on=join_columns,
        how="left",
    )

    matched_rows = int(
        joined
        .get_column("__matched")
        .fill_null(False)
        .sum()
    )

    match_rate = (
        round(
            (matched_rows / joined.height) * 100,
            2,
        )
        if joined.height
        else 0.0
    )

    return {
        "base_rows": joined.height,
        "matched_rows": matched_rows,
        "unmatched_rows": joined.height - matched_rows,
        "match_rate_pct": match_rate,
    }


def validate_season(
    season,
    player_stats,
    schedules,
    rosters,
    injuries,
    depth_charts,
    snap_counts,
    settings,
):
    print_section(f"QUALITY CONTROLS: {season}")

    quality = {}

    quality["weekly_player_stats"] = key_quality(
        player_stats,
        "weekly_player_stats",
        ["season", "week", "player_id"],
        fail_on_unavailable=True,
    )

    quality["schedules"] = key_quality(
        schedules,
        "schedules",
        ["game_id"],
        fail_on_unavailable=True,
    )

    home_team_weeks = schedules.select(
        "season",
        "week",
        pl.col("home_team").alias("team"),
    )

    away_team_weeks = schedules.select(
        "season",
        "week",
        pl.col("away_team").alias("team"),
    )

    team_weeks = pl.concat(
        [home_team_weeks, away_team_weeks]
    )

    key_quality(
        team_weeks,
        "schedule_team_week",
        ["season", "week", "team"],
        fail_on_unavailable=True,
    )

    quality["weekly_rosters"] = key_quality(
        rosters,
        "weekly_rosters",
        ["season", "week", "team", "gsis_id"],
    )

    multi_team_roster_player_week_groups = (
        rosters
        .filter(available_text("gsis_id"))
        .group_by(
            ["season", "week", "gsis_id"]
        )
        .agg(
            pl.col("team")
            .n_unique()
            .alias("distinct_teams")
        )
        .filter(
            pl.col("distinct_teams") > 1
        )
        .height
    )

    quality["injuries"] = key_quality(
        injuries,
        "injuries",
        ["season", "week", "team", "gsis_id"],
    )

    depth_formats = set(
        depth_charts
        .get_column("depth_source_format")
        .unique()
        .to_list()
    )

    if depth_formats == {"legacy_weekly"}:
        quality["depth_charts"] = key_quality(
            depth_charts,
            "depth_charts",
            [
                "season",
                "week",
                "team",
                "gsis_id",
                "pos_grp",
                "pos_abb",
                "pos_rank",
            ],
        )

    elif depth_formats == {"timestamped"}:
        quality["depth_charts"] = key_quality(
            depth_charts,
            "depth_charts",
            [
                "dt",
                "team",
                "gsis_id",
                "pos_abb",
                "pos_slot",
            ],
        )

    else:
        raise ValueError(
            f"depth_charts {season} contains unexpected "
            f"source formats: {sorted(depth_formats)}"
        )

    quality["snap_counts"] = key_quality(
        snap_counts,
        "snap_counts",
        [
            "season",
            "week",
            "game_id",
            "team",
            "pfr_player_id",
        ],
        fail_on_unavailable=True,
    )

    key_quality(
        snap_counts,
        "snap_count_player_week",
        [
            "season",
            "week",
            "team",
            "pfr_player_id",
        ],
        fail_on_unavailable=True,
    )

    schedule_keys = schedules.select(
        "game_id"
    )

    schedule_coverage = join_coverage(
        player_stats,
        schedule_keys,
        ["game_id"],
    )

    roster_gsis_keys = (
        rosters
        .filter(available_text("gsis_id"))
        .select(
            "season",
            "week",
            "team",
            pl.col("gsis_id").alias("player_id"),
        )
    )

    roster_coverage = join_coverage(
        player_stats,
        roster_gsis_keys,
        ["season", "week", "team", "player_id"],
    )

    valid_crosswalk = rosters.filter(
        available_text("gsis_id")
        & available_text("pfr_id")
    )

    crosswalk_conflicts = (
        valid_crosswalk
        .group_by(
            ["season", "week", "team", "gsis_id"]
        )
        .agg(
            pl.col("pfr_id")
            .n_unique()
            .alias("distinct_pfr_ids")
        )
        .filter(
            pl.col("distinct_pfr_ids") > 1
        )
        .height
    )

    if crosswalk_conflicts:
        raise ValueError(
            f"Season {season} contains "
            f"{crosswalk_conflicts:,} conflicting "
            "GSIS-to-PFR crosswalk groups."
        )

    roster_crosswalk = (
        valid_crosswalk
        .group_by(
            ["season", "week", "team", "gsis_id"]
        )
        .agg(
            pl.col("pfr_id")
            .first()
            .alias("pfr_player_id")
        )
        .rename(
            {"gsis_id": "player_id"}
        )
    )

    stats_with_pfr = player_stats.join(
        roster_crosswalk,
        on=["season", "week", "team", "player_id"],
        how="left",
    )

    snap_keys = snap_counts.select(
        "season",
        "week",
        "team",
        "pfr_player_id",
    )

    snap_coverage = join_coverage(
        stats_with_pfr,
        snap_keys,
        [
            "season",
            "week",
            "team",
            "pfr_player_id",
        ],
    )

    tolerance = settings["quality"][
        "fantasy_point_tolerance"
    ]

    ppr_mismatches = (
        player_stats
        .filter(
            pl.col("fantasy_point_difference")
            .abs()
            > tolerance
        )
        .height
    )

    maximum_ppr_difference = (
        player_stats
        .get_column("fantasy_point_difference")
        .abs()
        .max()
        if player_stats.height
        else None
    )

    if ppr_mismatches:
        raise ValueError(
            f"Season {season} contains "
            f"{ppr_mismatches:,} fantasy-point "
            "reconciliation mismatches."
        )

    required_coverage = [
        (
            "stats_schedule",
            schedule_coverage,
            settings["quality"][
                "minimum_stats_schedule_match_pct"
            ],
        ),
        (
            "stats_roster",
            roster_coverage,
            settings["quality"][
                "minimum_stats_roster_match_pct"
            ],
        ),
        (
            "stats_snap",
            snap_coverage,
            settings["quality"][
                "minimum_stats_snap_match_pct"
            ],
        ),
    ]

    for (
        coverage_name,
        coverage_result,
        minimum_rate,
    ) in required_coverage:
        if (
            coverage_result["match_rate_pct"]
            < minimum_rate
        ):
            raise ValueError(
                f"Season {season} {coverage_name} "
                f"coverage is "
                f"{coverage_result['match_rate_pct']:.2f}%, "
                f"below the required {minimum_rate:.2f}%."
            )

    print(
        "multi_team_roster_player_week_groups="
        f"{multi_team_roster_player_week_groups:,}"
    )
    print(
        f"player_week_rows={player_stats.height:,}"
    )
    print(
        "stats_schedule_match_rate_pct="
        f"{schedule_coverage['match_rate_pct']:.2f}"
    )
    print(
        "stats_roster_match_rate_pct="
        f"{roster_coverage['match_rate_pct']:.2f}"
    )
    print(
        "stats_snap_match_rate_pct="
        f"{snap_coverage['match_rate_pct']:.2f}"
    )
    print(
        f"ppr_mismatch_rows={ppr_mismatches:,}"
    )
    print(
        "maximum_ppr_difference="
        f"{maximum_ppr_difference}"
    )

    return {
        "dataset_quality": quality,
        "schedule_coverage": schedule_coverage,
        "roster_coverage": roster_coverage,
        "snap_coverage": snap_coverage,
        "ppr_mismatch_rows": ppr_mismatches,
        "maximum_ppr_difference": (
            maximum_ppr_difference
        ),
        "multi_team_roster_player_week_groups": (
            multi_team_roster_player_week_groups
        ),
    }


def write_partition(
    dataset_name,
    season,
    dataframe,
    output_root,
):
    dataset_directory = (
        output_root
        / dataset_name
    )

    dataset_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        dataset_directory
        / f"{dataset_name}_{season}.parquet"
    )

    dataframe.write_parquet(
        output_path,
        compression="zstd",
    )

    print(
        f"Wrote {dataset_name} {season}: "
        f"{dataframe.height:,} rows"
    )

    return output_path


def make_manifest_row(
    season,
    split,
    dataset_name,
    source_rows,
    processed_rows,
    output_path,
    missing_optional,
    dataset_quality,
    season_quality,
):
    is_player_stats = (
        dataset_name == "weekly_player_stats"
    )

    return {
        "season": season,
        "data_split": split,
        "dataset_name": dataset_name,
        "source_rows": source_rows,
        "processed_rows": processed_rows,
        "unavailable_key_rows": (
            dataset_quality[
                "unavailable_key_rows"
            ]
        ),
        "duplicate_key_groups": (
            dataset_quality[
                "duplicate_key_groups"
            ]
        ),
        "missing_optional_columns": (
            ",".join(missing_optional)
            if missing_optional
            else ""
        ),
        "stats_schedule_match_pct": (
            season_quality[
                "schedule_coverage"
            ]["match_rate_pct"]
            if is_player_stats
            else None
        ),
        "stats_roster_match_pct": (
            season_quality[
                "roster_coverage"
            ]["match_rate_pct"]
            if is_player_stats
            else None
        ),
        "stats_snap_match_pct": (
            season_quality[
                "snap_coverage"
            ]["match_rate_pct"]
            if is_player_stats
            else None
        ),
        "ppr_mismatch_rows": (
            season_quality[
                "ppr_mismatch_rows"
            ]
            if is_player_stats
            else None
        ),
        "maximum_ppr_difference": (
            season_quality[
                "maximum_ppr_difference"
            ]
            if is_player_stats
            else None
        ),
        "output_file": (
            output_path
            .relative_to(PROJECT_ROOT)
            .as_posix()
        ),
    }


def main():
    args = parse_args()
    settings, config_path = load_settings(
        args.config
    )
    scoring = load_league_scoring()
    configure_cache()

    player_identity = prepare_player_identity(
        nfl.load_players()
    )

    output_root = (
        resolve_project_path(
            settings["output"][
                "processed_directory"
            ]
        )
        / "historical"
    )

    sample_root = resolve_project_path(
        settings["output"]["sample_directory"]
    )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    sample_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    seasons = settings["data"]["seasons"]
    sample_limit = settings["output"][
        "sample_row_limit"
    ]

    sample_rows_per_season = max(
        1,
        math.ceil(
            sample_limit / len(seasons)
        ),
    )

    print_section("HISTORICAL EXTRACTION")
    print(f"Configuration: {config_path}")
    print(
        "Seasons: "
        + ", ".join(
            str(season)
            for season in seasons
        )
    )
    print(f"Output directory: {output_root}")
    print(f"Sample directory: {sample_root}")

    manifest_rows = []
    sample_frames = {
        "weekly_player_stats": [],
        "schedules": [],
        "weekly_rosters": [],
        "injuries": [],
        "depth_charts": [],
        "snap_counts": [],
    }

    for season in seasons:
        print_section(f"LOADING SEASON {season}")

        source_frames = {
            "weekly_player_stats": (
                nfl.load_player_stats(
                    season,
                    summary_level="week",
                )
            ),
            "schedules": (
                nfl.load_schedules(season)
            ),
            "weekly_rosters": (
                nfl.load_rosters_weekly(season)
            ),
            "injuries": (
                nfl.load_injuries(season)
            ),
            "depth_charts": (
                nfl.load_depth_charts(season)
            ),
            "snap_counts": (
                nfl.load_snap_counts(season)
            ),
        }

        prepared_frames = {}
        missing_optional = {}

        (
            prepared_frames["weekly_player_stats"],
            missing_optional["weekly_player_stats"],
        ) = prepare_player_stats(
            source_frames["weekly_player_stats"],
            season,
            settings,
            scoring,
        )

        (
            prepared_frames["schedules"],
            missing_optional["schedules"],
        ) = prepare_schedules(
            source_frames["schedules"],
            season,
            settings,
        )

        (
            prepared_frames["weekly_rosters"],
            missing_optional["weekly_rosters"],
        ) = prepare_rosters(
            source_frames["weekly_rosters"],
            season,
            settings,
            player_identity,
        )

        (
            prepared_frames["injuries"],
            missing_optional["injuries"],
        ) = prepare_injuries(
            source_frames["injuries"],
            season,
            settings,
        )

        (
            prepared_frames["depth_charts"],
            missing_optional["depth_charts"],
        ) = prepare_depth_charts(
            source_frames["depth_charts"],
            season,
            settings,
        )

        (
            prepared_frames["snap_counts"],
            missing_optional["snap_counts"],
        ) = prepare_snap_counts(
            source_frames["snap_counts"],
            season,
            settings,
        )

        season_quality = validate_season(
            season,
            prepared_frames[
                "weekly_player_stats"
            ],
            prepared_frames["schedules"],
            prepared_frames[
                "weekly_rosters"
            ],
            prepared_frames["injuries"],
            prepared_frames["depth_charts"],
            prepared_frames["snap_counts"],
            settings,
        )

        current_split = split_name(
            season,
            settings,
        )

        for (
            dataset_name,
            dataframe,
        ) in prepared_frames.items():
            output_path = write_partition(
                dataset_name,
                season,
                dataframe,
                output_root,
            )

            sample_frames[
                dataset_name
            ].append(
                dataframe.head(
                    sample_rows_per_season
                )
            )

            manifest_rows.append(
                make_manifest_row(
                    season=season,
                    split=current_split,
                    dataset_name=dataset_name,
                    source_rows=(
                        source_frames[
                            dataset_name
                        ].height
                    ),
                    processed_rows=(
                        dataframe.height
                    ),
                    output_path=output_path,
                    missing_optional=(
                        missing_optional[
                            dataset_name
                        ]
                    ),
                    dataset_quality=(
                        season_quality[
                            "dataset_quality"
                        ][dataset_name]
                    ),
                    season_quality=(
                        season_quality
                    ),
                )
            )

    print_section("WRITING SAMPLES AND MANIFEST")

    if settings["output"]["write_csv_samples"]:
        for (
            dataset_name,
            frames,
        ) in sample_frames.items():
            combined_sample = (
                pl.concat(
                    frames,
                    how="diagonal_relaxed",
                )
                .head(sample_limit)
            )

            sample_path = (
                sample_root
                / f"{dataset_name}_sample.csv"
            )

            combined_sample.write_csv(
                sample_path
            )

            print(
                f"Wrote {sample_path.name}: "
                f"{combined_sample.height:,} rows"
            )

    manifest = (
        pl.DataFrame(
            manifest_rows,
            strict=False,
        )
        .sort(
            ["season", "dataset_name"]
        )
    )

    manifest_path = (
        sample_root
        / "historical_extraction_manifest.csv"
    )

    manifest.write_csv(manifest_path)

    print(
        f"Wrote {manifest_path.name}: "
        f"{manifest.height:,} rows"
    )

    print_section("HISTORICAL EXTRACTION COMPLETE")
    print(
        f"seasons_processed={len(seasons)}"
    )
    print(
        f"datasets_per_season="
        f"{len(sample_frames)}"
    )
    print(
        f"manifest_rows={manifest.height}"
    )
    print(
        "All configured historical seasons passed "
        "the extraction quality controls."
    )


if __name__ == "__main__":
    main()