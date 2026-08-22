"""Build leakage-safe target-free features for a future NFL week."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tomllib
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

import nflreadpy as nfl
import numpy as np
import pandas as pd
import polars as pl
import pyarrow.parquet as pq
from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import Engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    PROJECT_ROOT / "config" / "future_features_settings.toml"
)
VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

TEAM_ALIASES = {
    "AZ": "ARI",
    "ARZ": "ARI",
    "JAC": "JAX",
    "OAK": "LV",
    "SD": "LAC",
    "STL": "LA",
}

PLAYER_HISTORY_COLUMNS = [
    "season",
    "week",
    "game_id",
    "game_date",
    "player_id",
    "position",
    "team",
    "completions",
    "attempts",
    "passing_yards",
    "carries",
    "rushing_yards",
    "receptions",
    "targets",
    "receiving_yards",
    "target_share",
    "air_yards_share",
    "wopr",
    "touches",
    "position_adjusted_opportunities",
    "yards_from_scrimmage",
    "total_offensive_yards",
    "total_offensive_tds",
    "offense_snaps",
    "offense_pct",
    "has_snap_record",
    "target_fantasy_points_ppr",
]

OPPONENT_HISTORY_COLUMNS = [
    "season",
    "week",
    "game_id",
    "game_date",
    "defensive_team",
    "position",
    "fantasy_points_ppr_allowed",
    "passing_yards_allowed",
    "rushing_yards_allowed",
    "receiving_yards_allowed",
    "position_adjusted_opportunities_allowed",
    "total_offensive_tds_allowed",
]

LIVE_SCHEDULE_COLUMNS = [
    "game_id",
    "season",
    "game_type",
    "week",
    "gameday",
    "away_team",
    "home_team",
    "away_rest",
    "home_rest",
    "spread_line",
    "total_line",
    "div_game",
    "roof",
    "surface",
]

LIVE_ROSTER_COLUMNS = [
    "season",
    "team",
    "position",
    "status",
    "full_name",
    "football_name",
    "gsis_id",
    "espn_id",
]

LIVE_DEPTH_COLUMNS = [
    "dt",
    "team",
    "player_name",
    "espn_id",
    "gsis_id",
    "pos_abb",
    "pos_slot",
    "pos_rank",
]

CURRENT_CONTEXT_COLUMNS = [
    "game_location",
    "is_home",
    "team_rest",
    "opponent_rest",
    "source_spread_line",
    "total_line",
    "div_game",
    "roof",
    "surface",
]


def print_section(title: str) -> None:
    """Print a readable console section."""

    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def display_path(path: Path) -> str:
    """Return a repository-relative path when possible."""

    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Build the frozen target-free future-week feature contract."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--replay",
        action="store_true",
        help="Rebuild the configured historical replay week.",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Build features from current nflverse sources.",
    )
    parser.add_argument(
        "--season",
        type=int,
        help="Target season for live mode; defaults to configuration.",
    )
    parser.add_argument(
        "--week",
        type=int,
        help="Target week for live mode; defaults to configuration.",
    )
    parser.add_argument(
        "--as-of",
        help=(
            "Required UTC-aware ISO-8601 cutoff for live mode. "
            "Depth records after this instant are excluded."
        ),
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to the future-feature settings TOML file.",
    )
    parser.add_argument(
        "--confirm-build",
        required=True,
        help="Required confirmation token from the configuration.",
    )
    parser.add_argument(
        "--orchestrated-revision",
        help=(
            "Git revision verified by run_weekly_pipeline.py before any "
            "weekly outputs were created. Manual runs should omit this."
        ),
    )
    parser.add_argument(
        "--player-history",
        help=(
            "Optional portable player-history Parquet file. Must be used "
            "with --opponent-history; otherwise MySQL remains the source."
        ),
    )
    parser.add_argument(
        "--opponent-history",
        help=(
            "Optional portable opponent-history Parquet file. Must be used "
            "with --player-history; otherwise MySQL remains the source."
        ),
    )
    arguments = parser.parse_args()
    if bool(arguments.player_history) != bool(arguments.opponent_history):
        parser.error(
            "--player-history and --opponent-history must be supplied together."
        )
    return arguments


def load_toml(path: Path) -> dict[str, Any]:
    """Load one TOML file."""

    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with path.open("rb") as file_handle:
        return tomllib.load(file_handle)


def sha256_file(path: Path) -> str:
    """Return a file SHA-256 value."""

    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_project_path(value: str) -> Path:
    """Resolve a configuration path relative to the project root."""

    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def require_identifier(value: str, label: str) -> str:
    """Validate a configured SQL identifier."""

    if not VALID_IDENTIFIER.fullmatch(value):
        raise ValueError(f"Invalid {label}: {value!r}")
    return value


def unique_in_order(values: list[str]) -> list[str]:
    """Return values once while preserving their configured order."""

    return list(dict.fromkeys(values))


def configured_contract(
    model_settings: dict[str, Any],
    configuration: dict[str, Any],
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Return and validate the frozen feature contract."""

    columns = model_settings["columns"]
    categorical = list(columns["categorical_features"])
    numeric = list(columns["numeric_features"])
    predictors = categorical + numeric
    metadata = list(
        configuration["quality"]["required_metadata_columns"]
    )

    expected = int(
        configuration["quality"]["expected_predictor_features"]
    )
    if len(predictors) != expected:
        raise ValueError(
            f"Expected {expected} predictors but found {len(predictors)}."
        )
    if len(set(predictors)) != len(predictors):
        raise ValueError("The predictor contract contains duplicates.")
    if len(set(metadata)) != len(metadata):
        raise ValueError("The metadata contract contains duplicates.")
    if columns["target"] in metadata or columns["target"] in predictors:
        raise ValueError("The target is present in the future input contract.")

    output_columns = unique_in_order(metadata + predictors)
    return metadata, categorical, numeric, output_columns


def validate_configuration(
    configuration: dict[str, Any],
    confirmation: str,
) -> None:
    """Validate non-negotiable future-feature safeguards."""

    settings = configuration["future_features"]
    if confirmation != settings["confirmation_token"]:
        raise ValueError("The future-feature confirmation token is invalid.")
    if settings["history_cutoff_rule"] != "strict_prior_week":
        raise ValueError("The history cutoff rule must be strict_prior_week.")
    if settings["allow_same_week_history"]:
        raise ValueError("Same-week history must remain disabled.")
    if settings["load_target_week_outcome"]:
        raise ValueError("Target-week outcome loading must remain disabled.")
    if not settings["fail_if_output_exists"]:
        raise ValueError("Output replacement protection must remain enabled.")


def run_git(arguments: list[str]) -> str:
    """Run one read-only Git command."""

    result = subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def validate_orchestrated_changes() -> None:
    """Allow only generated weekly evidence after the clean start gate."""

    commands = [
        ["diff", "--name-only"],
        ["diff", "--cached", "--name-only"],
        ["ls-files", "--others", "--exclude-standard"],
    ]
    changed = {
        path.replace("\\", "/")
        for command in commands
        for path in run_git(command).splitlines()
        if path.strip()
    }
    allowed_prefixes = (
        "data/sample/future_features_",
        "results/public/",
        "results/reports/weekly_rankings_",
        "results/tables/future_features_",
        "results/tables/history_refresh_",
        "results/tables/inference_",
        "results/tables/weekly_rankings_",
    )
    unexpected = sorted(
        path for path in changed if not path.startswith(allowed_prefixes)
    )
    if unexpected:
        raise RuntimeError(
            "The orchestrated worktree contains non-output changes: "
            + ", ".join(unexpected)
        )


def validate_git_state(
    configuration: dict[str, Any],
    orchestrated_revision: str | None = None,
) -> str:
    """Require a committed protocol and a clean worktree."""

    current_commit = run_git(["rev-parse", "HEAD"])
    if orchestrated_revision is not None:
        expected_commit = run_git(
            ["rev-parse", str(orchestrated_revision)]
        )
        if current_commit != expected_commit:
            raise RuntimeError(
                "The orchestrated revision no longer matches HEAD."
            )
        validate_orchestrated_changes()
        print(f"orchestrated_revision={expected_commit}")
    elif configuration["future_features"]["require_clean_worktree"]:
        status = run_git(["status", "--porcelain"])
        if status:
            raise RuntimeError(
                "Git worktree is not clean. Commit the future-feature "
                "protocol before executing a controlled run."
            )

    lineage_commit = configuration["lineage"][
        "feature_pipeline_commit"
    ]
    result = subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            lineage_commit,
            current_commit,
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "The frozen historical feature commit is not an ancestor "
            "of the current commit."
        )

    print(f"current_commit={current_commit}")
    print(f"feature_pipeline_commit={lineage_commit}")
    print("git_worktree_clean=PASS")
    return current_commit


