"""Load validated historical Parquet partitions into MySQL staging tables."""

from __future__ import annotations

import argparse
import csv
import math
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pymysql
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    PROJECT_ROOT
    / "data"
    / "sample"
    / "historical_extraction_manifest.csv"
)

TABLE_BY_DATASET = {
    "schedules": "stg_schedules",
    "weekly_rosters": "stg_weekly_rosters",
    "injuries": "stg_injuries",
    "depth_charts": "stg_depth_charts",
    "snap_counts": "stg_snap_counts",
    "weekly_player_stats": "stg_weekly_player_stats",
}

LOAD_ORDER = tuple(TABLE_BY_DATASET)

SEASON_COLUMN_BY_DATASET = {
    "schedules": "season",
    "weekly_rosters": "season",
    "injuries": "season",
    "depth_charts": "source_season",
    "snap_counts": "season",
    "weekly_player_stats": "season",
}

MYSQL_GENERATED_COLUMNS = {
    "staging_row_id",
    "loaded_at",
}

VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Partition:
    """One dataset-season partition recorded in the extraction manifest."""

    season: int
    data_split: str
    dataset_name: str
    processed_rows: int
    output_file: Path


def parse_arguments() -> argparse.Namespace:
    """Parse command-line options."""

    parser = argparse.ArgumentParser(
        description=(
            "Load the historical NFL Parquet partitions into MySQL "
            "staging tables."
        )
    )
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="Path to the historical extraction manifest.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5_000,
        help="Rows inserted in each database batch.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help=(
            "Truncate all six staging tables before loading. "
            "Required when any staging table already contains rows."
        ),
    )
    return parser.parse_args()


def resolve_project_path(raw_path: str) -> Path:
    """Resolve a path relative to the project root."""

    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def quote_identifier(identifier: str) -> str:
    """Safely quote a known MySQL identifier."""

    if not VALID_IDENTIFIER.fullmatch(identifier):
        raise ValueError(f"Unsafe SQL identifier: {identifier!r}")
    return f"`{identifier}`"


def load_manifest(manifest_path: Path) -> list[Partition]:
    """Read and validate the extraction manifest."""

    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Extraction manifest not found: {manifest_path}"
        )

    required_columns = {
        "season",
        "data_split",
        "dataset_name",
        "processed_rows",
        "output_file",
    }

    partitions: list[Partition] = []

    with manifest_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as manifest_file:
        reader = csv.DictReader(manifest_file)

        available_columns = set(reader.fieldnames or [])
        missing_columns = required_columns - available_columns

        if missing_columns:
            missing_text = ", ".join(sorted(missing_columns))
            raise ValueError(
                f"Manifest is missing required columns: {missing_text}"
            )

        for row_number, row in enumerate(reader, start=2):
            dataset_name = row["dataset_name"].strip()

            if dataset_name not in TABLE_BY_DATASET:
                raise ValueError(
                    f"Manifest row {row_number} contains an unknown "
                    f"dataset: {dataset_name!r}"
                )

            output_file = resolve_project_path(
                row["output_file"].strip()
            )

            partitions.append(
                Partition(
                    season=int(row["season"]),
                    data_split=row["data_split"].strip(),
                    dataset_name=dataset_name,
                    processed_rows=int(row["processed_rows"]),
                    output_file=output_file,
                )
            )

    if not partitions:
        raise ValueError("The extraction manifest contains no partitions.")

    keys = [
        (partition.dataset_name, partition.season)
        for partition in partitions
    ]

    duplicate_keys = {
        key
        for key in keys
        if keys.count(key) > 1
    }

    if duplicate_keys:
        duplicate_text = ", ".join(
            f"{dataset}-{season}"
            for dataset, season in sorted(duplicate_keys)
        )
        raise ValueError(
            f"Manifest contains repeated partition keys: {duplicate_text}"
        )

    order_index = {
        dataset_name: position
        for position, dataset_name in enumerate(LOAD_ORDER)
    }

    return sorted(
        partitions,
        key=lambda partition: (
            order_index[partition.dataset_name],
            partition.season,
        ),
    )


