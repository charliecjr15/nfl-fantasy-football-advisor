"""Build portable strict-prior-week history for automated scoring runs."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import tomllib
from datetime import datetime, timezone
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

import nflreadpy as nfl
import pandas as pd
import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIRECTORY = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))

import extract_history as historical  # noqa: E402


PLAYER_HISTORY_COLUMNS = [
    "season",
    "week",
    "game_id",
    "game_date",
    "player_id",
    "position",
    "team",
    "opponent",
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

SOURCE_DATASETS = (
    "weekly_player_stats",
    "schedules",
    "weekly_rosters",
    "snap_counts",
)


def parse_arguments() -> argparse.Namespace:
    """Parse the portable history refresh options."""

    parser = argparse.ArgumentParser(
        description=(
            "Refresh completed-game history without requiring a live MySQL "
            "database."
        )
    )
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument(
        "--through-week",
        type=int,
        required=True,
        help="Last completed week to include for --season; use 0 for Week 1.",
    )
    parser.add_argument(
        "--start-season",
        type=int,
        default=2018,
    )
    parser.add_argument(
        "--source-mode",
        choices=["download", "existing"],
        default="download",
        help=(
            "download reads nflverse through nflreadpy; existing reuses the "
            "validated data/processed/historical Parquet partitions."
        ),
    )
    parser.add_argument(
        "--player-output",
        default=(
            "data/processed/runtime_history/player_game_history.parquet"
        ),
    )
    parser.add_argument(
        "--opponent-output",
        default=(
            "data/processed/runtime_history/"
            "opponent_position_week_history.parquet"
        ),
    )
    parser.add_argument(
        "--manifest-output",
        help=(
            "Optional key-value CSV path. Defaults to a target-specific "
            "results/tables/history_refresh manifest."
        ),
    )
    arguments = parser.parse_args()
    if arguments.start_season < 1999:
        parser.error("--start-season is unexpectedly early.")
    if arguments.season < arguments.start_season:
        parser.error("--season cannot precede --start-season.")
    if arguments.through_week < 0 or arguments.through_week > 18:
        parser.error("--through-week must be between 0 and 18.")
    return arguments


def resolve_project_path(value: str) -> Path:
    """Resolve one path relative to the repository."""

    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def display_path(path: Path) -> str:
    """Return a repository-relative path where possible."""

    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path) -> str:
    """Hash one file in bounded blocks."""

    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for block in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_parquet(dataframe: pd.DataFrame, path: Path) -> None:
    """Write Parquet without exposing a partial file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.tmp{path.suffix}")
    dataframe.to_parquet(
        temporary, index=False, compression="snappy", engine="pyarrow"
    )
    os.replace(temporary, path)