def validate_lineage_hashes(
    configuration: dict[str, Any],
    mode: str,
) -> dict[str, str]:
    """Verify frozen configuration and replay inputs."""

    inputs = configuration["inputs"]
    lineage = configuration["lineage"]
    paths = {
        "model_settings": resolve_project_path(
            inputs["model_settings_path"]
        ),
        "feature_sql": resolve_project_path(inputs["feature_sql_path"]),
    }
    expected = {
        "model_settings": lineage["model_settings_sha256"],
        "feature_sql": lineage["feature_sql_sha256"],
    }
    if mode == "replay":
        paths["replay_reference"] = resolve_project_path(
            inputs["replay_reference_path"]
        )
        expected["replay_reference"] = lineage[
            "replay_reference_sha256"
        ]

    observed: dict[str, str] = {}
    for name, path in paths.items():
        if not path.exists():
            raise FileNotFoundError(f"Required input not found: {path}")
        observed[name] = sha256_file(path)
        if observed[name] != expected[name]:
            raise ValueError(f"Frozen {name} SHA-256 does not match.")
        print(f"{name}_sha256={observed[name]}")

    print("frozen_lineage_hashes=PASS")
    return observed


def parse_as_of(value: str | None) -> datetime:
    """Parse a required timezone-aware live cutoff as UTC."""

    if not value:
        raise ValueError("Live mode requires --as-of.")

    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("--as-of must include a UTC offset or Z suffix.")
    return parsed.astimezone(timezone.utc)


def format_template(template: str, season: int, week: int) -> Path:
    """Resolve one configured season-week output template."""

    return resolve_project_path(
        template.format(season=season, week=week)
    )


def build_run_specification(
    arguments: argparse.Namespace,
    configuration: dict[str, Any],
) -> dict[str, Any]:
    """Resolve target period, sources, and protected output paths."""

    if arguments.replay:
        replay = configuration["replay"]
        return {
            "mode": "replay",
            "season": int(replay["season"]),
            "week": int(replay["week"]),
            "as_of": None,
            "features": resolve_project_path(replay["features_path"]),
            "sample": resolve_project_path(replay["sample_path"]),
            "sample_rows": int(replay["sample_rows"]),
            "verification": resolve_project_path(
                replay["verification_path"]
            ),
            "manifest": resolve_project_path(
                replay["run_manifest_path"]
            ),
            "snapshot_directory": None,
            "expected_rows": int(replay["expected_rows"]),
        }

    live = configuration["live"]
    season = int(arguments.season or live["season"])
    week = int(arguments.week or live["week"])
    if not 1 <= week <= 18:
        raise ValueError("Target week must be between 1 and 18.")

    return {
        "mode": "live",
        "season": season,
        "week": week,
        "as_of": parse_as_of(arguments.as_of),
        "features": format_template(
            live["features_path_template"], season, week
        ),
        "sample": format_template(
            live["sample_path_template"], season, week
        ),
        "sample_rows": int(live["sample_rows"]),
        "verification": None,
        "manifest": format_template(
            live["run_manifest_path_template"], season, week
        ),
        "snapshot_directory": format_template(
            live["snapshot_directory_template"], season, week
        ),
        "expected_rows": None,
    }


def validate_output_paths(run_specification: dict[str, Any]) -> None:
    """Reject existing outputs before any source is loaded."""

    paths = [
        run_specification["features"],
        run_specification["sample"],
        run_specification["manifest"],
    ]
    if run_specification["verification"] is not None:
        paths.append(run_specification["verification"])

    existing = [path for path in paths if path.exists()]
    snapshot_directory = run_specification["snapshot_directory"]
    if snapshot_directory is not None and snapshot_directory.exists():
        existing.append(snapshot_directory)
    if existing:
        raise FileExistsError(
            "Protected future-feature outputs already exist: "
            + ", ".join(display_path(path) for path in existing)
        )


def required_environment_value(name: str) -> str:
    """Return a required private environment value."""

    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment value: {name}")
    if value in {"your_mysql_username", "your_mysql_password"}:
        raise ValueError(f"Environment value still uses a template: {name}")
    return value