def validate_parquet_files(
    partitions: list[Partition],
) -> dict[str, tuple[str, ...]]:
    """Validate paths, row counts, and schemas before changing MySQL."""

    schemas: dict[str, tuple[str, ...]] = {}

    for partition in partitions:
        if not partition.output_file.exists():
            raise FileNotFoundError(
                f"Parquet partition not found: {partition.output_file}"
            )

        parquet_file = pq.ParquetFile(partition.output_file)
        parquet_rows = parquet_file.metadata.num_rows
        parquet_columns = tuple(parquet_file.schema_arrow.names)

        if parquet_rows != partition.processed_rows:
            raise ValueError(
                f"{partition.dataset_name} {partition.season} has "
                f"{parquet_rows:,} Parquet rows but the manifest "
                f"expects {partition.processed_rows:,}."
            )

        previous_schema = schemas.get(partition.dataset_name)

        if previous_schema is None:
            schemas[partition.dataset_name] = parquet_columns
        elif previous_schema != parquet_columns:
            raise ValueError(
                f"{partition.dataset_name} has inconsistent columns "
                f"in season {partition.season}."
            )

    print(
        f"Validated {len(partitions)} Parquet partitions "
        "against the extraction manifest."
    )

    return schemas


def load_database_environment() -> dict[str, Any]:
    """Load and validate the private MySQL environment settings."""

    env_path = PROJECT_ROOT / ".env"

    if not env_path.exists():
        raise FileNotFoundError(
            f"Private environment file not found: {env_path}"
        )

    load_dotenv(env_path)

    settings = {
        "host": os.getenv("MYSQL_HOST"),
        "port": os.getenv("MYSQL_PORT", "3306"),
        "user": os.getenv("MYSQL_USER"),
        "password": os.getenv("MYSQL_PASSWORD"),
        "database": os.getenv("MYSQL_DATABASE"),
    }

    missing = [
        key
        for key, value in settings.items()
        if value is None
    ]

    if missing:
        raise ValueError(
            "Missing MySQL environment values: "
            + ", ".join(sorted(missing))
        )

    if settings["user"] == "your_mysql_username":
        raise ValueError("MYSQL_USER still contains the template value.")

    if settings["password"] == "your_mysql_password":
        raise ValueError(
            "MYSQL_PASSWORD still contains the template value."
        )

    try:
        settings["port"] = int(settings["port"])
    except ValueError as exc:
        raise ValueError("MYSQL_PORT must be an integer.") from exc

    return settings


def connect_to_mysql(
    settings: dict[str, Any],
) -> pymysql.connections.Connection:
    """Create the MySQL connection without printing credentials."""

    connection = pymysql.connect(
        host=settings["host"],
        port=settings["port"],
        user=settings["user"],
        password=settings["password"],
        database=settings["database"],
        charset="utf8mb4",
        autocommit=False,
        connect_timeout=10,
        read_timeout=600,
        write_timeout=600,
    )

    with connection.cursor() as cursor:
        cursor.execute("SET SESSION time_zone = '+00:00'")
        cursor.execute("SELECT DATABASE()")
        active_database = cursor.fetchone()[0]

    if active_database != settings["database"]:
        connection.close()
        raise ValueError(
            f"Connected to {active_database!r}, but .env specifies "
            f"{settings['database']!r}."
        )

    print(
        f"Connected to MySQL database: {active_database}"
    )

    return connection


def get_mysql_data_columns(
    connection: pymysql.connections.Connection,
    database_name: str,
    table_name: str,
) -> tuple[str, ...]:
    """Return non-generated staging columns in ordinal order."""

    query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s
        AND table_name = %s
        ORDER BY ordinal_position
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (database_name, table_name))
        columns = [
            row[0]
            for row in cursor.fetchall()
            if row[0] not in MYSQL_GENERATED_COLUMNS
        ]

    return tuple(columns)


def validate_mysql_schemas(
    connection: pymysql.connections.Connection,
    database_name: str,
    parquet_schemas: dict[str, tuple[str, ...]],
) -> None:
    """Confirm every Parquet column has a matching MySQL column."""

    for dataset_name in LOAD_ORDER:
        table_name = TABLE_BY_DATASET[dataset_name]
        mysql_columns = get_mysql_data_columns(
            connection,
            database_name,
            table_name,
        )

        if not mysql_columns:
            raise ValueError(
                f"MySQL staging table not found: {table_name}"
            )

        parquet_columns = parquet_schemas[dataset_name]

        if mysql_columns != parquet_columns:
            missing_in_mysql = sorted(
                set(parquet_columns) - set(mysql_columns)
            )
            extra_in_mysql = sorted(
                set(mysql_columns) - set(parquet_columns)
            )

            raise ValueError(
                f"Schema mismatch for {table_name}. "
                f"Missing in MySQL: {missing_in_mysql or 'None'}. "
                f"Extra in MySQL: {extra_in_mysql or 'None'}."
            )

    print("All six MySQL staging schemas match the Parquet files.")


