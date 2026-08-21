
"""Export and validate the model-ready player-week dataset."""

from __future__ import annotations

import argparse
import os
import re
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from pandas.api.types import is_numeric_dtype
from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import Engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "model_settings.toml"


def print_section(title: str) -> None:
    """Print a readable console section."""

    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Export the validated MySQL model_player_weeks table "
            "to a local Parquet file and reproducible sample."
        )
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to the model settings TOML file.",
    )
    return parser.parse_args()


def load_configuration(path: Path) -> dict[str, Any]:
    """Load a TOML configuration file."""

    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with path.open("rb") as file:
        return tomllib.load(file)


def resolve_project_path(path_value: str) -> Path:
    """Resolve and validate a configured project-relative path."""

    candidate = (PROJECT_ROOT / path_value).resolve()

    if candidate != PROJECT_ROOT and PROJECT_ROOT not in candidate.parents:
        raise ValueError(
            f"Configured output path leaves the project directory: {candidate}"
        )

    return candidate


def validate_identifier(identifier: str) -> str:
    """Allow only safe SQL identifiers from configuration."""

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"Unsafe SQL identifier: {identifier}")

    return identifier


def required_environment_value(name: str) -> str:
    """Return a required environment variable."""

    value = os.getenv(name)

    if value is None or value.strip() == "":
        raise ValueError(f"Required environment variable is missing: {name}")

    return value