def build_database_engine() -> Engine:
    """Build a private SQLAlchemy connection without printing secrets."""

    load_dotenv(PROJECT_ROOT / ".env")
    database_url = URL.create(
        drivername="mysql+pymysql",
        username=required_environment_value("MYSQL_USER"),
        password=required_environment_value("MYSQL_PASSWORD"),
        host=required_environment_value("MYSQL_HOST"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=required_environment_value("MYSQL_DATABASE"),
    )
    return create_engine(database_url, pool_pre_ping=True)


def quoted_columns(columns: list[str]) -> str:
    """Return validated backtick-quoted column identifiers."""

    return ",\n            ".join(
        f"`{require_identifier(column, 'column')}`" for column in columns
    )


def load_prior_history(
    engine: Engine,
    configuration: dict[str, Any],
    season: int,
    week: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Load only rows from weeks strictly before the target week."""

    inputs = configuration["inputs"]
    player_table = require_identifier(
        inputs["player_history_table"], "player history table"
    )
    opponent_table = require_identifier(
        inputs["opponent_history_table"], "opponent history table"
    )
    predicate = "(`season` < :season OR (`season` = :season AND `week` < :week))"
    player_query = text(
        f"""
        SELECT
            {quoted_columns(PLAYER_HISTORY_COLUMNS)}
        FROM `{player_table}`
        WHERE {predicate}
        ORDER BY `player_id`, `season`, `week`, `game_date`, `game_id`
        """
    )
    opponent_query = text(
        f"""
        SELECT
            {quoted_columns(OPPONENT_HISTORY_COLUMNS)}
        FROM `{opponent_table}`
        WHERE {predicate}
        ORDER BY `defensive_team`, `position`, `season`, `week`,
            `game_date`, `game_id`
        """
    )
    params = {"season": season, "week": week}

    with engine.connect() as connection:
        database_name = connection.execute(
            text("SELECT DATABASE()")
        ).scalar_one()
        player_history = pd.read_sql_query(
            player_query, connection, params=params
        )
        opponent_history = pd.read_sql_query(
            opponent_query, connection, params=params
        )

    return validate_prior_history_frames(
        player_history,
        opponent_history,
        configuration,
        season,
        week,
        str(database_name),
    )


def validate_prior_history_frames(
    player_history: pd.DataFrame,
    opponent_history: pd.DataFrame,
    configuration: dict[str, Any],
    season: int,
    week: int,
    source_name: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Validate portable or database history at the required grains."""

    missing_player = sorted(
        set(PLAYER_HISTORY_COLUMNS) - set(player_history.columns)
    )
    missing_opponent = sorted(
        set(OPPONENT_HISTORY_COLUMNS) - set(opponent_history.columns)
    )
    if missing_player or missing_opponent:
        raise ValueError(
            "History contract columns are missing: "
            f"player={missing_player}, opponent={missing_opponent}"
        )

    player_history = player_history.loc[:, PLAYER_HISTORY_COLUMNS].copy()
    opponent_history = opponent_history.loc[:, OPPONENT_HISTORY_COLUMNS].copy()
    for dataframe in (player_history, opponent_history):
        dataframe["game_date"] = pd.to_datetime(
            dataframe["game_date"]
        ).dt.normalize()

    quality = configuration["quality"]
    if len(player_history) < int(quality["minimum_player_history_rows"]):
        raise ValueError("Player history is unexpectedly empty.")
    if len(opponent_history) < int(
        quality["minimum_opponent_history_rows"]
    ):
        raise ValueError("Opponent history is unexpectedly empty.")

    player_duplicates = int(
        player_history.duplicated(["season", "week", "player_id"]).sum()
    )
    opponent_duplicates = int(
        opponent_history.duplicated(
            ["season", "week", "defensive_team", "position"]
        ).sum()
    )
    if player_duplicates or opponent_duplicates:
        raise ValueError("Validated history tables contain duplicate keys.")

    invalid_player_cutoff = int(
        (
            (player_history["season"] > season)
            | (
                (player_history["season"] == season)
                & (player_history["week"] >= week)
            )
        ).sum()
    )
    invalid_opponent_cutoff = int(
        (
            (opponent_history["season"] > season)
            | (
                (opponent_history["season"] == season)
                & (opponent_history["week"] >= week)
            )
        ).sum()
    )
    if invalid_player_cutoff or invalid_opponent_cutoff:
        raise ValueError("Same-week or future history rows were loaded.")

    history_summary = {
        "database_name": source_name,
        "player_history_rows": len(player_history),
        "opponent_history_rows": len(opponent_history),
        "maximum_player_history_date": player_history[
            "game_date"
        ].max(),
        "maximum_opponent_history_date": opponent_history[
            "game_date"
        ].max(),
        "player_history_duplicate_keys": player_duplicates,
        "opponent_history_duplicate_keys": opponent_duplicates,
        "same_week_history_rows_loaded": (
            invalid_player_cutoff + invalid_opponent_cutoff
        ),
    }
    print(f"database_name={source_name}")
    print(f"player_history_rows={len(player_history):,}")
    print(f"opponent_history_rows={len(opponent_history):,}")
    print("same_week_history_rows_loaded=0")
    print("history_grain_validation=PASS")
    return player_history, opponent_history, history_summary


def load_prior_history_files(
    player_path: Path,
    opponent_path: Path,
    configuration: dict[str, Any],
    season: int,
    week: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Load strict-prior-week history from portable Parquet files."""

    for label, path in {
        "player history": player_path,
        "opponent history": opponent_path,
    }.items():
        if not path.exists():
            raise FileNotFoundError(f"Portable {label} not found: {path}")
        if path.suffix.lower() != ".parquet":
            raise ValueError(f"Portable {label} must be Parquet: {path}")

    player_history = pd.read_parquet(
        player_path, columns=PLAYER_HISTORY_COLUMNS
    )
    opponent_history = pd.read_parquet(
        opponent_path, columns=OPPONENT_HISTORY_COLUMNS
    )
    player_history = player_history.loc[
        (player_history["season"] < season)
        | (
            player_history["season"].eq(season)
            & player_history["week"].lt(week)
        )
    ]
    opponent_history = opponent_history.loc[
        (opponent_history["season"] < season)
        | (
            opponent_history["season"].eq(season)
            & opponent_history["week"].lt(week)
        )
    ]
    player_history = player_history.sort_values(
        ["player_id", "season", "week", "game_date", "game_id"],
        kind="stable",
    ).reset_index(drop=True)
    opponent_history = opponent_history.sort_values(
        [
            "defensive_team",
            "position",
            "season",
            "week",
            "game_date",
            "game_id",
        ],
        kind="stable",
    ).reset_index(drop=True)
    return validate_prior_history_frames(
        player_history,
        opponent_history,
        configuration,
        season,
        week,
        "PORTABLE_PARQUET",
    )


def atomic_write_parquet(dataframe: pd.DataFrame, path: Path) -> None:
    """Write a pandas Parquet file without partial replacement."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.tmp{path.suffix}")
    dataframe.to_parquet(
        temporary, index=False, compression="snappy", engine="pyarrow"
    )
    os.replace(temporary, path)


def atomic_write_polars(dataframe: pl.DataFrame, path: Path) -> None:
    """Write a Polars Parquet snapshot atomically."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.tmp{path.suffix}")
    dataframe.write_parquet(temporary, compression="snappy")
    os.replace(temporary, path)


def atomic_write_csv(dataframe: pd.DataFrame, path: Path) -> None:
    """Write a CSV file without partial replacement."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.tmp{path.suffix}")
    dataframe.to_csv(temporary, index=False, lineterminator="\n")
    os.replace(temporary, path)


def require_source_columns(
    dataframe: pl.DataFrame,
    columns: list[str],
    source_name: str,
) -> pl.DataFrame:
    """Select the exact allowlisted columns from one live source."""

    missing = sorted(set(columns) - set(dataframe.columns))
    if missing:
        raise ValueError(
            f"{source_name} is missing required columns: {missing}"
        )
    return dataframe.select(columns)


def normalize_team_columns(
    dataframe: pl.DataFrame, columns: list[str]
) -> pl.DataFrame:
    """Normalize known cross-source NFL team abbreviations."""

    return dataframe.with_columns(
        [pl.col(column).replace(TEAM_ALIASES) for column in columns]
    )


def expand_team_schedule(schedule: pd.DataFrame) -> pd.DataFrame:
    """Expand one game row into reciprocal team-week context rows."""

    common = [
        "season",
        "week",
        "game_id",
        "gameday",
        "spread_line",
        "total_line",
        "div_game",
        "roof",
        "surface",
    ]
    home = schedule[
        common + ["home_team", "away_team", "home_rest", "away_rest"]
    ].copy()
    home = home.rename(
        columns={
            "gameday": "game_date",
            "home_team": "team",
            "away_team": "opponent",
            "home_rest": "team_rest",
            "away_rest": "opponent_rest",
            "spread_line": "source_spread_line",
        }
    )
    home["game_location"] = "HOME"
    home["is_home"] = 1

    away = schedule[
        common + ["away_team", "home_team", "away_rest", "home_rest"]
    ].copy()
    away = away.rename(
        columns={
            "gameday": "game_date",
            "away_team": "team",
            "home_team": "opponent",
            "away_rest": "team_rest",
            "home_rest": "opponent_rest",
            "spread_line": "source_spread_line",
        }
    )
    away["game_location"] = "AWAY"
    away["is_home"] = 0

    team_schedule = pd.concat([home, away], ignore_index=True)
    team_schedule["game_date"] = pd.to_datetime(
        team_schedule["game_date"], errors="raise"
    ).dt.normalize()
    ordered = [
        "season",
        "week",
        "team",
        "game_id",
        "game_date",
        "opponent",
        *CURRENT_CONTEXT_COLUMNS,
    ]
    return team_schedule[ordered]


def load_live_candidates(
    run_specification: dict[str, Any],
    configuration: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, str], dict[str, Any]]:
    """Load allowlisted current sources and create player-game candidates."""

    season = run_specification["season"]
    week = run_specification["week"]
    as_of = run_specification["as_of"]
    snapshot_directory = run_specification["snapshot_directory"]

    print(f"Downloading nflverse schedule for {season}...")
    schedules = require_source_columns(
        nfl.load_schedules(season),
        LIVE_SCHEDULE_COLUMNS,
        "schedules",
    )
    print(f"Downloading nflverse season roster for {season}...")
    rosters = require_source_columns(
        nfl.load_rosters(season), LIVE_ROSTER_COLUMNS, "rosters"
    )
    print(f"Downloading nflverse depth charts for {season}...")
    depth = require_source_columns(
        nfl.load_depth_charts(season),
        LIVE_DEPTH_COLUMNS,
        "depth_charts",
    )

    snapshot_paths = {
        "schedule": snapshot_directory / "schedule.parquet",
        "roster": snapshot_directory / "roster.parquet",
        "depth_chart": snapshot_directory / "depth_chart.parquet",
    }
    atomic_write_polars(schedules, snapshot_paths["schedule"])
    atomic_write_polars(rosters, snapshot_paths["roster"])
    atomic_write_polars(depth, snapshot_paths["depth_chart"])
    snapshot_hashes = {
        name: sha256_file(path) for name, path in snapshot_paths.items()
    }

    schedule_alias_rows = int(
        schedules.select(
            pl.col("away_team").is_in(list(TEAM_ALIASES)).sum()
            + pl.col("home_team").is_in(list(TEAM_ALIASES)).sum()
        ).item()
    )
    roster_alias_rows = int(
        rosters.select(
            pl.col("team").is_in(list(TEAM_ALIASES)).sum()
        ).item()
    )
    depth_alias_rows = int(
        depth.select(
            pl.col("team").is_in(list(TEAM_ALIASES)).sum()
        ).item()
    )
    normalized_schedules = normalize_team_columns(
        schedules, ["away_team", "home_team"]
    )
    normalized_rosters = normalize_team_columns(rosters, ["team"])
    normalized_depth = normalize_team_columns(depth, ["team"])

    schedule_week = normalized_schedules.filter(
        (pl.col("season") == season)
        & (pl.col("game_type") == "REG")
        & (pl.col("week") == week)
    )
    if schedule_week.is_empty() or schedule_week.height > 16:
        raise ValueError(
            "The target regular-season schedule has an invalid game count: "
            f"{schedule_week.height}."
        )
    if schedule_week["game_id"].n_unique() != schedule_week.height:
        raise ValueError("The target schedule contains duplicate games.")
    scheduled_teams = sorted(
        set(schedule_week["away_team"].to_list())
        | set(schedule_week["home_team"].to_list())
    )
    if len(scheduled_teams) != 2 * schedule_week.height:
        raise ValueError("A target-week team appears in multiple games.")

    game_dates = pd.to_datetime(
        schedule_week["gameday"].to_list(), errors="raise"
    )
    if as_of.date() >= game_dates.min().date():
        raise ValueError(
            "The live cutoff must be before every target game date."
        )

    supported_positions = list(
        configuration["future_features"]["supported_positions"]
    )
    statuses = list(
        configuration["future_features"]["candidate_roster_statuses"]
    )
    roster_candidates = normalized_rosters.filter(
        pl.col("team").is_in(scheduled_teams)
        & pl.col("position").is_in(supported_positions)
        & pl.col("status").is_in(statuses)
        & pl.col("gsis_id").is_not_null()
        & (pl.col("gsis_id").str.strip_chars() != "")
    )

    depth_with_time = normalized_depth.with_columns(
        pl.col("dt")
        .str.to_datetime(time_zone="UTC", strict=True)
        .alias("depth_timestamp")
    ).filter(pl.col("depth_timestamp") <= as_of)
    if depth_with_time.is_empty():
        raise ValueError("No depth-chart snapshot exists at the cutoff.")

    latest_by_team = (
        depth_with_time.filter(pl.col("team").is_in(scheduled_teams))
        .group_by("team")
        .agg(pl.col("depth_timestamp").max().alias("latest_timestamp"))
    )
    if latest_by_team.height != len(scheduled_teams):
        raise ValueError(
            "A latest depth-chart snapshot was not found for every "
            "target-week team."
        )

    latest_depth = (
        depth_with_time.join(latest_by_team, on="team", how="inner")
        .filter(
            (pl.col("depth_timestamp") == pl.col("latest_timestamp"))
            & pl.col("pos_abb").is_in(supported_positions)
            & pl.col("gsis_id").is_not_null()
        )
        .sort(["team", "gsis_id", "pos_rank", "pos_slot"])
        .unique(["team", "gsis_id"], keep="first")
    )

    candidate_pool = roster_candidates.join(
        latest_depth.select(
            [
                "team",
                "gsis_id",
                "pos_abb",
                "pos_rank",
                "pos_slot",
                "depth_timestamp",
            ]
        ),
        on=["team", "gsis_id"],
        how="left",
    )
    roster_rows = roster_candidates.height
    depth_matched_rows = candidate_pool.filter(
        pl.col("depth_timestamp").is_not_null()
    ).height
    depth_unmatched_rows = roster_rows - depth_matched_rows
    if configuration["future_features"]["require_depth_chart_match"]:
        candidate_pool = candidate_pool.filter(
            pl.col("depth_timestamp").is_not_null()
        )

    if candidate_pool["gsis_id"].n_unique() != candidate_pool.height:
        raise ValueError("Live candidate player IDs are not unique.")

    team_schedule = expand_team_schedule(schedule_week.to_pandas())
    roster_frame = candidate_pool.select(
        ["team", "position", "full_name", "football_name", "gsis_id"]
    ).to_pandas()
    candidates = roster_frame.merge(
        team_schedule,
        on="team",
        how="inner",
        validate="many_to_one",
    )
    if len(candidates) != len(roster_frame):
        raise ValueError("Candidate teams did not fully match the schedule.")

    candidate_teams = candidates["team"].nunique()
    candidate_games = candidates["game_id"].nunique()
    if (
        candidate_teams != len(scheduled_teams)
        or candidate_games != schedule_week.height
    ):
        raise ValueError(
            "Live candidate coverage differs from the target schedule: "
            f"teams={candidate_teams}/{len(scheduled_teams)}, "
            f"games={candidate_games}/{schedule_week.height}."
        )

    candidates = candidates.rename(
        columns={
            "gsis_id": "player_id",
            "full_name": "player_display_name",
        }
    )
    candidates["player_display_name"] = candidates[
        "player_display_name"
    ].fillna(candidates["football_name"])
    candidates = candidates.drop(columns=["football_name"])

    source_summary = {
        "schedule_source_rows": schedules.height,
        "target_schedule_games": schedule_week.height,
        "roster_source_rows": rosters.height,
        "eligible_roster_rows": roster_rows,
        "depth_source_rows": depth.height,
        "latest_depth_teams": latest_by_team.height,
        "depth_matched_candidate_rows": depth_matched_rows,
        "depth_unmatched_candidate_rows": depth_unmatched_rows,
        "candidate_rows": len(candidates),
        "candidate_teams": candidate_teams,
        "candidate_games": candidate_games,
        "schedule_team_alias_rows": schedule_alias_rows,
        "roster_team_alias_rows": roster_alias_rows,
        "depth_team_alias_rows": depth_alias_rows,
        "maximum_selected_depth_timestamp": latest_depth[
            "depth_timestamp"
        ].max(),
        "nflreadpy_version": package_version("nflreadpy"),
    }
    print(f"eligible_active_roster_rows={roster_rows:,}")
    print(f"depth_matched_candidate_rows={depth_matched_rows:,}")
    print(f"depth_unmatched_candidate_rows={depth_unmatched_rows:,}")
    print(f"live_candidate_rows={len(candidates):,}")
    print("live_source_contract=PASS")
    return candidates, snapshot_hashes, source_summary