def get_table_counts(
    connection: pymysql.connections.Connection,
) -> dict[str, int]:
    """Return current row counts for all staging tables."""

    counts: dict[str, int] = {}

    with connection.cursor() as cursor:
        for dataset_name in LOAD_ORDER:
            table_name = TABLE_BY_DATASET[dataset_name]
            cursor.execute(
                f"SELECT COUNT(*) FROM {quote_identifier(table_name)}"
            )
            counts[table_name] = int(cursor.fetchone()[0])

    return counts


def prepare_staging_tables(
    connection: pymysql.connections.Connection,
    replace: bool,
) -> None:
    """Require explicit permission before clearing existing rows."""

    counts = get_table_counts(connection)
    populated = {
        table_name: row_count
        for table_name, row_count in counts.items()
        if row_count > 0
    }

    if populated and not replace:
        details = ", ".join(
            f"{table_name}={row_count:,}"
            for table_name, row_count in populated.items()
        )
        raise RuntimeError(
            "Staging tables already contain rows: "
            f"{details}. Run again with --replace to truncate and reload "
            "all six reproducible staging tables."
        )

    if replace:
        print("Truncating all six staging tables...")

        connection.commit()

        with connection.cursor() as cursor:
            for dataset_name in LOAD_ORDER:
                table_name = TABLE_BY_DATASET[dataset_name]
                cursor.execute(
                    f"TRUNCATE TABLE {quote_identifier(table_name)}"
                )

        connection.commit()
        print("All staging tables were truncated.")
    else:
        print("All staging tables are empty; no truncation was needed.")


def normalize_mysql_value(value: Any) -> Any:
    """Convert Arrow values into MySQL-safe Python values."""

    if isinstance(value, datetime) and value.tzinfo is not None:
        return (
            value.astimezone(timezone.utc)
            .replace(tzinfo=None)
        )

    if isinstance(value, float) and not math.isfinite(value):
        return None

    return value


def build_insert_statement(
    table_name: str,
    columns: tuple[str, ...],
) -> str:
    """Build a parameterized INSERT statement."""

    column_sql = ", ".join(
        quote_identifier(column)
        for column in columns
    )
    placeholder_sql = ", ".join(
        ["%s"] * len(columns)
    )

    return (
        f"INSERT INTO {quote_identifier(table_name)} "
        f"({column_sql}) VALUES ({placeholder_sql})"
    )


def load_partition(
    connection: pymysql.connections.Connection,
    partition: Partition,
    batch_size: int,
) -> int:
    """Load one Parquet partition as one database transaction."""

    table_name = TABLE_BY_DATASET[partition.dataset_name]
    parquet_file = pq.ParquetFile(partition.output_file)
    columns = tuple(parquet_file.schema_arrow.names)
    insert_sql = build_insert_statement(table_name, columns)

    loaded_rows = 0
    next_progress_mark = 100_000
    started_at = time.perf_counter()

    try:
        with connection.cursor() as cursor:
            for batch in parquet_file.iter_batches(
                batch_size=batch_size,
                use_threads=True,
            ):
                column_values = batch.to_pydict()
                ordered_columns = [
                    column_values[column]
                    for column in columns
                ]

                records = [
                    tuple(
                        normalize_mysql_value(column[row_index])
                        for column in ordered_columns
                    )
                    for row_index in range(batch.num_rows)
                ]

                cursor.executemany(insert_sql, records)
                loaded_rows += batch.num_rows

                if loaded_rows >= next_progress_mark:
                    print(
                        f"    inserted {loaded_rows:,} of "
                        f"{partition.processed_rows:,} rows"
                    )
                    next_progress_mark += 100_000

        if loaded_rows != partition.processed_rows:
            raise ValueError(
                f"Inserted {loaded_rows:,} rows but expected "
                f"{partition.processed_rows:,}."
            )

        connection.commit()

    except Exception:
        connection.rollback()
        print(
            f"    rolled back {partition.dataset_name} "
            f"{partition.season}"
        )
        raise

    elapsed_seconds = time.perf_counter() - started_at

    print(
        f"    committed {loaded_rows:,} rows "
        f"in {elapsed_seconds:,.1f} seconds"
    )

    return loaded_rows


def expected_counts(
    partitions: list[Partition],
) -> tuple[dict[str, int], dict[tuple[str, int], int]]:
    """Calculate expected totals from the extraction manifest."""

    dataset_totals: dict[str, int] = defaultdict(int)
    partition_totals: dict[tuple[str, int], int] = {}

    for partition in partitions:
        dataset_totals[partition.dataset_name] += (
            partition.processed_rows
        )
        partition_totals[
            (partition.dataset_name, partition.season)
        ] = partition.processed_rows

    return dict(dataset_totals), partition_totals