def atomic_write_csv(dataframe: pd.DataFrame, path: Path) -> None:
    """Write CSV without exposing a partial file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.tmp{path.suffix}")
    dataframe.to_csv(temporary, index=False, lineterminator="\n")
    os.replace(temporary, path)


def runtime_settings(end_season: int) -> dict[str, Any]:
    """Extend extraction settings for live history without changing training."""

    with (PROJECT_ROOT / "config" / "data_settings.toml").open(
        "rb"
    ) as file_handle:
        settings = copy.deepcopy(tomllib.load(file_handle))

    configured_start = int(settings["data"]["start_season"])
    settings["data"]["end_season"] = end_season
    settings["data"]["seasons"] = list(
        range(configured_start, end_season + 1)
    )
    known = (
        set(settings["split"]["training_seasons"])
        | set(settings["split"]["validation_seasons"])
        | set(settings["split"]["test_seasons"])
    )
    new_seasons = sorted(set(settings["data"]["seasons"]) - known)
    settings["split"]["test_seasons"] = sorted(
        set(settings["split"]["test_seasons"]) | set(new_seasons)
    )
    return settings


def existing_partition(dataset: str, season: int) -> pl.DataFrame:
    """Load one already-prepared historical partition."""

    path = (
        PROJECT_ROOT
        / "data"
        / "processed"
        / "historical"
        / dataset
        / f"{dataset}_{season}.parquet"
    )
    if not path.exists():
        raise FileNotFoundError(
            f"Existing prepared source is missing: {display_path(path)}"
        )
    return pl.read_parquet(path)


def download_prepared_sources(
    season: int,
    settings: dict[str, Any],
    scoring: dict[str, Any],
    player_identity: pl.DataFrame,
) -> dict[str, pl.DataFrame]:
    """Download and normalize the four sources needed for history."""

    raw_stats = nfl.load_player_stats(season, summary_level="week")
    raw_schedule = nfl.load_schedules(season)
    raw_rosters = nfl.load_rosters_weekly(season)
    raw_snaps = nfl.load_snap_counts(season)

    stats, _ = historical.prepare_player_stats(
        raw_stats, season, settings, scoring
    )
    schedules, _ = historical.prepare_schedules(
        raw_schedule, season, settings
    )
    rosters, _ = historical.prepare_rosters(
        raw_rosters, season, settings, player_identity
    )
    snaps, _ = historical.prepare_snap_counts(
        raw_snaps, season, settings
    )
    return {
        "weekly_player_stats": stats,
        "schedules": schedules,
        "weekly_rosters": rosters,
        "snap_counts": snaps,
    }


def write_source_snapshot(
    dataframe: pl.DataFrame, dataset: str, season: int
) -> Path:
    """Persist the exact prepared source used by a download refresh."""

    path = (
        PROJECT_ROOT
        / "data"
        / "processed"
        / "runtime_history"
        / "source_snapshots"
        / str(season)
        / f"{dataset}.parquet"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.tmp{path.suffix}")
    dataframe.write_parquet(temporary, compression="snappy")
    os.replace(temporary, path)
    return path


def load_sources(
    start_season: int,
    target_season: int,
    through_week: int,
    source_mode: str,
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """Load prepared sources for all completed history seasons."""

    final_source_season = target_season if through_week else target_season - 1
    seasons = list(range(start_season, final_source_season + 1))
    if not seasons:
        raise ValueError("No history seasons were selected.")

    settings = runtime_settings(max(seasons))
    scoring = historical.load_league_scoring()
    player_identity = None
    if source_mode == "download":
        historical.configure_cache()
        player_identity = historical.prepare_player_identity(
            nfl.load_players()
        )

    collected: dict[str, list[pd.DataFrame]] = {
        dataset: [] for dataset in SOURCE_DATASETS
    }
    hashes: dict[str, str] = {}

    for season in seasons:
        print(f"Loading portable history sources for {season}...")
        if source_mode == "existing":
            prepared = {
                dataset: existing_partition(dataset, season)
                for dataset in SOURCE_DATASETS
            }
            snapshot_paths = {
                dataset: (
                    PROJECT_ROOT
                    / "data"
                    / "processed"
                    / "historical"
                    / dataset
                    / f"{dataset}_{season}.parquet"
                )
                for dataset in SOURCE_DATASETS
            }
        else:
            if player_identity is None:
                raise RuntimeError("Player identity source was not initialized.")
            prepared = download_prepared_sources(
                season, settings, scoring, player_identity
            )
            snapshot_paths = {
                dataset: write_source_snapshot(frame, dataset, season)
                for dataset, frame in prepared.items()
            }

        for dataset, frame in prepared.items():
            if season == target_season:
                frame = frame.filter(pl.col("week") <= through_week)
            collected[dataset].append(frame.to_pandas())
            hashes[f"{dataset}_{season}"] = sha256_file(
                snapshot_paths[dataset]
            )

    combined = {
        dataset: pd.concat(frames, ignore_index=True, sort=False)
        for dataset, frames in collected.items()
    }
    return combined, hashes


def require_unique(
    dataframe: pd.DataFrame, columns: list[str], label: str
) -> None:
    """Require complete, unique keys."""

    if dataframe[columns].isna().any(axis=1).any():
        raise ValueError(f"{label} contains unavailable key values.")
    duplicates = int(dataframe.duplicated(columns).sum())
    if duplicates:
        raise ValueError(f"{label} contains {duplicates} duplicate keys.")


def build_team_weeks(schedules: pd.DataFrame) -> pd.DataFrame:
    """Expand one game row into home-team and away-team context."""

    shared = {
        "season": schedules["season"],
        "week": schedules["week"],
        "game_id": schedules["game_id"],
        "game_date": pd.to_datetime(schedules["gameday"]).dt.normalize(),
        "source_spread_line": schedules["spread_line"],
        "total_line": schedules["total_line"],
        "div_game": schedules["div_game"],
        "roof": schedules["roof"],
        "surface": schedules["surface"],
    }
    home = pd.DataFrame(
        {
            **shared,
            "team": schedules["home_team"],
            "opponent": schedules["away_team"],
            "game_location": "HOME",
            "is_home": 1,
            "team_rest": schedules["home_rest"],
            "opponent_rest": schedules["away_rest"],
        }
    )
    away = pd.DataFrame(
        {
            **shared,
            "team": schedules["away_team"],
            "opponent": schedules["home_team"],
            "game_location": "AWAY",
            "is_home": 0,
            "team_rest": schedules["away_rest"],
            "opponent_rest": schedules["home_rest"],
        }
    )
    team_weeks = pd.concat([home, away], ignore_index=True)
    require_unique(team_weeks, ["season", "week", "team"], "Team weeks")
    return team_weeks


def build_snap_player_weeks(
    rosters: pd.DataFrame, snaps: pd.DataFrame
) -> pd.DataFrame:
    """Attach stable GSIS player identifiers to PFR-keyed snap rows."""

    crosswalk = rosters.loc[
        rosters["pfr_id"].notna()
        & rosters["pfr_id"].astype(str).str.strip().ne(""),
        ["season", "week", "team", "gsis_id", "pfr_id"],
    ].rename(
        columns={"gsis_id": "player_id", "pfr_id": "pfr_player_id"}
    )
    require_unique(
        crosswalk,
        ["season", "week", "team", "player_id"],
        "Roster player crosswalk",
    )
    require_unique(
        crosswalk,
        ["season", "week", "team", "pfr_player_id"],
        "Roster PFR crosswalk",
    )
    matched = snaps.merge(
        crosswalk,
        on=["season", "week", "team", "pfr_player_id"],
        how="left",
        validate="many_to_one",
    )
    matched = matched.loc[matched["player_id"].notna()].copy()
    require_unique(matched, ["game_id", "player_id"], "Matched snaps")
    return matched[
        ["game_id", "player_id", "offense_snaps", "offense_pct"]
    ]


def build_player_history(sources: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Construct the exact raw player-history contract used by features."""

    stats = sources["weekly_player_stats"].copy()
    require_unique(stats, ["season", "week", "player_id"], "Player stats")
    team_weeks = build_team_weeks(sources["schedules"])
    history = stats.merge(
        team_weeks,
        on=["season", "week", "game_id", "team"],
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    unmatched_schedule = int(history["_merge"].ne("both").sum())
    if unmatched_schedule:
        raise ValueError(
            f"Player history has {unmatched_schedule} unmatched schedule rows."
        )
    history = history.drop(columns="_merge")

    snap_player_weeks = build_snap_player_weeks(
        sources["weekly_rosters"], sources["snap_counts"]
    )
    history = history.merge(
        snap_player_weeks,
        on=["game_id", "player_id"],
        how="left",
        validate="one_to_one",
    )
    history["has_snap_record"] = history["offense_snaps"].notna().astype(int)

    count_columns = [
        "completions",
        "attempts",
        "passing_yards",
        "passing_tds",
        "carries",
        "rushing_yards",
        "rushing_tds",
        "receptions",
        "targets",
        "receiving_yards",
        "receiving_tds",
    ]
    for column in count_columns:
        history[column] = pd.to_numeric(
            history[column], errors="raise"
        ).fillna(0)
    for column in ["target_share", "air_yards_share", "wopr"]:
        history[column] = pd.to_numeric(
            history[column], errors="coerce"
        ).fillna(0.0)

    history["touches"] = history["carries"] + history["receptions"]
    history["position_adjusted_opportunities"] = history["targets"]
    history.loc[
        history["position"].eq("QB"), "position_adjusted_opportunities"
    ] = history["attempts"] + history["carries"]
    history.loc[
        history["position"].eq("RB"), "position_adjusted_opportunities"
    ] = history["carries"] + history["targets"]
    history["yards_from_scrimmage"] = (
        history["rushing_yards"] + history["receiving_yards"]
    )
    history["total_offensive_yards"] = (
        history["passing_yards"]
        + history["rushing_yards"]
        + history["receiving_yards"]
    )
    history["total_offensive_tds"] = (
        history["passing_tds"]
        + history["rushing_tds"]
        + history["receiving_tds"]
    )
    history["target_fantasy_points_ppr"] = pd.to_numeric(
        history["fantasy_points_ppr"], errors="raise"
    )

    history = history.loc[:, PLAYER_HISTORY_COLUMNS].sort_values(
        ["player_id", "season", "week", "game_date", "game_id"],
        kind="stable",
    )
    require_unique(
        history, ["season", "week", "player_id"], "Player history"
    )
    return history.reset_index(drop=True)


def build_opponent_history(player_history: pd.DataFrame) -> pd.DataFrame:
    """Aggregate completed player outcomes to defense-position-week grain."""

    grouped = (
        player_history.groupby(
            [
                "season",
                "week",
                "game_id",
                "game_date",
                "opponent",
                "position",
            ],
            dropna=False,
            sort=False,
        )
        .agg(
            fantasy_points_ppr_allowed=(
                "target_fantasy_points_ppr",
                "sum",
            ),
            passing_yards_allowed=("passing_yards", "sum"),
            rushing_yards_allowed=("rushing_yards", "sum"),
            receiving_yards_allowed=("receiving_yards", "sum"),
            position_adjusted_opportunities_allowed=(
                "position_adjusted_opportunities",
                "sum",
            ),
            total_offensive_tds_allowed=("total_offensive_tds", "sum"),
        )
        .reset_index()
        .rename(columns={"opponent": "defensive_team"})
    )
    grouped = grouped.loc[:, OPPONENT_HISTORY_COLUMNS].sort_values(
        [
            "defensive_team",
            "position",
            "season",
            "week",
            "game_date",
            "game_id",
        ],
        kind="stable",
    )
    require_unique(
        grouped,
        ["season", "week", "defensive_team", "position"],
        "Opponent history",
    )
    return grouped.reset_index(drop=True)


def build_manifest(
    arguments: argparse.Namespace,
    player_history: pd.DataFrame,
    opponent_history: pd.DataFrame,
    source_hashes: dict[str, str],
    player_output: Path,
    opponent_output: Path,
) -> pd.DataFrame:
    """Build compact history lineage and quality evidence."""

    current_rows = player_history.loc[
        player_history["season"].eq(arguments.season)
    ]
    rows = [
        ("run_timestamp_utc", datetime.now(timezone.utc).isoformat()),
        ("source_mode", arguments.source_mode),
        ("nflreadpy_version", package_version("nflreadpy")),
        ("start_season", arguments.start_season),
        ("target_season", arguments.season),
        ("through_week", arguments.through_week),
        ("player_history_rows", len(player_history)),
        ("opponent_history_rows", len(opponent_history)),
        ("current_season_player_rows", len(current_rows)),
        (
            "maximum_completed_week",
            (
                int(current_rows["week"].max())
                if not current_rows.empty
                else 0
            ),
        ),
        (
            "maximum_game_date",
            pd.to_datetime(player_history["game_date"]).max().isoformat(),
        ),
        (
            "player_history_duplicate_keys",
            int(
                player_history.duplicated(
                    ["season", "week", "player_id"]
                ).sum()
            ),
        ),
        (
            "opponent_history_duplicate_keys",
            int(
                opponent_history.duplicated(
                    ["season", "week", "defensive_team", "position"]
                ).sum()
            ),
        ),
        ("source_sha256", json.dumps(source_hashes, sort_keys=True)),
        ("player_history_path", display_path(player_output)),
        ("player_history_sha256", sha256_file(player_output)),
        ("opponent_history_path", display_path(opponent_output)),
        ("opponent_history_sha256", sha256_file(opponent_output)),
        ("history_refresh_status", "PASS"),
    ]
    return pd.DataFrame(rows, columns=["manifest_key", "manifest_value"])


def main() -> None:
    """Refresh portable historical inputs for one target scoring week."""

    arguments = parse_arguments()
    player_output = resolve_project_path(arguments.player_output)
    opponent_output = resolve_project_path(arguments.opponent_output)
    manifest_output = resolve_project_path(
        arguments.manifest_output
        or (
            "results/tables/history_refresh_"
            f"{arguments.season}_through_week_"
            f"{arguments.through_week:02d}_manifest.csv"
        )
    )

    sources, source_hashes = load_sources(
        arguments.start_season,
        arguments.season,
        arguments.through_week,
        arguments.source_mode,
    )
    player_history = build_player_history(sources)
    opponent_history = build_opponent_history(player_history)

    atomic_write_parquet(player_history, player_output)
    atomic_write_parquet(opponent_history, opponent_output)
    manifest = build_manifest(
        arguments,
        player_history,
        opponent_history,
        source_hashes,
        player_output,
        opponent_output,
    )
    atomic_write_csv(manifest, manifest_output)

    print(f"player_history_rows={len(player_history):,}")
    print(f"opponent_history_rows={len(opponent_history):,}")
    print(f"player_history={display_path(player_output)}")
    print(f"opponent_history={display_path(opponent_output)}")
    print(f"manifest={display_path(manifest_output)}")
    print("history_refresh_status=PASS")


if __name__ == "__main__":
    main()
