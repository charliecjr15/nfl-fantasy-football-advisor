"""Evaluate leakage-safe fantasy-point baselines on validation data."""

from __future__ import annotations

import argparse
import os
import tomllib
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "model_settings.toml"

SUPPORTED_BASELINES = {
    "training_position_mean",
    "previous_game",
    "rolling_3_game",
    "rolling_5_game",
}

RAW_BASELINE_COLUMNS = {
    "training_position_mean": None,
    "previous_game": "fantasy_points_ppr_prev_game",
    "rolling_3_game": "fantasy_points_ppr_avg_last_3_games",
    "rolling_5_game": "fantasy_points_ppr_avg_last_5_games",
}


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
            "Evaluate simple fantasy-point baselines using only "
            "the configured validation split."
        )
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to the model settings TOML file.",
    )
    return parser.parse_args()


def load_configuration(path: Path) -> dict[str, Any]:
    """Load the model settings."""

    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with path.open("rb") as file:
        return tomllib.load(file)


def resolve_project_path(path_value: str) -> Path:
    """Resolve a configured path inside the project."""

    candidate = (PROJECT_ROOT / path_value).resolve()

    if candidate != PROJECT_ROOT and PROJECT_ROOT not in candidate.parents:
        raise ValueError(
            f"Configured path leaves the project directory: {candidate}"
        )

    return candidate


def validate_configuration(
    configuration: dict[str, Any],
) -> None:
    """Validate the baseline evaluation contract."""

    baseline = configuration["baseline"]
    split = configuration["split"]

    evaluation_split = baseline["evaluation_split"]
    validation_label = split["validation_label"]
    test_label = split["test_label"]

    if evaluation_split != validation_label:
        raise ValueError(
            "Baseline development must use the validation split."
        )

    if evaluation_split == test_label:
        raise ValueError(
            "The test split cannot be used during baseline development."
        )

    if baseline["allow_test_evaluation"]:
        raise ValueError(
            "allow_test_evaluation must remain false during "
            "baseline development."
        )

    configured_models = set(baseline["models"])
    unsupported_models = sorted(
        configured_models - SUPPORTED_BASELINES
    )
    missing_models = sorted(
        SUPPORTED_BASELINES - configured_models
    )

    if unsupported_models:
        raise ValueError(
            "Unsupported baseline models: "
            + ", ".join(unsupported_models)
        )

    if missing_models:
        raise ValueError(
            "Required baseline models are missing: "
            + ", ".join(missing_models)
        )

    if baseline["primary_baseline"] not in configured_models:
        raise ValueError(
            "The primary baseline is not in the configured model list."
        )


def load_development_data(
    parquet_path: Path,
    configuration: dict[str, Any],
) -> pd.DataFrame:
    """Load only training and validation rows from Parquet."""

    split = configuration["split"]
    allowed_splits = [
        split["training_label"],
        split["validation_label"],
    ]

    if not parquet_path.exists():
        raise FileNotFoundError(
            "Model Parquet file not found. Run "
            "scripts/export_model_data.py first."
        )

    dataframe = pd.read_parquet(
        parquet_path,
        engine="pyarrow",
        filters=[
            (
                "data_split",
                "in",
                allowed_splits,
            )
        ],
    )

    unexpected_splits = sorted(
        set(dataframe["data_split"].dropna().unique())
        - set(allowed_splits)
    )

    if unexpected_splits:
        raise ValueError(
            "Unexpected splits loaded during baseline development: "
            + ", ".join(unexpected_splits)
        )

    if split["test_label"] in set(
        dataframe["data_split"].dropna().unique()
    ):
        raise ValueError(
            "Test rows were loaded during baseline development."
        )

    return dataframe