def load_replay_candidates(
    run_specification: dict[str, Any],
    configuration: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load only safe candidate/context columns from the replay source."""

    reference_path = resolve_project_path(
        configuration["inputs"]["replay_reference_path"]
    )
    model_settings = load_toml(
        resolve_project_path(
            configuration["inputs"]["model_settings_path"]
        )
    )
    metadata = list(
        configuration["quality"]["required_metadata_columns"]
    )
    safe_columns = unique_in_order(metadata + CURRENT_CONTEXT_COLUMNS)
    source_schema = pq.ParquetFile(reference_path).schema_arrow.names
    target = str(model_settings["columns"]["target"])
    source_contains_target = target in source_schema
    missing = sorted(set(safe_columns) - set(source_schema))
    if missing:
        raise ValueError(f"Replay source is missing safe columns: {missing}")

    candidates = pd.read_parquet(
        reference_path,
        columns=safe_columns,
        filters=[
            ("season", "=", run_specification["season"]),
            ("week", "=", run_specification["week"]),
        ],
    )
    candidates["game_date"] = pd.to_datetime(
        candidates["game_date"]
    ).dt.normalize()
    if len(candidates) != run_specification["expected_rows"]:
        raise ValueError(
            f"Expected {run_specification['expected_rows']} replay rows "
            f"but found {len(candidates)}."
        )

    summary = {
        "reference_source_contains_target": source_contains_target,
        "target_week_outcome_loaded": False,
        "candidate_rows": len(candidates),
    }
    print(f"replay_candidate_rows={len(candidates):,}")
    print(f"reference_source_contains_target={source_contains_target}")
    print("target_week_outcome_loaded=False")
    print("replay_candidate_contract=PASS")
    return candidates, summary


def value_or_nan(value: Any) -> Any:
    """Return NaN for unavailable scalar values."""

    return np.nan if pd.isna(value) else value


def previous_value(history: pd.DataFrame, column: str) -> Any:
    """Return the last prior-game value or NaN."""

    if history.empty:
        return np.nan
    return value_or_nan(history.iloc[-1][column])


def window_mean(history: pd.DataFrame, column: str, rows: int) -> float:
    """Return a SQL-AVG-equivalent trailing mean."""

    if history.empty:
        return np.nan
    value = history.tail(rows)[column].mean()
    return float(value) if not pd.isna(value) else np.nan


def full_mean(history: pd.DataFrame, column: str) -> float:
    """Return a SQL-AVG-equivalent full-window mean."""

    if history.empty:
        return np.nan
    value = history[column].mean()
    return float(value) if not pd.isna(value) else np.nan


def mysql_integer_window_mean(
    history: pd.DataFrame, column: str, rows: int
) -> float:
    """Match MySQL AVG(integer), which returns four decimal places."""

    if history.empty:
        return np.nan
    values = history.tail(rows)[column].dropna()
    if values.empty:
        return np.nan
    average = Decimal(int(values.sum())) / Decimal(len(values))
    return float(
        average.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    )


def mysql_integer_full_mean(
    history: pd.DataFrame, column: str
) -> float:
    """Match MySQL AVG(integer) for a complete season window."""

    if history.empty:
        return np.nan
    values = history[column].dropna()
    if values.empty:
        return np.nan
    average = Decimal(int(values.sum())) / Decimal(len(values))
    return float(
        average.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    )


def window_std(history: pd.DataFrame, column: str, rows: int) -> float:
    """Return a SQL STDDEV_SAMP-equivalent trailing deviation."""

    if history.empty:
        return np.nan
    value = history.tail(rows)[column].std(ddof=1)
    return float(value) if not pd.isna(value) else np.nan


def full_std(history: pd.DataFrame, column: str) -> float:
    """Return a SQL STDDEV_SAMP-equivalent full-window deviation."""

    if history.empty:
        return np.nan
    value = history[column].std(ddof=1)
    return float(value) if not pd.isna(value) else np.nan


def protected_ratio(numerator: Any, denominator: Any) -> float:
    """Return a protected ratio, preserving zero as unavailable."""

    if pd.isna(numerator) or pd.isna(denominator) or denominator == 0:
        return np.nan
    return float(numerator) / float(denominator)


def assign_player_summaries(
    output: dict[str, Any],
    history: pd.DataFrame,
    current_season_history: pd.DataFrame,
) -> None:
    """Populate all frozen lagged player measures."""

    output["fantasy_points_ppr_prev_game"] = previous_value(
        history, "target_fantasy_points_ppr"
    )
    output["fantasy_points_ppr_avg_last_3_games"] = window_mean(
        history, "target_fantasy_points_ppr", 3
    )
    output["fantasy_points_ppr_avg_last_5_games"] = window_mean(
        history, "target_fantasy_points_ppr", 5
    )
    output["fantasy_points_ppr_stddev_last_5_games"] = window_std(
        history, "target_fantasy_points_ppr", 5
    )
    last_five_points = history.tail(5)["target_fantasy_points_ppr"]
    output["fantasy_points_ppr_min_last_5_games"] = (
        float(last_five_points.min()) if not last_five_points.empty else np.nan
    )
    output["fantasy_points_ppr_max_last_5_games"] = (
        float(last_five_points.max()) if not last_five_points.empty else np.nan
    )
    output["fantasy_points_ppr_season_to_date"] = full_mean(
        current_season_history, "target_fantasy_points_ppr"
    )
    output["fantasy_points_ppr_stddev_season_to_date"] = full_std(
        current_season_history, "target_fantasy_points_ppr"
    )

    specifications = [
        (
            "attempts",
            "attempts_prev_game",
            "attempts_avg_last_3_games",
            "attempts_avg_last_5_games",
            "attempts_season_to_date",
        ),
        (
            "carries",
            "carries_prev_game",
            "carries_avg_last_3_games",
            "carries_avg_last_5_games",
            "carries_season_to_date",
        ),
        (
            "targets",
            "targets_prev_game",
            "targets_avg_last_3_games",
            "targets_avg_last_5_games",
            "targets_season_to_date",
        ),
        (
            "position_adjusted_opportunities",
            "opportunities_prev_game",
            "opportunities_avg_last_3_games",
            "opportunities_avg_last_5_games",
            "opportunities_season_to_date",
        ),
    ]
    for source, previous, average_three, average_five, season_average in specifications:
        output[previous] = previous_value(history, source)
        output[average_three] = mysql_integer_window_mean(
            history, source, 3
        )
        output[average_five] = mysql_integer_window_mean(
            history, source, 5
        )
        output[season_average] = mysql_integer_full_mean(
            current_season_history, source
        )

    shorter_specifications = [
        (
            "receptions",
            "receptions_prev_game",
            "receptions_avg_last_3_games",
            "receptions_avg_last_5_games",
        ),
        (
            "touches",
            "touches_prev_game",
            "touches_avg_last_3_games",
            "touches_avg_last_5_games",
        ),
        (
            "target_share",
            "target_share_prev_game",
            "target_share_avg_last_3_games",
            "target_share_avg_last_5_games",
        ),
        (
            "air_yards_share",
            "air_yards_share_prev_game",
            "air_yards_share_avg_last_3_games",
            "air_yards_share_avg_last_5_games",
        ),
        (
            "wopr",
            "wopr_prev_game",
            "wopr_avg_last_3_games",
            "wopr_avg_last_5_games",
        ),
        (
            "offense_snaps",
            "offense_snaps_prev_game",
            "offense_snaps_avg_last_3_games",
            "offense_snaps_avg_last_5_games",
        ),
        (
            "offense_pct",
            "offense_pct_prev_game",
            "offense_pct_avg_last_3_games",
            "offense_pct_avg_last_5_games",
        ),
    ]
    for source, previous, average_three, average_five in shorter_specifications:
        output[previous] = previous_value(history, source)
        if source in {"receptions", "touches"}:
            output[average_three] = mysql_integer_window_mean(
                history, source, 3
            )
            output[average_five] = mysql_integer_window_mean(
                history, source, 5
            )
        else:
            output[average_three] = window_mean(history, source, 3)
            output[average_five] = window_mean(history, source, 5)

    three_game_specifications = [
        (
            "passing_yards",
            "passing_yards_prev_game",
            "passing_yards_avg_last_3_games",
        ),
        (
            "rushing_yards",
            "rushing_yards_prev_game",
            "rushing_yards_avg_last_3_games",
        ),
        (
            "receiving_yards",
            "receiving_yards_prev_game",
            "receiving_yards_avg_last_3_games",
        ),
        (
            "yards_from_scrimmage",
            "yards_from_scrimmage_prev_game",
            "yards_from_scrimmage_avg_last_3_games",
        ),
        (
            "total_offensive_tds",
            "total_offensive_tds_prev_game",
            "total_offensive_tds_avg_last_3_games",
        ),
    ]
    for source, previous, average_three in three_game_specifications:
        output[previous] = previous_value(history, source)
        output[average_three] = mysql_integer_window_mean(
            history, source, 3
        )

    output["target_share_season_to_date"] = full_mean(
        current_season_history, "target_share"
    )


def assign_efficiency_features(
    output: dict[str, Any], history: pd.DataFrame
) -> None:
    """Populate ratios from separately aggregated prior-three totals."""

    last_three = history.tail(3)

    def total(column: str) -> float:
        value = last_three[column].sum(min_count=1)
        return float(value) if not pd.isna(value) else np.nan

    attempts = total("attempts")
    carries = total("carries")
    targets = total("targets")
    receptions = total("receptions")
    opportunities = total("position_adjusted_opportunities")

    output["completion_pct_avg_last_3_games"] = protected_ratio(
        total("completions"), attempts
    )
    output[
        "passing_yards_per_attempt_avg_last_3_games"
    ] = protected_ratio(total("passing_yards"), attempts)
    output[
        "rushing_yards_per_carry_avg_last_3_games"
    ] = protected_ratio(total("rushing_yards"), carries)
    output[
        "receiving_yards_per_target_avg_last_3_games"
    ] = protected_ratio(total("receiving_yards"), targets)
    output[
        "receiving_yards_per_reception_avg_last_3_games"
    ] = protected_ratio(total("receiving_yards"), receptions)
    output[
        "fantasy_points_per_opportunity_avg_last_3_games"
    ] = protected_ratio(total("target_fantasy_points_ppr"), opportunities)
    output[
        "total_yards_per_opportunity_avg_last_3_games"
    ] = protected_ratio(total("total_offensive_yards"), opportunities)


def assign_opponent_features(
    output: dict[str, Any],
    history: pd.DataFrame,
    current_season_history: pd.DataFrame,
) -> None:
    """Populate frozen opponent-by-position prior-game features."""

    output["opponent_prior_position_games"] = len(history)
    output["opponent_prior_position_games_current_season"] = len(
        current_season_history
    )
    output["has_opponent_history"] = int(len(history) >= 1)
    output["opp_ppr_allowed_prev_game"] = previous_value(
        history, "fantasy_points_ppr_allowed"
    )
    output["opp_ppr_allowed_avg_last_3_games"] = window_mean(
        history, "fantasy_points_ppr_allowed", 3
    )
    output["opp_ppr_allowed_avg_last_5_games"] = window_mean(
        history, "fantasy_points_ppr_allowed", 5
    )
    output["opp_ppr_allowed_season_to_date"] = full_mean(
        current_season_history, "fantasy_points_ppr_allowed"
    )
    output["opp_opportunities_allowed_prev_game"] = previous_value(
        history, "position_adjusted_opportunities_allowed"
    )
    output[
        "opp_opportunities_allowed_avg_last_3_games"
    ] = window_mean(history, "position_adjusted_opportunities_allowed", 3)
    output[
        "opp_opportunities_allowed_season_to_date"
    ] = full_mean(
        current_season_history,
        "position_adjusted_opportunities_allowed",
    )
    output[
        "opp_passing_yards_allowed_season_to_date"
    ] = full_mean(current_season_history, "passing_yards_allowed")
    output[
        "opp_rushing_yards_allowed_season_to_date"
    ] = full_mean(current_season_history, "rushing_yards_allowed")
    output[
        "opp_receiving_yards_allowed_season_to_date"
    ] = full_mean(current_season_history, "receiving_yards_allowed")
    output[
        "opp_offensive_tds_allowed_season_to_date"
    ] = full_mean(current_season_history, "total_offensive_tds_allowed")


def build_future_features(
    candidates: pd.DataFrame,
    player_history: pd.DataFrame,
    opponent_history: pd.DataFrame,
    output_columns: list[str],
) -> pd.DataFrame:
    """Create the target-free future feature frame."""

    candidates = candidates.copy()
    candidates["game_date"] = pd.to_datetime(
        candidates["game_date"]
    ).dt.normalize()
    player_groups = {
        str(player_id): group.reset_index(drop=True)
        for player_id, group in player_history.groupby(
            "player_id", sort=False
        )
    }
    opponent_groups = {
        (str(team), str(position)): group.reset_index(drop=True)
        for (team, position), group in opponent_history.groupby(
            ["defensive_team", "position"], sort=False
        )
    }

    rows: list[dict[str, Any]] = []
    for candidate in candidates.to_dict(orient="records"):
        output = dict(candidate)
        season = int(candidate["season"])
        player = player_groups.get(
            str(candidate["player_id"]),
            player_history.iloc[0:0],
        )
        opponent = opponent_groups.get(
            (str(candidate["opponent"]), str(candidate["position"])),
            opponent_history.iloc[0:0],
        )
        player_season = player[player["season"] == season]
        opponent_season = opponent[opponent["season"] == season]

        output["prior_games_count"] = len(player)
        output["prior_games_current_season"] = len(player_season)
        previous = None if player.empty else player.iloc[-1]
        previous_date = (
            pd.NaT if previous is None else previous["game_date"]
        )
        output["days_since_previous_game"] = (
            np.nan
            if pd.isna(previous_date)
            else int((candidate["game_date"] - previous_date).days)
        )
        output["is_first_observed_game"] = int(len(player) == 0)
        output["is_first_observed_game_of_season"] = int(
            len(player_season) == 0
        )
        output["has_previous_game"] = int(len(player) >= 1)
        output["has_3_prior_games"] = int(len(player) >= 3)
        output["has_5_prior_games"] = int(len(player) >= 5)
        output["team_changed_since_previous_game"] = int(
            previous is not None
            and str(previous["team"]) != str(candidate["team"])
        )
        output["has_previous_snap_record"] = int(
            previous is not None and int(previous["has_snap_record"]) == 1
        )
        output["snap_records_last_3_games"] = int(
            player.tail(3)["has_snap_record"].sum()
        )
        output["snap_records_last_5_games"] = int(
            player.tail(5)["has_snap_record"].sum()
        )

        assign_player_summaries(output, player, player_season)
        assign_efficiency_features(output, player)
        assign_opponent_features(output, opponent, opponent_season)
        rows.append(output)

    dataframe = pd.DataFrame(rows)
    missing = sorted(set(output_columns) - set(dataframe.columns))
    if missing:
        raise ValueError(f"Feature builder did not create columns: {missing}")
    return dataframe[output_columns]


def validate_feature_frame(
    dataframe: pd.DataFrame,
    run_specification: dict[str, Any],
    configuration: dict[str, Any],
    metadata: list[str],
    categorical: list[str],
    numeric: list[str],
) -> dict[str, Any]:
    """Validate the completed target-free frame."""

    quality = configuration["quality"]
    key = list(quality["key_columns"])
    target = load_toml(
        resolve_project_path(
            configuration["inputs"]["model_settings_path"]
        )
    )["columns"]["target"]

    duplicate_keys = int(dataframe.duplicated(key).sum())
    unavailable_keys = int(dataframe[key].isna().sum().sum())
    for column in ["player_id", "game_id", "position", "team", "opponent"]:
        unavailable_keys += int(
            dataframe[column].astype("string").str.strip().eq("").sum()
        )
    infinite_numeric = int(
        np.isinf(
            dataframe[numeric]
            .apply(pd.to_numeric, errors="coerce")
            .to_numpy(dtype=float)
        ).sum()
    )
    unsupported_positions = sorted(
        set(dataframe["position"])
        - set(configuration["future_features"]["supported_positions"])
    )
    incorrect_period_rows = int(
        (
            (dataframe["season"] != run_specification["season"])
            | (dataframe["week"] != run_specification["week"])
        ).sum()
    )
    missing_game_context = int(
        dataframe[
            [
                "game_id",
                "game_date",
                "player_display_name",
                "position",
                "team",
                "opponent",
                "game_location",
                "is_home",
            ]
        ]
        .isna()
        .sum()
        .sum()
    )
    if target in dataframe.columns:
        raise ValueError("The target column is present in future features.")
    if list(dataframe.columns) != unique_in_order(
        metadata + categorical + numeric
    ):
        raise ValueError("Future feature columns or order are incorrect.")
    if duplicate_keys or unavailable_keys:
        raise ValueError("Future features failed key quality controls.")
    if infinite_numeric:
        raise ValueError("Future features contain infinite numeric values.")
    if unsupported_positions:
        raise ValueError(
            f"Unsupported positions found: {unsupported_positions}"
        )
    if incorrect_period_rows or missing_game_context:
        raise ValueError("Future features contain invalid target context.")
    if not len(dataframe):
        raise ValueError("Future feature output is empty.")

    summary = {
        "output_rows": len(dataframe),
        "output_columns": len(dataframe.columns),
        "predictor_count": len(categorical) + len(numeric),
        "duplicate_keys": duplicate_keys,
        "unavailable_keys": unavailable_keys,
        "infinite_numeric_values": infinite_numeric,
        "missing_numeric_values": int(dataframe[numeric].isna().sum().sum()),
        "position_counts": dataframe["position"]
        .value_counts()
        .sort_index()
        .to_dict(),
        "players_without_prior_games": int(
            (dataframe["prior_games_count"] == 0).sum()
        ),
        "players_without_current_season_history": int(
            (dataframe["prior_games_current_season"] == 0).sum()
        ),
    }
    print(f"future_feature_rows={len(dataframe):,}")
    print(f"future_feature_columns={len(dataframe.columns):,}")
    print(f"predictor_count={summary['predictor_count']}")
    print("future_feature_duplicate_keys=0")
    print("future_feature_unavailable_keys=0")
    print("future_feature_infinite_values=0")
    print("target_week_outcome_loaded=False")
    print("future_feature_contract=PASS")
    return summary


def build_replay_verification(
    features: pd.DataFrame,
    run_specification: dict[str, Any],
    configuration: dict[str, Any],
    metadata: list[str],
    categorical: list[str],
    numeric: list[str],
) -> pd.DataFrame:
    """Compare every replay column with the frozen historical reference."""

    reference_path = resolve_project_path(
        configuration["inputs"]["replay_reference_path"]
    )
    compare_columns = unique_in_order(metadata + categorical + numeric)
    reference = pd.read_parquet(
        reference_path,
        columns=compare_columns,
        filters=[
            ("season", "=", run_specification["season"]),
            ("week", "=", run_specification["week"]),
        ],
    )
    key = list(configuration["quality"]["key_columns"])
    tolerance = float(
        configuration["quality"]["numeric_comparison_tolerance"]
    )
    merged = features.merge(
        reference,
        on=key,
        how="outer",
        suffixes=("_built", "_reference"),
        indicator=True,
        validate="one_to_one",
    )
    if not merged["_merge"].eq("both").all():
        raise ValueError("Replay feature keys do not fully reconcile.")

    row_mismatch = np.zeros(len(merged), dtype=bool)
    verification_rows: list[dict[str, Any]] = []
    for column in compare_columns:
        if column in key:
            mismatch = np.zeros(len(merged), dtype=bool)
            maximum_difference = 0.0
            data_type = "key"
        else:
            built = merged[f"{column}_built"]
            expected = merged[f"{column}_reference"]
            if column == "game_date":
                built = pd.to_datetime(built).dt.normalize()
                expected = pd.to_datetime(expected).dt.normalize()
                mismatch = ~(
                    (built.isna() & expected.isna()) | built.eq(expected)
                ).to_numpy()
                maximum_difference = 0.0
                data_type = "date"
            elif column in numeric:
                built_numeric = pd.to_numeric(built, errors="coerce")
                expected_numeric = pd.to_numeric(expected, errors="coerce")
                both_missing = (
                    built_numeric.isna() & expected_numeric.isna()
                ).to_numpy()
                difference = (built_numeric - expected_numeric).abs()
                close = np.isclose(
                    built_numeric.to_numpy(dtype=float),
                    expected_numeric.to_numpy(dtype=float),
                    rtol=0.0,
                    atol=tolerance,
                    equal_nan=True,
                )
                mismatch = ~(both_missing | close)
                finite_difference = difference[np.isfinite(difference)]
                maximum_difference = (
                    float(finite_difference.max())
                    if len(finite_difference)
                    else 0.0
                )
                data_type = "numeric"
            else:
                built_text = built.astype("string").fillna("<NULL>")
                expected_text = expected.astype("string").fillna("<NULL>")
                mismatch = built_text.ne(expected_text).to_numpy()
                maximum_difference = 0.0
                data_type = "categorical"

        mismatch_rows = int(mismatch.sum())
        row_mismatch |= mismatch
        verification_rows.append(
            {
                "scope": (
                    "predictor" if column in categorical + numeric else "metadata"
                ),
                "column_name": column,
                "data_type": data_type,
                "compared_rows": len(merged),
                "mismatch_rows": mismatch_rows,
                "maximum_absolute_difference": maximum_difference,
                "verification_status": (
                    "PASS" if mismatch_rows == 0 else "FAIL"
                ),
            }
        )

    maximum_numeric_difference = max(
        row["maximum_absolute_difference"]
        for row in verification_rows
    )
    verification_rows.append(
        {
            "scope": "overall",
            "column_name": "ALL",
            "data_type": "mixed",
            "compared_rows": len(merged),
            "mismatch_rows": int(row_mismatch.sum()),
            "maximum_absolute_difference": maximum_numeric_difference,
            "verification_status": (
                "PASS" if not row_mismatch.any() else "FAIL"
            ),
        }
    )
    verification = pd.DataFrame(verification_rows)
    if set(verification["verification_status"]) != {"PASS"}:
        failed = verification.loc[
            verification["verification_status"] == "FAIL",
            ["column_name", "mismatch_rows"],
        ]
        raise ValueError(
            "Replay feature verification failed:\n"
            + failed.to_string(index=False)
        )

    print(f"replay_verified_columns={len(compare_columns):,}")
    print("replay_mismatch_rows=0")
    print(
        "replay_maximum_absolute_difference="
        f"{maximum_numeric_difference:.16g}"
    )
    print("replay_feature_reconciliation=PASS")
    return verification


def json_value(value: Any) -> str:
    """Serialize one manifest value consistently."""

    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, default=str)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def build_manifest(
    run_timestamp_utc: str,
    current_commit: str,
    configuration_path: Path,
    configuration: dict[str, Any],
    run_specification: dict[str, Any],
    lineage_hashes: dict[str, str],
    source_hashes: dict[str, str],
    source_summary: dict[str, Any],
    history_summary: dict[str, Any],
    feature_summary: dict[str, Any],
    output_hashes: dict[str, str],
) -> pd.DataFrame:
    """Build compact run lineage and quality evidence."""

    rows = [
        ("run_timestamp_utc", run_timestamp_utc),
        ("run_mode", run_specification["mode"]),
        ("future_feature_commit", current_commit),
        (
            "feature_pipeline_commit",
            configuration["lineage"]["feature_pipeline_commit"],
        ),
        (
            "future_feature_configuration_sha256",
            sha256_file(configuration_path),
        ),
        ("model_settings_sha256", lineage_hashes["model_settings"]),
        ("feature_sql_sha256", lineage_hashes["feature_sql"]),
        (
            "future_feature_version",
            configuration["future_features"]["version"],
        ),
        (
            "model_feature_version",
            configuration["future_features"]["model_feature_version"],
        ),
        ("target_season", run_specification["season"]),
        ("target_week", run_specification["week"]),
        (
            "as_of_utc",
            (
                run_specification["as_of"].isoformat()
                if run_specification["as_of"] is not None
                else "not_applicable"
            ),
        ),
        (
            "history_cutoff_rule",
            configuration["future_features"]["history_cutoff_rule"],
        ),
        ("same_week_history_rows_loaded", 0),
        ("target_week_outcome_loaded", False),
        ("prior_completed_outcomes_used_as_history", True),
        ("database_name", history_summary["database_name"]),
        (
            "player_history_rows",
            history_summary["player_history_rows"],
        ),
        (
            "opponent_history_rows",
            history_summary["opponent_history_rows"],
        ),
        (
            "maximum_player_history_date",
            history_summary["maximum_player_history_date"],
        ),
        (
            "maximum_opponent_history_date",
            history_summary["maximum_opponent_history_date"],
        ),
        ("source_sha256", source_hashes),
        ("source_summary", source_summary),
        ("output_rows", feature_summary["output_rows"]),
        ("output_columns", feature_summary["output_columns"]),
        ("predictor_count", feature_summary["predictor_count"]),
        ("position_counts", feature_summary["position_counts"]),
        (
            "players_without_prior_games",
            feature_summary["players_without_prior_games"],
        ),
        (
            "players_without_current_season_history",
            feature_summary["players_without_current_season_history"],
        ),
        (
            "missing_numeric_values",
            feature_summary["missing_numeric_values"],
        ),
        ("duplicate_keys", feature_summary["duplicate_keys"]),
        ("unavailable_keys", feature_summary["unavailable_keys"]),
        (
            "infinite_numeric_values",
            feature_summary["infinite_numeric_values"],
        ),
        ("features_path", display_path(run_specification["features"])),
        ("features_sha256", output_hashes["features"]),
        ("sample_path", display_path(run_specification["sample"])),
        ("sample_sha256", output_hashes["sample"]),
    ]
    if run_specification["verification"] is not None:
        rows.extend(
            [
                (
                    "verification_path",
                    display_path(run_specification["verification"]),
                ),
                ("verification_sha256", output_hashes["verification"]),
                ("replay_feature_mismatch_rows", 0),
            ]
        )
    return pd.DataFrame(
        [(key, json_value(value)) for key, value in rows],
        columns=["manifest_key", "manifest_value"],
    )


def write_outputs(
    features: pd.DataFrame,
    verification: pd.DataFrame | None,
    run_specification: dict[str, Any],
    configuration_path: Path,
    configuration: dict[str, Any],
    current_commit: str,
    lineage_hashes: dict[str, str],
    source_hashes: dict[str, str],
    source_summary: dict[str, Any],
    history_summary: dict[str, Any],
    feature_summary: dict[str, Any],
) -> pd.DataFrame:
    """Write protected future-feature outputs and run evidence."""

    atomic_write_parquet(features, run_specification["features"])
    sample = (
        features.sort_values(
            ["season", "week", "position", "player_id"], kind="stable"
        )
        .head(run_specification["sample_rows"])
        .reset_index(drop=True)
    )
    atomic_write_csv(sample, run_specification["sample"])
    output_hashes = {
        "features": sha256_file(run_specification["features"]),
        "sample": sha256_file(run_specification["sample"]),
    }
    if verification is not None:
        atomic_write_csv(verification, run_specification["verification"])
        output_hashes["verification"] = sha256_file(
            run_specification["verification"]
        )

    manifest = build_manifest(
        datetime.now(timezone.utc).isoformat(),
        current_commit,
        configuration_path,
        configuration,
        run_specification,
        lineage_hashes,
        source_hashes,
        source_summary,
        history_summary,
        feature_summary,
        output_hashes,
    )
    atomic_write_csv(manifest, run_specification["manifest"])

    print(f"Wrote {display_path(run_specification['features'])}")
    print(f"Wrote {display_path(run_specification['sample'])}")
    if run_specification["verification"] is not None:
        print(f"Wrote {display_path(run_specification['verification'])}")
    print(f"Wrote {display_path(run_specification['manifest'])}")
    return manifest


def reopen_and_validate_outputs(
    features: pd.DataFrame,
    verification: pd.DataFrame | None,
    manifest: pd.DataFrame,
    run_specification: dict[str, Any],
    configuration: dict[str, Any],
) -> None:
    """Reopen every written artifact and reconcile its controls."""

    written = pd.read_parquet(run_specification["features"])
    written_sample = pd.read_csv(run_specification["sample"])
    written_manifest = pd.read_csv(run_specification["manifest"], dtype=str)
    if len(written) != len(features) or list(written.columns) != list(
        features.columns
    ):
        raise ValueError("Reopened feature output does not match memory.")
    if len(written_sample) != min(
        len(features), run_specification["sample_rows"]
    ):
        raise ValueError("Reopened sample row count is incorrect.")
    if written_manifest["manifest_key"].duplicated().any():
        raise ValueError("Reopened manifest contains duplicate keys.")
    manifest_values = written_manifest.set_index("manifest_key")[
        "manifest_value"
    ]
    if manifest_values["features_sha256"] != sha256_file(
        run_specification["features"]
    ):
        raise ValueError("Reopened feature hash does not reconcile.")
    if manifest_values["target_week_outcome_loaded"] != "false":
        raise ValueError("Manifest does not confirm target exclusion.")
    if manifest_values["same_week_history_rows_loaded"] != "0":
        raise ValueError("Manifest does not confirm the history cutoff.")
    if set(written_manifest["manifest_key"]) != set(
        manifest["manifest_key"]
    ):
        raise ValueError("Reopened manifest keys are incorrect.")

    if verification is not None:
        written_verification = pd.read_csv(
            run_specification["verification"]
        )
        if set(written_verification["verification_status"]) != {"PASS"}:
            raise ValueError("Reopened replay verification failed.")
        if int(written_verification["mismatch_rows"].sum()) != 0:
            raise ValueError("Reopened replay verification has mismatches.")

    print(f"reopened_feature_rows={len(written):,}")
    print(f"reopened_sample_rows={len(written_sample):,}")
    print(f"reopened_manifest_rows={len(written_manifest):,}")
    print("written_output_validation=PASS")


def main() -> None:
    """Run controlled replay or live future-feature preparation."""

    arguments = parse_arguments()
    configuration_path = Path(arguments.config).resolve()
    configuration = load_toml(configuration_path)
    validate_configuration(configuration, arguments.confirm_build)
    run_specification = build_run_specification(arguments, configuration)
    model_settings = load_toml(
        resolve_project_path(
            configuration["inputs"]["model_settings_path"]
        )
    )
    metadata, categorical, numeric, output_columns = configured_contract(
        model_settings, configuration
    )

    print_section("NFL FANTASY FUTURE-WEEK FEATURE PREPARATION")
    print(f"Configuration: {configuration_path}")
    print(f"Run mode: {run_specification['mode']}")
    print(f"Target season: {run_specification['season']}")
    print(f"Target week: {run_specification['week']}")
    print(f"Output: {display_path(run_specification['features'])}")
    print("History cutoff: strict prior week")
    print("Target-week outcome loading permitted: False")

    print_section("EXECUTION AND LINEAGE GUARDS")
    validate_output_paths(run_specification)
    current_commit = validate_git_state(
        configuration, arguments.orchestrated_revision
    )
    lineage_hashes = validate_lineage_hashes(
        configuration, run_specification["mode"]
    )

    print_section("TARGET-WEEK CANDIDATE PREPARATION")
    if run_specification["mode"] == "live":
        candidates, source_hashes, source_summary = load_live_candidates(
            run_specification, configuration
        )
    else:
        candidates, source_summary = load_replay_candidates(
            run_specification, configuration
        )
        source_hashes = {
            "replay_reference": lineage_hashes["replay_reference"]
        }

    print_section("STRICT PRIOR-WEEK HISTORY LOAD")
    if arguments.player_history:
        player_history_path = resolve_project_path(arguments.player_history)
        opponent_history_path = resolve_project_path(
            arguments.opponent_history
        )
        player_history, opponent_history, history_summary = (
            load_prior_history_files(
                player_history_path,
                opponent_history_path,
                configuration,
                run_specification["season"],
                run_specification["week"],
            )
        )
        source_hashes["player_history"] = sha256_file(
            player_history_path
        )
        source_hashes["opponent_history"] = sha256_file(
            opponent_history_path
        )
    else:
        engine = build_database_engine()
        try:
            player_history, opponent_history, history_summary = (
                load_prior_history(
                    engine,
                    configuration,
                    run_specification["season"],
                    run_specification["week"],
                )
            )
        finally:
            engine.dispose()

    earliest_target_date = pd.to_datetime(candidates["game_date"]).min()
    if history_summary["maximum_player_history_date"] >= earliest_target_date:
        raise ValueError("Player history is not strictly before the target.")
    if history_summary["maximum_opponent_history_date"] >= earliest_target_date:
        raise ValueError("Opponent history is not strictly before the target.")

    print_section("FROZEN FEATURE CONSTRUCTION")
    features = build_future_features(
        candidates,
        player_history,
        opponent_history,
        output_columns,
    )
    feature_summary = validate_feature_frame(
        features,
        run_specification,
        configuration,
        metadata,
        categorical,
        numeric,
    )

    verification = None
    if run_specification["mode"] == "replay":
        print_section("HISTORICAL REPLAY RECONCILIATION")
        verification = build_replay_verification(
            features,
            run_specification,
            configuration,
            metadata,
            categorical,
            numeric,
        )

    print_section("WRITING PROTECTED OUTPUTS")
    manifest = write_outputs(
        features,
        verification,
        run_specification,
        configuration_path,
        configuration,
        current_commit,
        lineage_hashes,
        source_hashes,
        source_summary,
        history_summary,
        feature_summary,
    )

    print_section("REOPENING WRITTEN OUTPUTS")
    reopen_and_validate_outputs(
        features,
        verification,
        manifest,
        run_specification,
        configuration,
    )

    print_section("FUTURE-WEEK FEATURE PREPARATION COMPLETE")
    print("strict_prior_week_history=PASS")
    print("target_week_outcome_excluded=PASS")
    print("feature_contract=PASS")
    if verification is not None:
        print("historical_replay_reconciliation=PASS")
    else:
        print("historical_replay_reconciliation=NOT_APPLICABLE")
    print("future_feature_status=PASS")


if __name__ == "__main__":
    main()
