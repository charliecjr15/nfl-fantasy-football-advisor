import argparse
import os
from importlib.metadata import version
from pathlib import Path

import nflreadpy as nfl
import polars as pl
from dotenv import load_dotenv
from nflreadpy.config import update_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]

PROFILE_COLUMNS = [
    "season",
    "week",
    "season_type",
    "game_id",
    "player_id",
    "gsis_id",
    "pfr_player_id",
    "player_name",
    "full_name",
    "team",
    "recent_team",
    "opponent_team",
    "position",
    "report_status",
    "practice_status",
]

PREVIEW_COLUMNS = [
    "season",
    "week",
    "season_type",
    "game_id",
    "player_id",
    "gsis_id",
    "player_name",
    "full_name",
    "team",
    "recent_team",
    "opponent_team",
    "position",
    "report_status",
    "practice_status",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Inspect nflverse datasets before defining analytical keys "
            "or MySQL tables."
        )
    )
    parser.add_argument(
        "--season",
        type=int,
        required=True,
        help="NFL season to inspect, such as 2025.",
    )
    return parser.parse_args()


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


def print_range(dataframe, column):
    if column not in dataframe.columns:
        return

    values = dataframe.get_column(column).drop_nulls()

    if values.len() == 0:
        print(f"{column}_minimum=None")
        print(f"{column}_maximum=None")
        return

    print(f"{column}_minimum={values.min()}")
    print(f"{column}_maximum={values.max()}")


def print_profile_columns(dataframe):
    print("Selected column controls:")

    available_columns = [
        column
        for column in PROFILE_COLUMNS
        if column in dataframe.columns
    ]

    if not available_columns:
        print("  No planned profile columns were found.")
        return

    for column in available_columns:
        series = dataframe.get_column(column)
        null_rows = series.null_count()

        blank_rows = (
            int(
                (
                    series
                    .str
                    .strip_chars()
                    == ""
                ).sum()
            )
            if series.dtype == pl.String
            else 0
        )

        unavailable_rows = null_rows + blank_rows
        unavailable_pct = (
            round(
                (
                    unavailable_rows
                    / dataframe.height
                )
                * 100,
                2,
            )
            if dataframe.height
            else 0.0
        )

        print(
            f"  {column}: "
            f"dtype={series.dtype}, "
            f"null_rows={null_rows:,}, "
            f"blank_rows={blank_rows:,}, "
            f"unavailable_rows={unavailable_rows:,}, "
            f"unavailable_pct={unavailable_pct:.2f}, "
            f"distinct_values={series.n_unique():,}"
        )


def print_top_null_columns(dataframe):
    if dataframe.height == 0:
        print("Top null columns: dataset has no rows.")
        return

    null_summary = []

    for column in dataframe.columns:
        null_rows = dataframe.get_column(column).null_count()

        if null_rows > 0:
            null_pct = round(
                (null_rows / dataframe.height) * 100,
                2,
            )
            null_summary.append(
                (column, null_rows, null_pct)
            )

    null_summary.sort(
        key=lambda row: (-row[1], row[0])
    )

    print("Top null columns:")

    if not null_summary:
        print("  None")
        return

    for column, null_rows, null_pct in null_summary[:10]:
        print(
            f"  {column}: "
            f"null_rows={null_rows:,}, "
            f"null_pct={null_pct:.2f}"
        )


def print_preview(dataframe):
    available_columns = [
        column
        for column in PREVIEW_COLUMNS
        if column in dataframe.columns
    ]

    print("Three-row identifier preview:")

    if not available_columns or dataframe.height == 0:
        print("  No preview available.")
        return

    preview_rows = (
        dataframe
        .select(available_columns)
        .head(3)
        .to_dicts()
    )

    for row in preview_rows:
        print(f"  {row}")


def profile_dataset(dataset_name, dataframe):
    if not isinstance(dataframe, pl.DataFrame):
        raise TypeError(
            f"{dataset_name} did not return a Polars DataFrame."
        )

    print()
    print("=" * 72)
    print(dataset_name)
    print("=" * 72)
    print(f"rows={dataframe.height:,}")
    print(f"columns={dataframe.width:,}")
    print("column_names=" + ", ".join(dataframe.columns))

    schema_text = ", ".join(
        f"{column}:{data_type}"
        for column, data_type in dataframe.schema.items()
    )
    print("schema=" + schema_text)

    print_range(dataframe, "season")
    print_range(dataframe, "week")
    print_profile_columns(dataframe)
    print_top_null_columns(dataframe)
    print_preview(dataframe)


def main():
    args = parse_args()
    configure_cache()

    print(f"Python package nflreadpy={version('nflreadpy')}")
    print(f"Python package polars={version('polars')}")
    print(f"Inspection season={args.season}")

    dataset_loaders = [
        (
            "weekly_player_stats",
            lambda: nfl.load_player_stats(
                args.season,
                summary_level="week",
            ),
        ),
        (
            "schedules",
            lambda: nfl.load_schedules(args.season),
        ),
        (
            "weekly_rosters",
            lambda: nfl.load_rosters_weekly(args.season),
        ),
        (
            "injuries",
            lambda: nfl.load_injuries(args.season),
        ),
        (
            "depth_charts",
            lambda: nfl.load_depth_charts(args.season),
        ),
        (
            "snap_counts",
            lambda: nfl.load_snap_counts(args.season),
        ),
    ]

    failures = []

    for dataset_name, loader in dataset_loaders:
        try:
            dataframe = loader()
            profile_dataset(dataset_name, dataframe)
        except Exception as error:
            failures.append(
                (dataset_name, type(error).__name__, str(error))
            )
            print()
            print("=" * 72)
            print(dataset_name)
            print("=" * 72)
            print(
                f"LOAD FAILED: "
                f"{type(error).__name__}: {error}"
            )

    print()
    print("=" * 72)
    print("SOURCE INSPECTION SUMMARY")
    print("=" * 72)
    print(
        f"datasets_attempted={len(dataset_loaders)}"
    )
    print(
        f"datasets_loaded="
        f"{len(dataset_loaders) - len(failures)}"
    )
    print(f"datasets_failed={len(failures)}")

    if failures:
        for dataset_name, error_type, message in failures:
            print(
                f"  {dataset_name}: "
                f"{error_type}: {message}"
            )
        raise SystemExit(1)

    print("All source datasets loaded successfully.")


if __name__ == "__main__":
    main()