def reconcile_mysql_counts(
    connection: pymysql.connections.Connection,
    partitions: list[Partition],
) -> None:
    """Reconcile MySQL totals and season counts to the manifest."""

    expected_dataset, expected_partition = expected_counts(partitions)
    problems: list[str] = []

    print()
    print("=" * 72)
    print("MYSQL STAGING RECONCILIATION")
    print("=" * 72)
    print(
        f"{'dataset':<24}"
        f"{'expected':>14}"
        f"{'actual':>14}"
        f"{'difference':>14}"
    )

    with connection.cursor() as cursor:
        for dataset_name in LOAD_ORDER:
            table_name = TABLE_BY_DATASET[dataset_name]
            season_column = SEASON_COLUMN_BY_DATASET[dataset_name]

            cursor.execute(
                f"SELECT COUNT(*) "
                f"FROM {quote_identifier(table_name)}"
            )
            actual_total = int(cursor.fetchone()[0])
            expected_total = expected_dataset[dataset_name]
            difference = actual_total - expected_total

            print(
                f"{dataset_name:<24}"
                f"{expected_total:>14,}"
                f"{actual_total:>14,}"
                f"{difference:>14,}"
            )

            if difference != 0:
                problems.append(
                    f"{dataset_name} total differs by {difference:,}"
                )

            cursor.execute(
                f"SELECT {quote_identifier(season_column)}, COUNT(*) "
                f"FROM {quote_identifier(table_name)} "
                f"GROUP BY {quote_identifier(season_column)}"
            )

            actual_by_season = {
                int(season): int(row_count)
                for season, row_count in cursor.fetchall()
                if season is not None
            }

            for partition in [
                item
                for item in partitions
                if item.dataset_name == dataset_name
            ]:
                expected_rows = expected_partition[
                    (dataset_name, partition.season)
                ]
                actual_rows = actual_by_season.get(
                    partition.season,
                    0,
                )

                if actual_rows != expected_rows:
                    problems.append(
                        f"{dataset_name} {partition.season}: "
                        f"expected {expected_rows:,}, "
                        f"found {actual_rows:,}"
                    )

    if problems:
        problem_text = "\n".join(
            f"- {problem}"
            for problem in problems
        )
        raise ValueError(
            "MySQL staging reconciliation failed:\n"
            + problem_text
        )

    print()
    print("All MySQL staging row counts match the manifest.")


def main() -> None:
    """Run the complete staging load."""

    args = parse_arguments()

    if args.batch_size <= 0:
        raise ValueError("--batch-size must be greater than zero.")

    manifest_path = resolve_project_path(args.manifest)

    print("=" * 72)
    print("NFL HISTORICAL MYSQL STAGING LOAD")
    print("=" * 72)
    print(f"Manifest: {manifest_path}")
    print(f"Batch size: {args.batch_size:,}")
    print(f"Replace existing rows: {args.replace}")

    partitions = load_manifest(manifest_path)
    parquet_schemas = validate_parquet_files(partitions)
    settings = load_database_environment()
    connection = connect_to_mysql(settings)

    try:
        validate_mysql_schemas(
            connection,
            settings["database"],
            parquet_schemas,
        )
        prepare_staging_tables(
            connection,
            args.replace,
        )

        print()
        print("=" * 72)
        print("LOADING PARTITIONS")
        print("=" * 72)

        total_loaded_rows = 0
        overall_started_at = time.perf_counter()

        for partition_number, partition in enumerate(
            partitions,
            start=1,
        ):
            print(
                f"[{partition_number:02d}/{len(partitions):02d}] "
                f"{partition.dataset_name} {partition.season} "
                f"({partition.data_split}) - "
                f"{partition.processed_rows:,} rows"
            )

            total_loaded_rows += load_partition(
                connection,
                partition,
                args.batch_size,
            )

        reconcile_mysql_counts(
            connection,
            partitions,
        )

        elapsed_seconds = (
            time.perf_counter()
            - overall_started_at
        )

        print()
        print("=" * 72)
        print("MYSQL STAGING LOAD COMPLETE")
        print("=" * 72)
        print(f"Partitions loaded: {len(partitions)}")
        print(f"Rows loaded: {total_loaded_rows:,}")
        print(f"Elapsed seconds: {elapsed_seconds:,.1f}")
        print("All staging loads passed.")

    finally:
        connection.close()


if __name__ == "__main__":
    main()