def build_database_engine() -> Engine:
    """Create the SQLAlchemy MySQL engine without exposing credentials."""

    load_dotenv(PROJECT_ROOT / ".env")

    database_url = URL.create(
        drivername="mysql+pymysql",
        username=required_environment_value("MYSQL_USER"),
        password=required_environment_value("MYSQL_PASSWORD"),
        host=required_environment_value("MYSQL_HOST"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=required_environment_value("MYSQL_DATABASE"),
    )

    return create_engine(
        database_url,
        pool_pre_ping=True,
    )


def configured_columns(
    configuration: dict[str, Any],
) -> tuple[list[str], list[str], list[str], str, list[str]]:
    """Return and validate the configured model columns."""

    columns = configuration["columns"]

    metadata = list(columns["metadata"])
    categorical = list(columns["categorical_features"])
    numeric = list(columns["numeric_features"])
    target = str(columns["target"])
    forbidden = list(columns["forbidden_predictors"])

    all_columns = metadata + categorical + numeric + [target]

    duplicate_columns = sorted(
        {
            column
            for column in all_columns
            if all_columns.count(column) > 1
        }
    )

    if duplicate_columns:
        raise ValueError(
            "Configured columns appear more than once: "
            + ", ".join(duplicate_columns)
        )

    predictor_overlap = sorted(
        set(categorical + numeric) & set(forbidden)
    )

    if predictor_overlap:
        raise ValueError(
            "Forbidden columns appear in the predictor allowlist: "
            + ", ".join(predictor_overlap)
        )

    configured_key = list(columns["key"])
    missing_key_columns = sorted(
        set(configured_key) - set(all_columns)
    )

    if missing_key_columns:
        raise ValueError(
            "Configured key columns are missing from the export schema: "
            + ", ".join(missing_key_columns)
        )

    return metadata, categorical, numeric, target, all_columns


def load_live_schema(
    engine: Engine,
    source_table: str,
) -> tuple[str, list[str]]:
    """Load the live database name and source-table columns."""

    schema_query = text(
        """
        SELECT
            ordinal_position,
            column_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
        AND table_name = :table_name
        ORDER BY ordinal_position
        """
    )

    with engine.connect() as connection:
        database_name = connection.execute(
            text("SELECT DATABASE()")
        ).scalar_one()

        schema = pd.read_sql_query(
            schema_query,
            connection,
            params={"table_name": source_table},
        )
    schema.columns = [
        str(column).lower()
        for column in schema.columns
    ]

    if schema.empty:
        raise ValueError(
            f"Source table does not exist or has no columns: {source_table}"
        )

    return str(database_name), schema["column_name"].tolist()


def validate_schema_contract(
    live_columns: list[str],
    expected_columns: list[str],
    expected_column_count: int,
) -> None:
    """Require exact agreement between configuration and MySQL."""

    live_set = set(live_columns)
    configured_set = set(expected_columns)

    missing_from_configuration = sorted(
        live_set - configured_set
    )
    missing_from_database = sorted(
        configured_set - live_set
    )

    print(f"live_columns={len(live_columns)}")
    print(f"configured_columns={len(expected_columns)}")
    print(
        "missing_from_configuration="
        f"{missing_from_configuration}"
    )
    print(f"missing_from_database={missing_from_database}")

    if len(live_columns) != expected_column_count:
        raise ValueError(
            "Live source-column count does not match the configured "
            f"expectation: {len(live_columns)} != "
            f"{expected_column_count}"
        )

    if live_set != configured_set:
        raise ValueError(
            "The live MySQL schema does not match the configured "
            "model-column contract."
        )

    print("schema_contract=PASS")


def load_model_data(
    engine: Engine,
    source_table: str,
    live_columns: list[str],
) -> pd.DataFrame:
    """Load the model dataset in deterministic key order."""

    quoted_table = f"`{validate_identifier(source_table)}`"
    quoted_columns = ",\n            ".join(
        f"`{validate_identifier(column)}`"
        for column in live_columns
    )

    query = text(
        f"""
        SELECT
            {quoted_columns}
        FROM {quoted_table}
        ORDER BY
            `season`,
            `week`,
            `player_id`
        """
    )

    with engine.connect() as connection:
        return pd.read_sql_query(query, connection)


def expected_split_mapping(
    configuration: dict[str, Any],
) -> dict[int, str]:
    """Map every configured season to its chronological split."""

    split = configuration["split"]
    mapping: dict[int, str] = {}

    for season in split["training_seasons"]:
        mapping[int(season)] = split["training_label"]

    for season in split["validation_seasons"]:
        mapping[int(season)] = split["validation_label"]

    for season in split["test_seasons"]:
        mapping[int(season)] = split["test_label"]

    return mapping


def validate_dataframe(
    dataframe: pd.DataFrame,
    configuration: dict[str, Any],
    live_columns: list[str],
    numeric_features: list[str],
    target: str,
) -> None:
    """Run blocking export-quality controls."""

    quality = configuration["quality"]
    model = configuration["model"]
    split = configuration["split"]
    key_columns = list(configuration["columns"]["key"])

    expected_rows = int(quality["expected_source_rows"])
    expected_columns = int(quality["expected_source_columns"])

    actual_rows = len(dataframe)
    actual_columns = len(dataframe.columns)

    duplicate_key_groups = int(
        dataframe.groupby(
            key_columns,
            dropna=False,
        )
        .size()
        .gt(1)
        .sum()
    )

    unavailable_key_rows = int(
        dataframe[key_columns].isna().any(axis=1).sum()
    )

    blank_player_id_rows = int(
        dataframe["player_id"]
        .astype("string")
        .str.strip()
        .eq("")
        .fillna(False)
        .sum()
    )

    missing_target_rows = int(dataframe[target].isna().sum())

    split_counts = (
        dataframe["data_split"]
        .value_counts(dropna=False)
        .to_dict()
    )

    expected_split_counts = {
        split["training_label"]: int(
            quality["expected_training_rows"]
        ),
        split["validation_label"]: int(
            quality["expected_validation_rows"]
        ),
        split["test_label"]: int(
            quality["expected_test_rows"]
        ),
    }

    season_mapping = expected_split_mapping(configuration)
    expected_row_splits = dataframe["season"].map(season_mapping)

    split_mismatch_rows = int(
        (
            expected_row_splits.isna()
            | dataframe["data_split"].ne(expected_row_splits)
        ).sum()
    )

    invalid_feature_version_rows = int(
        dataframe["feature_version"]
        .ne(model["version"])
        .sum()
    )

    nonnumeric_features = [
        column
        for column in numeric_features
        if not is_numeric_dtype(dataframe[column])
    ]

    infinite_numeric_rows = int(
        dataframe[numeric_features]
        .isin([float("inf"), float("-inf")])
        .any(axis=1)
        .sum()
    )

    print(f"model_rows={actual_rows:,}")
    print(f"model_columns={actual_columns}")
    print(f"duplicate_key_groups={duplicate_key_groups}")
    print(f"unavailable_key_rows={unavailable_key_rows}")
    print(f"blank_player_id_rows={blank_player_id_rows}")
    print(f"missing_target_rows={missing_target_rows}")
    print(f"split_counts={split_counts}")
    print(f"expected_split_counts={expected_split_counts}")
    print(f"split_mismatch_rows={split_mismatch_rows}")
    print(
        "invalid_feature_version_rows="
        f"{invalid_feature_version_rows}"
    )
    print(f"nonnumeric_features={nonnumeric_features}")
    print(f"infinite_numeric_rows={infinite_numeric_rows}")

    if actual_rows != expected_rows:
        raise ValueError(
            f"Unexpected model row count: {actual_rows} != "
            f"{expected_rows}"
        )

    if actual_columns != expected_columns:
        raise ValueError(
            f"Unexpected model column count: {actual_columns} != "
            f"{expected_columns}"
        )

    if dataframe.columns.tolist() != live_columns:
        raise ValueError(
            "Exported dataframe column order differs from MySQL."
        )

    if duplicate_key_groups != 0:
        raise ValueError(
            f"Duplicate model key groups found: {duplicate_key_groups}"
        )

    if unavailable_key_rows != 0 or blank_player_id_rows != 0:
        raise ValueError("Unavailable model key values were found.")

    if missing_target_rows != 0:
        raise ValueError(
            f"Missing target rows found: {missing_target_rows}"
        )

    if split_counts != expected_split_counts:
        raise ValueError(
            "Observed split counts do not match configuration."
        )

    if split_mismatch_rows != 0:
        raise ValueError(
            f"Chronological split mismatches found: "
            f"{split_mismatch_rows}"
        )

    if invalid_feature_version_rows != 0:
        raise ValueError(
            "Unexpected feature-version rows found: "
            f"{invalid_feature_version_rows}"
        )

    if nonnumeric_features:
        raise ValueError(
            "Configured numeric features have nonnumeric dtypes: "
            + ", ".join(nonnumeric_features)
        )

    if infinite_numeric_rows != 0:
        raise ValueError(
            f"Infinite numeric feature rows found: "
            f"{infinite_numeric_rows}"
        )

    print("dataframe_quality=PASS")


def build_stratified_sample(
    dataframe: pd.DataFrame,
    configuration: dict[str, Any],
) -> pd.DataFrame:
    """Create a deterministic sample across splits and positions."""

    limit = int(configuration["export"]["sample_row_limit"])
    random_seed = int(configuration["model"]["random_seed"])
    positions = list(configuration["model"]["positions"])
    split = configuration["split"]

    split_order = [
        split["training_label"],
        split["validation_label"],
        split["test_label"],
    ]

    groups = [
        (split_name, position)
        for split_name in split_order
        for position in positions
    ]

    base_size = limit // len(groups)
    remainder = limit % len(groups)
    sample_parts: list[pd.DataFrame] = []

    for index, (split_name, position) in enumerate(groups):
        group = dataframe.loc[
            dataframe["data_split"].eq(split_name)
            & dataframe["position"].eq(position)
        ]

        requested_rows = base_size + int(index < remainder)
        requested_rows = min(requested_rows, len(group))

        sample_parts.append(
            group.sample(
                n=requested_rows,
                random_state=random_seed + index,
            )
        )

    sample = pd.concat(
        sample_parts,
        ignore_index=True,
    )

    return sample.sort_values(
        ["data_split", "position", "season", "week", "player_id"],
        kind="stable",
    ).reset_index(drop=True)


def build_manifest(
    dataframe: pd.DataFrame,
    configuration: dict[str, Any],
    database_name: str,
    source_table: str,
    parquet_path: Path,
) -> pd.DataFrame:
    """Create a split-and-position export manifest."""

    target = configuration["columns"]["target"]
    model = configuration["model"]
    split = configuration["split"]

    manifest = (
        dataframe.groupby(
            ["data_split", "position"],
            as_index=False,
            sort=False,
        )
        .agg(
            minimum_season=("season", "min"),
            maximum_season=("season", "max"),
            row_count=(target, "size"),
            distinct_players=("player_id", "nunique"),
            missing_target_rows=(target, lambda values: values.isna().sum()),
            average_target_ppr=(target, "mean"),
        )
    )

    split_order = {
        split["training_label"]: 1,
        split["validation_label"]: 2,
        split["test_label"]: 3,
    }
    position_order = {
        position: index
        for index, position in enumerate(
            model["positions"],
            start=1,
        )
    }

    manifest["_split_order"] = manifest["data_split"].map(
        split_order
    )
    manifest["_position_order"] = manifest["position"].map(
        position_order
    )

    manifest = manifest.sort_values(
        ["_split_order", "_position_order"]
    ).drop(
        columns=["_split_order", "_position_order"]
    )

    exported_at_utc = datetime.now(
        timezone.utc
    ).replace(
        microsecond=0
    ).isoformat()

    manifest.insert(0, "exported_at_utc", exported_at_utc)
    manifest.insert(1, "source_database", database_name)
    manifest.insert(2, "source_table", source_table)
    manifest.insert(
        3,
        "feature_version",
        model["version"],
    )
    manifest.insert(
        4,
        "parquet_file",
        parquet_path.relative_to(PROJECT_ROOT).as_posix(),
    )
    manifest.insert(
        5,
        "source_column_count",
        len(dataframe.columns),
    )
    manifest.insert(
        6,
        "predictor_count",
        len(configuration["columns"]["categorical_features"])
        + len(configuration["columns"]["numeric_features"]),
    )

    manifest["average_target_ppr"] = manifest[
        "average_target_ppr"
    ].round(4)

    return manifest.reset_index(drop=True)


def atomic_write_parquet(
    dataframe: pd.DataFrame,
    output_path: Path,
) -> None:
    """Write a Parquet file through a temporary file."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(
        f"{output_path.stem}.tmp{output_path.suffix}"
    )

    dataframe.to_parquet(
        temporary_path,
        engine="pyarrow",
        compression="snappy",
        index=False,
    )

    os.replace(temporary_path, output_path)


def atomic_write_csv(
    dataframe: pd.DataFrame,
    output_path: Path,
) -> None:
    """Write a UTF-8 CSV file through a temporary file."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(
        f"{output_path.stem}.tmp{output_path.suffix}"
    )

    dataframe.to_csv(
        temporary_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    os.replace(temporary_path, output_path)


def main() -> None:
    """Run the validated model-data export."""

    arguments = parse_arguments()
    config_path = Path(arguments.config).resolve()
    configuration = load_configuration(config_path)

    (
        metadata,
        categorical_features,
        numeric_features,
        target,
        expected_columns,
    ) = configured_columns(configuration)

    quality = configuration["quality"]
    export = configuration["export"]
    source_table = validate_identifier(export["source_table"])

    parquet_path = resolve_project_path(export["parquet_path"])
    sample_path = resolve_project_path(export["sample_path"])
    manifest_path = resolve_project_path(export["manifest_path"])

    print_section("NFL MODEL DATA EXPORT")
    print(f"Configuration: {config_path}")
    print(f"Source table: {source_table}")
    print(f"Metadata columns: {len(metadata)}")
    print(f"Categorical features: {len(categorical_features)}")
    print(f"Numeric features: {len(numeric_features)}")
    print(
        "Total predictor features: "
        f"{len(categorical_features) + len(numeric_features)}"
    )
    print(f"Target: {target}")

    engine = build_database_engine()

    try:
        print_section("LIVE MYSQL SCHEMA CONTRACT")

        database_name, live_columns = load_live_schema(
            engine,
            source_table,
        )

        print(f"Connected database: {database_name}")

        validate_schema_contract(
            live_columns=live_columns,
            expected_columns=expected_columns,
            expected_column_count=int(
                quality["expected_source_columns"]
            ),
        )

        print_section("LOADING MODEL DATA")

        dataframe = load_model_data(
            engine=engine,
            source_table=source_table,
            live_columns=live_columns,
        )

        print_section("EXPORT QUALITY CONTROLS")

        validate_dataframe(
            dataframe=dataframe,
            configuration=configuration,
            live_columns=live_columns,
            numeric_features=numeric_features,
            target=target,
        )

        print_section("WRITING MODEL ARTIFACTS")

        sample = build_stratified_sample(
            dataframe,
            configuration,
        )

        manifest = build_manifest(
            dataframe=dataframe,
            configuration=configuration,
            database_name=database_name,
            source_table=source_table,
            parquet_path=parquet_path,
        )

        atomic_write_parquet(dataframe, parquet_path)
        atomic_write_csv(sample, sample_path)
        atomic_write_csv(manifest, manifest_path)

        parquet_size_mb = parquet_path.stat().st_size / (1024 * 1024)

        print(
            f"Wrote {parquet_path.relative_to(PROJECT_ROOT)}: "
            f"{len(dataframe):,} rows, "
            f"{parquet_size_mb:.2f} MB"
        )
        print(
            f"Wrote {sample_path.relative_to(PROJECT_ROOT)}: "
            f"{len(sample):,} rows"
        )
        print(
            f"Wrote {manifest_path.relative_to(PROJECT_ROOT)}: "
            f"{len(manifest):,} rows"
        )

        print_section("MODEL DATA EXPORT COMPLETE")
        print("schema_contract=PASS")
        print("dataframe_quality=PASS")
        print("model_export_status=PASS")

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()