def validate_development_data(
    dataframe: pd.DataFrame,
    configuration: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate training and validation input partitions."""

    quality = configuration["quality"]
    split = configuration["split"]
    columns = configuration["columns"]

    training_label = split["training_label"]
    validation_label = split["validation_label"]
    target = columns["target"]
    key = list(columns["key"])

    training = dataframe.loc[
        dataframe["data_split"].eq(training_label)
    ].copy()

    validation = dataframe.loc[
        dataframe["data_split"].eq(validation_label)
    ].copy()

    expected_training_rows = int(
        quality["expected_training_rows"]
    )
    expected_validation_rows = int(
        quality["expected_validation_rows"]
    )

    duplicate_training_keys = int(
        training.duplicated(key).sum()
    )
    duplicate_validation_keys = int(
        validation.duplicated(key).sum()
    )

    missing_training_targets = int(
        training[target].isna().sum()
    )
    missing_validation_targets = int(
        validation[target].isna().sum()
    )

    print(f"training_rows={len(training):,}")
    print(f"validation_rows={len(validation):,}")
    print("test_rows_loaded=0")
    print(
        "duplicate_training_keys="
        f"{duplicate_training_keys}"
    )
    print(
        "duplicate_validation_keys="
        f"{duplicate_validation_keys}"
    )
    print(
        "missing_training_targets="
        f"{missing_training_targets}"
    )
    print(
        "missing_validation_targets="
        f"{missing_validation_targets}"
    )

    if len(training) != expected_training_rows:
        raise ValueError(
            f"Unexpected training rows: {len(training)} != "
            f"{expected_training_rows}"
        )

    if len(validation) != expected_validation_rows:
        raise ValueError(
            f"Unexpected validation rows: {len(validation)} != "
            f"{expected_validation_rows}"
        )

    if duplicate_training_keys != 0:
        raise ValueError("Duplicate training keys were found.")

    if duplicate_validation_keys != 0:
        raise ValueError("Duplicate validation keys were found.")

    if missing_training_targets != 0:
        raise ValueError("Missing training targets were found.")

    if missing_validation_targets != 0:
        raise ValueError("Missing validation targets were found.")

    return training, validation


def add_coalesced_prediction(
    dataframe: pd.DataFrame,
    baseline_name: str,
    candidates: list[tuple[str, str]],
) -> None:
    """Create a prediction and record which fallback supplied it."""

    prediction_column = f"prediction_{baseline_name}"
    source_column = f"prediction_source_{baseline_name}"

    prediction = pd.Series(
        float("nan"),
        index=dataframe.index,
        dtype="float64",
    )
    prediction_source = pd.Series(
        pd.NA,
        index=dataframe.index,
        dtype="string",
    )

    for candidate_column, source_name in candidates:
        available = (
            prediction.isna()
            & dataframe[candidate_column].notna()
        )

        prediction.loc[available] = dataframe.loc[
            available,
            candidate_column,
        ].astype("float64")

        prediction_source.loc[available] = source_name

    dataframe[prediction_column] = prediction
    dataframe[source_column] = prediction_source


def build_baseline_predictions(
    training: pd.DataFrame,
    validation: pd.DataFrame,
    configuration: dict[str, Any],
) -> pd.DataFrame:
    """Build validation predictions without using validation targets."""

    target = configuration["columns"]["target"]

    training_position_means = (
        training.groupby("position")[target]
        .mean()
        .rename("_training_position_mean")
    )

    predictions = validation.copy()

    predictions["_training_position_mean"] = (
        predictions["position"].map(training_position_means)
    )

    if predictions["_training_position_mean"].isna().any():
        missing_positions = sorted(
            predictions.loc[
                predictions["_training_position_mean"].isna(),
                "position",
            ].unique()
        )
        raise ValueError(
            "Validation positions lack a training mean: "
            + ", ".join(missing_positions)
        )

    add_coalesced_prediction(
        predictions,
        "training_position_mean",
        [
            (
                "_training_position_mean",
                "training_position_mean",
            )
        ],
    )

    add_coalesced_prediction(
        predictions,
        "previous_game",
        [
            (
                "fantasy_points_ppr_prev_game",
                "previous_game",
            ),
            (
                "_training_position_mean",
                "training_position_mean",
            ),
        ],
    )

    add_coalesced_prediction(
        predictions,
        "rolling_3_game",
        [
            (
                "fantasy_points_ppr_avg_last_3_games",
                "rolling_3_game",
            ),
            (
                "fantasy_points_ppr_prev_game",
                "previous_game",
            ),
            (
                "_training_position_mean",
                "training_position_mean",
            ),
        ],
    )

    add_coalesced_prediction(
        predictions,
        "rolling_5_game",
        [
            (
                "fantasy_points_ppr_avg_last_5_games",
                "rolling_5_game",
            ),
            (
                "fantasy_points_ppr_avg_last_3_games",
                "rolling_3_game",
            ),
            (
                "fantasy_points_ppr_prev_game",
                "previous_game",
            ),
            (
                "_training_position_mean",
                "training_position_mean",
            ),
        ],
    )

    baseline_models = list(
        configuration["baseline"]["models"]
    )

    for baseline_name in baseline_models:
        prediction_column = f"prediction_{baseline_name}"
        missing_predictions = int(
            predictions[prediction_column].isna().sum()
        )

        if missing_predictions != 0:
            raise ValueError(
                f"{baseline_name} has {missing_predictions} "
                "missing predictions."
            )

    return predictions


def spearman_rank_correlation(
    actual: pd.Series,
    predicted: pd.Series,
) -> float:
    """Calculate Spearman correlation through ranked values."""

    valid = actual.notna() & predicted.notna()
    actual_valid = actual.loc[valid]
    predicted_valid = predicted.loc[valid]

    if len(actual_valid) < 2:
        return float("nan")

    if actual_valid.nunique() < 2:
        return float("nan")

    if predicted_valid.nunique() < 2:
        return float("nan")

    return float(
        actual_valid.rank(method="average").corr(
            predicted_valid.rank(method="average")
        )
    )


def regression_metrics(
    actual: pd.Series,
    predicted: pd.Series,
) -> tuple[float, float]:
    """Calculate MAE and RMSE."""

    errors = predicted - actual
    mae = float(errors.abs().mean())
    rmse = float(errors.pow(2).mean() ** 0.5)

    return mae, rmse


def top_n_overlap_pct(
    group: pd.DataFrame,
    target: str,
    prediction_column: str,
    cutoff: int,
) -> float:
    """Measure overlap between predicted and actual top players."""

    effective_cutoff = min(cutoff, len(group))

    if effective_cutoff == 0:
        return float("nan")

    actual_top = set(
        group.sort_values(
            [target, "player_id"],
            ascending=[False, True],
            kind="stable",
        )
        .head(effective_cutoff)["player_id"]
    )

    predicted_top = set(
        group.sort_values(
            [prediction_column, "player_id"],
            ascending=[False, True],
            kind="stable",
        )
        .head(effective_cutoff)["player_id"]
    )

    return 100.0 * len(actual_top & predicted_top) / effective_cutoff


def build_weekly_metrics(
    predictions: pd.DataFrame,
    configuration: dict[str, Any],
) -> pd.DataFrame:
    """Calculate metrics for each validation week and position."""

    target = configuration["columns"]["target"]
    baseline_models = list(
        configuration["baseline"]["models"]
    )
    cutoffs = configuration["evaluation"]["starter_cutoffs"]

    rows: list[dict[str, Any]] = []

    grouped = predictions.groupby(
        ["season", "week", "position"],
        sort=True,
    )

    for baseline_name in baseline_models:
        prediction_column = f"prediction_{baseline_name}"
        source_column = f"prediction_source_{baseline_name}"
        raw_column = RAW_BASELINE_COLUMNS[baseline_name]

        for (
            season,
            week,
            position,
        ), group in grouped:
            mae, rmse = regression_metrics(
                group[target],
                group[prediction_column],
            )

            if raw_column is None:
                raw_coverage_pct = 100.0
                fallback_rows = 0
            else:
                raw_coverage_pct = float(
                    100.0 * group[raw_column].notna().mean()
                )
                fallback_rows = int(
                    group[source_column]
                    .ne(baseline_name)
                    .sum()
                )

            rows.append(
                {
                    "evaluation_split": configuration[
                        "baseline"
                    ]["evaluation_split"],
                    "baseline": baseline_name,
                    "season": int(season),
                    "week": int(week),
                    "position": position,
                    "row_count": len(group),
                    "starter_cutoff": int(cutoffs[position]),
                    "raw_feature_coverage_pct": raw_coverage_pct,
                    "fallback_rows": fallback_rows,
                    "mae": mae,
                    "rmse": rmse,
                    "spearman_rank_correlation": (
                        spearman_rank_correlation(
                            group[target],
                            group[prediction_column],
                        )
                    ),
                    "top_n_overlap_pct": top_n_overlap_pct(
                        group=group,
                        target=target,
                        prediction_column=prediction_column,
                        cutoff=int(cutoffs[position]),
                    ),
                }
            )

    weekly_metrics = pd.DataFrame(rows)

    baseline_order = {
        baseline: index
        for index, baseline in enumerate(
            baseline_models,
            start=1,
        )
    }
    position_order = {
        position: index
        for index, position in enumerate(
            configuration["model"]["positions"],
            start=1,
        )
    }

    weekly_metrics["_baseline_order"] = (
        weekly_metrics["baseline"].map(baseline_order)
    )
    weekly_metrics["_position_order"] = (
        weekly_metrics["position"].map(position_order)
    )

    weekly_metrics = weekly_metrics.sort_values(
        [
            "_baseline_order",
            "season",
            "week",
            "_position_order",
        ]
    ).drop(
        columns=["_baseline_order", "_position_order"]
    )

    return weekly_metrics.reset_index(drop=True)


def build_summary_metrics(
    predictions: pd.DataFrame,
    weekly_metrics: pd.DataFrame,
    configuration: dict[str, Any],
) -> pd.DataFrame:
    """Calculate overall and position-level validation metrics."""

    target = configuration["columns"]["target"]
    baseline_models = list(
        configuration["baseline"]["models"]
    )
    positions = list(configuration["model"]["positions"])

    scopes: list[tuple[str, str | None]] = [
        ("overall", None),
        *[("position", position) for position in positions],
    ]

    rows: list[dict[str, Any]] = []

    for baseline_name in baseline_models:
        prediction_column = f"prediction_{baseline_name}"
        source_column = f"prediction_source_{baseline_name}"
        raw_column = RAW_BASELINE_COLUMNS[baseline_name]

        for scope, position in scopes:
            if position is None:
                frame = predictions
                weekly = weekly_metrics.loc[
                    weekly_metrics["baseline"].eq(
                        baseline_name
                    )
                ]
                scope_label = "ALL"
            else:
                frame = predictions.loc[
                    predictions["position"].eq(position)
                ]
                weekly = weekly_metrics.loc[
                    weekly_metrics["baseline"].eq(
                        baseline_name
                    )
                    & weekly_metrics["position"].eq(position)
                ]
                scope_label = position

            mae, rmse = regression_metrics(
                frame[target],
                frame[prediction_column],
            )

            if raw_column is None:
                raw_coverage_pct = 100.0
                fallback_rows = 0
            else:
                raw_coverage_pct = float(
                    100.0 * frame[raw_column].notna().mean()
                )
                fallback_rows = int(
                    frame[source_column]
                    .ne(baseline_name)
                    .sum()
                )

            rows.append(
                {
                    "evaluation_split": configuration[
                        "baseline"
                    ]["evaluation_split"],
                    "baseline": baseline_name,
                    "scope": scope,
                    "position": scope_label,
                    "row_count": len(frame),
                    "raw_feature_coverage_pct": raw_coverage_pct,
                    "fallback_rows": fallback_rows,
                    "mae": mae,
                    "rmse": rmse,
                    "spearman_rank_correlation": (
                        spearman_rank_correlation(
                            frame[target],
                            frame[prediction_column],
                        )
                    ),
                    "mean_weekly_spearman": weekly[
                        "spearman_rank_correlation"
                    ].mean(),
                    "mean_top_n_overlap_pct": weekly[
                        "top_n_overlap_pct"
                    ].mean(),
                }
            )

    summary = pd.DataFrame(rows)

    baseline_order = {
        baseline: index
        for index, baseline in enumerate(
            baseline_models,
            start=1,
        )
    }
    scope_order = {
        "ALL": 0,
        **{
            position: index
            for index, position in enumerate(
                positions,
                start=1,
            )
        },
    }

    summary["_baseline_order"] = summary["baseline"].map(
        baseline_order
    )
    summary["_scope_order"] = summary["position"].map(
        scope_order
    )

    summary = summary.sort_values(
        ["_baseline_order", "_scope_order"]
    ).drop(
        columns=["_baseline_order", "_scope_order"]
    )

    return summary.reset_index(drop=True)


def prepare_prediction_output(
    predictions: pd.DataFrame,
    configuration: dict[str, Any],
) -> pd.DataFrame:
    """Select auditable prediction-output columns."""

    baseline_models = list(
        configuration["baseline"]["models"]
    )
    target = configuration["columns"]["target"]

    output_columns = [
        "season",
        "week",
        "game_id",
        "game_date",
        "player_id",
        "player_display_name",
        "position",
        "team",
        "opponent",
        "data_split",
        target,
        "fantasy_points_ppr_prev_game",
        "fantasy_points_ppr_avg_last_3_games",
        "fantasy_points_ppr_avg_last_5_games",
    ]

    for baseline_name in baseline_models:
        output_columns.extend(
            [
                f"prediction_{baseline_name}",
                f"prediction_source_{baseline_name}",
            ]
        )

    return predictions[output_columns].sort_values(
        ["season", "week", "position", "player_id"],
        kind="stable",
    ).reset_index(drop=True)


def round_metric_columns(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Round presentation metrics without changing row-level predictions."""

    result = dataframe.copy()

    metric_columns = [
        "raw_feature_coverage_pct",
        "mae",
        "rmse",
        "spearman_rank_correlation",
        "mean_weekly_spearman",
        "mean_top_n_overlap_pct",
        "top_n_overlap_pct",
    ]

    for column in metric_columns:
        if column in result.columns:
            result[column] = result[column].round(4)

    return result


def atomic_write_csv(
    dataframe: pd.DataFrame,
    output_path: Path,
) -> None:
    """Write a CSV file through a temporary file."""

    output_path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = output_path.with_name(
        f"{output_path.stem}.tmp{output_path.suffix}"
    )

    dataframe.to_csv(
        temporary_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
        na_rep="",
    )

    os.replace(temporary_path, output_path)


def main() -> None:
    """Run validation-only baseline evaluation."""

    arguments = parse_arguments()
    config_path = Path(arguments.config).resolve()
    configuration = load_configuration(config_path)

    validate_configuration(configuration)

    parquet_path = resolve_project_path(
        configuration["export"]["parquet_path"]
    )

    baseline_output = configuration["baseline"]["output"]

    predictions_path = resolve_project_path(
        baseline_output["predictions_path"]
    )
    metrics_path = resolve_project_path(
        baseline_output["metrics_path"]
    )
    weekly_metrics_path = resolve_project_path(
        baseline_output["weekly_metrics_path"]
    )

    print_section("NFL FANTASY BASELINE EVALUATION")
    print(f"Configuration: {config_path}")
    print(f"Input Parquet: {parquet_path}")
    print(
        "Evaluation split: "
        f"{configuration['baseline']['evaluation_split']}"
    )
    print("Test evaluation allowed: False")

    print_section("LOADING DEVELOPMENT DATA")

    development_data = load_development_data(
        parquet_path,
        configuration,
    )

    training, validation = validate_development_data(
        development_data,
        configuration,
    )

    print_section("BUILDING BASELINE PREDICTIONS")

    predictions = build_baseline_predictions(
        training,
        validation,
        configuration,
    )

    print(f"validation_predictions={len(predictions):,}")

    for baseline_name in configuration["baseline"]["models"]:
        prediction_column = f"prediction_{baseline_name}"
        missing_predictions = int(
            predictions[prediction_column].isna().sum()
        )
        print(
            f"{baseline_name}_missing_predictions="
            f"{missing_predictions}"
        )

    print_section("CALCULATING VALIDATION METRICS")

    weekly_metrics = build_weekly_metrics(
        predictions,
        configuration,
    )

    summary_metrics = build_summary_metrics(
        predictions,
        weekly_metrics,
        configuration,
    )

    overall_metrics = summary_metrics.loc[
        summary_metrics["position"].eq("ALL")
    ].sort_values(
        ["mae", "rmse"],
        kind="stable",
    )

    display_columns = [
        "baseline",
        "row_count",
        "raw_feature_coverage_pct",
        "fallback_rows",
        "mae",
        "rmse",
        "spearman_rank_correlation",
        "mean_weekly_spearman",
        "mean_top_n_overlap_pct",
    ]

    print(
        round_metric_columns(
            overall_metrics[display_columns]
        ).to_string(index=False)
    )

    validation_leader = str(
        overall_metrics.iloc[0]["baseline"]
    )

    print(f"validation_leader={validation_leader}")
    print(
        "configured_primary_baseline="
        f"{configuration['baseline']['primary_baseline']}"
    )
    print("test_rows_evaluated=0")

    print_section("WRITING BASELINE RESULTS")

    prediction_output = prepare_prediction_output(
        predictions,
        configuration,
    )

    atomic_write_csv(
        prediction_output,
        predictions_path,
    )
    atomic_write_csv(
        round_metric_columns(summary_metrics),
        metrics_path,
    )
    atomic_write_csv(
        round_metric_columns(weekly_metrics),
        weekly_metrics_path,
    )

    print(
        f"Wrote {predictions_path.relative_to(PROJECT_ROOT)}: "
        f"{len(prediction_output):,} rows"
    )
    print(
        f"Wrote {metrics_path.relative_to(PROJECT_ROOT)}: "
        f"{len(summary_metrics):,} rows"
    )
    print(
        f"Wrote {weekly_metrics_path.relative_to(PROJECT_ROOT)}: "
        f"{len(weekly_metrics):,} rows"
    )

    print_section("BASELINE EVALUATION COMPLETE")
    print("development_data_quality=PASS")
    print("validation_predictions_complete=PASS")
    print("test_split_untouched=PASS")
    print("baseline_evaluation_status=PASS")


if __name__ == "__main__":
    main()