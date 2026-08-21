"""Run the frozen fantasy model specification on the 2025 test split once."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import json

from evaluate_baselines import (
    atomic_write_csv,
    load_configuration,
    print_section,
    regression_metrics,
    resolve_project_path,
    round_metric_columns,
    spearman_rank_correlation,
    top_n_overlap_pct,
)
from train_models import (
    build_candidate_pipeline,
    configured_columns,
    prepare_predictors,
    unavailable_key_rows,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "model_settings.toml"

SUPPORTED_POSITION_MODELS = {
    "ridge",
    "random_forest",
    "hist_gradient_boosting",
}


def parse_arguments() -> argparse.Namespace:
    """Parse the explicit final-test confirmation."""

    parser = argparse.ArgumentParser(
        description=(
            "Refit the frozen position-specific model specification "
            "on development data and evaluate the 2025 test split once."
        )
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to the model settings TOML file.",
    )
    parser.add_argument(
        "--confirm-final-test",
        required=True,
        help=(
            "Required confirmation token from the final-evaluation "
            "configuration."
        ),
    )
    return parser.parse_args()


def validate_final_configuration(
    configuration: dict[str, Any],
    confirmation_token: str,
) -> None:
    """Validate the frozen final-test contract."""

    final = configuration["final_evaluation"]
    training = configuration["training"]
    split = configuration["split"]
    model = configuration["model"]

    expected_fit_splits = [
        split["training_label"],
        split["validation_label"],
    ]

    if final["selected_model"] != training[
        "composite_model_name"
    ]:
        raise ValueError(
            "Final selected model does not match the frozen composite."
        )

    if final["selected_model"] != "position_champion":
        raise ValueError(
            "The final selected model must be position_champion."
        )

    if list(final["fit_splits"]) != expected_fit_splits:
        raise ValueError(
            "Final fitting must use training and validation only."
        )

    if final["evaluation_split"] != split["test_label"]:
        raise ValueError(
            "Final evaluation must use the configured test split."
        )

    if not final["allow_test_evaluation"]:
        raise ValueError(
            "Final test evaluation has not been explicitly enabled."
        )

    if training["allow_test_evaluation"]:
        raise ValueError(
            "The development workflow must continue to prohibit test "
            "evaluation."
        )

    if not final["evaluate_once"]:
        raise ValueError(
            "The final test must be configured as a one-time run."
        )

    if not split["evaluate_test_once"]:
        raise ValueError(
            "The split contract must require one-time test evaluation."
        )

    if not final["fail_if_output_exists"]:
        raise ValueError(
            "Final evaluation must refuse to overwrite existing output."
        )

    if not final[
        "refit_preprocessing_on_development_data"
    ]:
        raise ValueError(
            "Final preprocessing must be refit on development data."
        )

    if split["allow_random_split"]:
        raise ValueError(
            "Random model-data splits are not permitted."
        )

    if confirmation_token != final["confirmation_token"]:
        raise ValueError(
            "Final-test confirmation token is incorrect."
        )

    positions = list(model["positions"])
    position_models = dict(final["position_models"])

    if set(position_models) != set(positions):
        raise ValueError(
            "Final position-model mapping is incomplete."
        )

    unsupported_models = sorted(
        set(position_models.values())
        - SUPPORTED_POSITION_MODELS
    )

    if unsupported_models:
        raise ValueError(
            "Unsupported final position models: "
            + ", ".join(unsupported_models)
        )

    if position_models != {
        "QB": "hist_gradient_boosting",
        "RB": "random_forest",
        "WR": "ridge",
        "TE": "ridge",
    }:
        raise ValueError(
            "Final position-model mapping differs from the frozen "
            "validation selection."
        )

    selection_commit = str(final["selection_commit"])

    if (
        len(selection_commit) < 7
        or any(
            character not in "0123456789abcdef"
            for character in selection_commit.lower()
        )
    ):
        raise ValueError(
            "Selection commit must be a hexadecimal Git identifier."
        )

    required_outputs = {
        "predictions_path",
        "metrics_path",
        "weekly_metrics_path",
        "comparison_path",
        "run_manifest_path",
    }

    if set(final["output"]) != required_outputs:
        raise ValueError(
            "Final output configuration must contain exactly: "
            + ", ".join(sorted(required_outputs))
        )


def run_git_command(*arguments: str) -> str:
    """Run a read-only Git command in the project repository."""

    completed = subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    return completed.stdout.strip()


def validate_frozen_git_state(
    configuration: dict[str, Any],
) -> tuple[str, str]:
    """Require a clean repository containing the selection commit."""

    selection_commit = str(
        configuration["final_evaluation"][
            "selection_commit"
        ]
    )

    current_commit = run_git_command("rev-parse", "HEAD")
    full_selection_commit = run_git_command(
        "rev-parse",
        selection_commit,
    )
    worktree_status = run_git_command(
        "status",
        "--porcelain",
    )

    ancestor_check = subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            full_selection_commit,
            current_commit,
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    print(f"current_commit={current_commit}")
    print(
        "selection_commit="
        f"{full_selection_commit}"
    )
    print(
        "selection_commit_is_ancestor="
        f"{ancestor_check.returncode == 0}"
    )
    print(f"worktree_clean={worktree_status == ''}")

    if ancestor_check.returncode != 0:
        raise ValueError(
            "The frozen selection commit is not an ancestor of HEAD."
        )

    if worktree_status:
        raise ValueError(
            "Commit the final-evaluation protocol before opening "
            "the test split."
        )

    return current_commit, full_selection_commit


def configured_output_paths(
    configuration: dict[str, Any],
) -> dict[str, Path]:
    """Resolve the five final-result output paths."""

    output = configuration["final_evaluation"]["output"]

    return {
        name: resolve_project_path(path_value)
        for name, path_value in {
            "predictions": output["predictions_path"],
            "metrics": output["metrics_path"],
            "weekly_metrics": output[
                "weekly_metrics_path"
            ],
            "comparison": output["comparison_path"],
            "run_manifest": output["run_manifest_path"],
        }.items()
    }


def ensure_final_outputs_do_not_exist(
    output_paths: dict[str, Path],
) -> None:
    """Prevent a second test run from overwriting evidence."""

    existing_outputs = [
        str(path.relative_to(PROJECT_ROOT))
        for path in output_paths.values()
        if path.exists()
    ]

    print(f"existing_final_outputs={existing_outputs}")

    if existing_outputs:
        raise FileExistsError(
            "Final-test outputs already exist. The one-time "
            "evaluation will not overwrite them."
        )


def sha256_file(path: Path) -> str:
    """Calculate a reproducibility hash for a local file."""

    digest = hashlib.sha256()

    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def load_final_evaluation_data(
    parquet_path: Path,
    configuration: dict[str, Any],
) -> pd.DataFrame:
    """Load development and test rows after explicit confirmation."""

    if not parquet_path.exists():
        raise FileNotFoundError(
            "Model Parquet file not found. Run "
            "scripts/export_model_data.py first."
        )

    (
        categorical_features,
        numeric_features,
        _,
        target,
    ) = configured_columns(configuration)

    required_output_columns = [
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
    ]

    selected_columns = list(
        dict.fromkeys(
            list(configuration["columns"]["metadata"])
            + required_output_columns
            + categorical_features
            + numeric_features
            + [target]
        )
    )

    final = configuration["final_evaluation"]
    allowed_splits = [
        *list(final["fit_splits"]),
        final["evaluation_split"],
    ]

    dataframe = pd.read_parquet(
        parquet_path,
        engine="pyarrow",
        columns=selected_columns,
        filters=[("data_split", "in", allowed_splits)],
    )

    observed_splits = set(
        dataframe["data_split"].dropna().unique()
    )

    if observed_splits != set(allowed_splits):
        raise ValueError(
            "Loaded splits do not match the final-evaluation contract."
        )

    return dataframe


def validate_final_evaluation_data(
    dataframe: pd.DataFrame,
    configuration: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate development and test partitions."""

    final = configuration["final_evaluation"]
    quality = configuration["quality"]
    key = list(configuration["columns"]["key"])
    target = configuration["columns"]["target"]

    development = dataframe.loc[
        dataframe["data_split"].isin(final["fit_splits"])
    ].copy()

    test = dataframe.loc[
        dataframe["data_split"].eq(
            final["evaluation_split"]
        )
    ].copy()

    expected_development_rows = (
        int(quality["expected_training_rows"])
        + int(quality["expected_validation_rows"])
    )
    expected_test_rows = int(quality["expected_test_rows"])

    duplicate_development_keys = int(
        development.duplicated(key).sum()
    )
    duplicate_test_keys = int(
        test.duplicated(key).sum()
    )
    unavailable_development_keys = unavailable_key_rows(
        development,
        key,
    )
    unavailable_test_keys = unavailable_key_rows(
        test,
        key,
    )
    missing_development_targets = int(
        development[target].isna().sum()
    )
    missing_test_targets = int(test[target].isna().sum())

    expected_positions = set(
        configuration["model"]["positions"]
    )
    development_positions = set(
        development["position"].dropna().unique()
    )
    test_positions = set(
        test["position"].dropna().unique()
    )
    expected_test_seasons = set(
        configuration["split"]["test_seasons"]
    )
    observed_test_seasons = set(
        test["season"].dropna().unique()
    )

    print(f"development_rows={len(development):,}")
    print(f"test_rows={len(test):,}")
    print(
        "duplicate_development_keys="
        f"{duplicate_development_keys}"
    )
    print(f"duplicate_test_keys={duplicate_test_keys}")
    print(
        "unavailable_development_keys="
        f"{unavailable_development_keys}"
    )
    print(
        "unavailable_test_keys="
        f"{unavailable_test_keys}"
    )
    print(
        "missing_development_targets="
        f"{missing_development_targets}"
    )
    print(f"missing_test_targets={missing_test_targets}")
    print(
        "development_splits="
        f"{sorted(development['data_split'].unique())}"
    )
    print(
        "test_splits="
        f"{sorted(test['data_split'].unique())}"
    )
    print(f"test_seasons={sorted(observed_test_seasons)}")

    if len(development) != expected_development_rows:
        raise ValueError(
            "Development row count is incorrect."
        )

    if len(test) != expected_test_rows:
        raise ValueError("Test row count is incorrect.")

    if duplicate_development_keys or duplicate_test_keys:
        raise ValueError(
            "Duplicate final-evaluation keys were found."
        )

    if unavailable_development_keys or unavailable_test_keys:
        raise ValueError(
            "Unavailable final-evaluation keys were found."
        )

    if missing_development_targets or missing_test_targets:
        raise ValueError(
            "Missing final-evaluation targets were found."
        )

    if development_positions != expected_positions:
        raise ValueError(
            "Development positions do not match configuration."
        )

    if test_positions != expected_positions:
        raise ValueError(
            "Test positions do not match configuration."
        )

    if observed_test_seasons != expected_test_seasons:
        raise ValueError(
            "Observed test seasons do not match configuration."
        )

    return development, test

def build_test_baseline_predictions(
    development: pd.DataFrame,
    test: pd.DataFrame,
    configuration: dict[str, Any],
) -> tuple[pd.Series, pd.Series]:
    """Build the rolling-five baseline without using test targets."""

    target = configuration["columns"]["target"]

    development_position_mean = (
        development.groupby("position")[target].mean()
    )

    prediction = pd.Series(
        np.nan,
        index=test.index,
        dtype="float64",
    )
    source = pd.Series(
        "",
        index=test.index,
        dtype="object",
    )

    fallback_chain = [
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
    ]

    for feature_column, source_name in fallback_chain:
        available = (
            prediction.isna()
            & test[feature_column].notna()
        )

        prediction.loc[available] = test.loc[
            available,
            feature_column,
        ]
        source.loc[available] = source_name

    position_fallback = test["position"].map(
        development_position_mean
    )
    available = prediction.isna() & position_fallback.notna()

    prediction.loc[available] = position_fallback.loc[
        available
    ]
    source.loc[available] = "development_position_mean"

    missing_predictions = int(prediction.isna().sum())
    missing_sources = int(source.eq("").sum())

    print(
        "test_baseline_missing_predictions="
        f"{missing_predictions}"
    )
    print(
        "test_baseline_missing_sources="
        f"{missing_sources}"
    )
    print(
        "test_baseline_source_counts="
        f"{source.value_counts().to_dict()}"
    )

    if missing_predictions or missing_sources:
        raise ValueError(
            "Final test baseline predictions are incomplete."
        )

    return prediction, source


def build_final_test_predictions(
    development: pd.DataFrame,
    test: pd.DataFrame,
    configuration: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Refit frozen position pipelines and predict the test split."""

    (
        categorical_features,
        numeric_features,
        _,
        target,
    ) = configured_columns(configuration)

    baseline_name = configuration["baseline"][
        "primary_baseline"
    ]
    composite_name = configuration["final_evaluation"][
        "selected_model"
    ]
    position_models = dict(
        configuration["final_evaluation"][
            "position_models"
        ]
    )

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
    ]

    predictions = test[output_columns].copy()

    (
        baseline_prediction,
        baseline_source,
    ) = build_test_baseline_predictions(
        development,
        test,
        configuration,
    )

    predictions[f"prediction_{baseline_name}"] = (
        baseline_prediction.reindex(predictions.index)
    )
    predictions[f"{baseline_name}_source_model"] = (
        baseline_source.reindex(predictions.index)
    )

    composite_prediction = pd.Series(
        np.nan,
        index=test.index,
        dtype="float64",
    )
    composite_source = pd.Series(
        "",
        index=test.index,
        dtype="object",
    )

    fit_seconds_by_position: dict[str, float] = {}
    total_start = time.perf_counter()

    for position in configuration["model"]["positions"]:
        selected_algorithm = position_models[position]

        position_development = development.loc[
            development["position"].eq(position)
        ]
        position_test = test.loc[
            test["position"].eq(position)
        ]

        if position_development.empty or position_test.empty:
            raise ValueError(
                f"Final data is missing rows for {position}."
            )

        pipeline = build_candidate_pipeline(
            selected_algorithm,
            configuration,
        )

        development_predictors = prepare_predictors(
            position_development,
            categorical_features,
            numeric_features,
        )
        test_predictors = prepare_predictors(
            position_test,
            categorical_features,
            numeric_features,
        )

        position_start = time.perf_counter()

        pipeline.fit(
            development_predictors,
            position_development[target],
        )

        position_prediction = pipeline.predict(
            test_predictors
        )

        position_seconds = (
            time.perf_counter() - position_start
        )
        fit_seconds_by_position[position] = (
            position_seconds
        )

        composite_prediction.loc[
            position_test.index
        ] = position_prediction
        composite_source.loc[
            position_test.index
        ] = selected_algorithm

        print(
            f"{position} {selected_algorithm}: "
            f"development_rows={len(position_development):,}, "
            f"test_rows={len(position_test):,}, "
            f"fit_predict_seconds={position_seconds:.1f}"
        )

    total_fit_seconds = time.perf_counter() - total_start

    predictions[f"prediction_{composite_name}"] = (
        composite_prediction.reindex(predictions.index)
    )
    predictions[f"{composite_name}_source_model"] = (
        composite_source.reindex(predictions.index)
    )

    fit_seconds = {
        composite_name: total_fit_seconds,
        **{
            f"{composite_name}_{position}": seconds
            for position, seconds
            in fit_seconds_by_position.items()
        },
    }

    print(
        "final_position_champion_total_seconds="
        f"{total_fit_seconds:.1f}"
    )

    return predictions.sort_values(
        ["season", "week", "position", "player_id"],
        kind="stable",
    ).reset_index(drop=True), fit_seconds


def validate_final_predictions(
    predictions: pd.DataFrame,
    configuration: dict[str, Any],
) -> None:
    """Validate frozen test predictions and source assignments."""

    key = list(configuration["columns"]["key"])
    target = configuration["columns"]["target"]
    baseline_name = configuration["baseline"][
        "primary_baseline"
    ]
    composite_name = configuration["final_evaluation"][
        "selected_model"
    ]
    position_models = dict(
        configuration["final_evaluation"][
            "position_models"
        ]
    )

    prediction_columns = [
        f"prediction_{baseline_name}",
        f"prediction_{composite_name}",
    ]
    source_column = f"{composite_name}_source_model"

    expected_rows = int(
        configuration["quality"]["expected_test_rows"]
    )
    duplicate_keys = int(
        predictions.duplicated(key).sum()
    )
    unavailable_keys = unavailable_key_rows(
        predictions,
        key,
    )
    missing_targets = int(predictions[target].isna().sum())
    missing_predictions = int(
        predictions[prediction_columns].isna().sum().sum()
    )
    infinite_prediction_rows = int(
        (
            ~np.isfinite(
                predictions[prediction_columns].to_numpy(
                    dtype="float64"
                )
            )
        )
        .any(axis=1)
        .sum()
    )
    missing_sources = int(
        (
            predictions[source_column].isna()
            | predictions[source_column]
            .astype("string")
            .str.strip()
            .eq("")
            .fillna(True)
        ).sum()
    )
    source_mismatches = int(
        (
            predictions[source_column]
            != predictions["position"].map(
                position_models
            )
        ).sum()
    )
    observed_splits = set(
        predictions["data_split"].dropna().unique()
    )
    expected_splits = {
        configuration["split"]["test_label"]
    }

    print(f"test_predictions={len(predictions):,}")
    print(f"duplicate_test_prediction_keys={duplicate_keys}")
    print(
        "unavailable_test_prediction_keys="
        f"{unavailable_keys}"
    )
    print(f"missing_test_targets={missing_targets}")
    print(
        "missing_test_predictions="
        f"{missing_predictions}"
    )
    print(
        "infinite_test_prediction_rows="
        f"{infinite_prediction_rows}"
    )
    print(
        "missing_test_composite_sources="
        f"{missing_sources}"
    )
    print(
        "test_composite_source_mismatches="
        f"{source_mismatches}"
    )
    print(f"test_prediction_splits={sorted(observed_splits)}")

    if len(predictions) != expected_rows:
        raise ValueError(
            "Final test prediction row count is incorrect."
        )

    if duplicate_keys or unavailable_keys:
        raise ValueError(
            "Final test prediction keys are invalid."
        )

    if missing_targets:
        raise ValueError(
            "Final test targets are missing."
        )

    if missing_predictions or infinite_prediction_rows:
        raise ValueError(
            "Final test predictions are incomplete or non-finite."
        )

    if missing_sources or source_mismatches:
        raise ValueError(
            "Final test source-model assignments are invalid."
        )

    if observed_splits != expected_splits:
        raise ValueError(
            "Final prediction output is not test-only."
        )


def final_model_names(
    configuration: dict[str, Any],
) -> list[str]:
    """Return baseline and frozen composite names."""

    return [
        configuration["baseline"]["primary_baseline"],
        configuration["final_evaluation"]["selected_model"],
    ]


def build_final_weekly_metrics(
    predictions: pd.DataFrame,
    configuration: dict[str, Any],
) -> pd.DataFrame:
    """Calculate test metrics by week and position."""

    target = configuration["columns"]["target"]
    cutoffs = configuration["evaluation"]["starter_cutoffs"]
    model_names = final_model_names(configuration)

    rows: list[dict[str, Any]] = []

    grouped = predictions.groupby(
        ["season", "week", "position"],
        sort=True,
    )

    for model_name in model_names:
        prediction_column = f"prediction_{model_name}"

        for (
            season,
            week,
            position,
        ), group in grouped:
            mae, rmse = regression_metrics(
                group[target],
                group[prediction_column],
            )

            rows.append(
                {
                    "evaluation_split": configuration[
                        "final_evaluation"
                    ]["evaluation_split"],
                    "model_name": model_name,
                    "model_type": (
                        "selected_baseline"
                        if model_name
                        == configuration["baseline"][
                            "primary_baseline"
                        ]
                        else "frozen_position_composite"
                    ),
                    "season": int(season),
                    "week": int(week),
                    "position": position,
                    "row_count": len(group),
                    "starter_cutoff": int(cutoffs[position]),
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

    weekly = pd.DataFrame(rows)

    model_order = {
        model_name: index
        for index, model_name in enumerate(
            model_names,
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

    weekly["_model_order"] = weekly["model_name"].map(
        model_order
    )
    weekly["_position_order"] = weekly["position"].map(
        position_order
    )

    return (
        weekly.sort_values(
            [
                "_model_order",
                "season",
                "week",
                "_position_order",
            ],
            kind="stable",
        )
        .drop(
            columns=[
                "_model_order",
                "_position_order",
            ]
        )
        .reset_index(drop=True)
    )


def build_final_summary_metrics(
    predictions: pd.DataFrame,
    weekly_metrics: pd.DataFrame,
    fit_seconds: dict[str, float],
    configuration: dict[str, Any],
) -> pd.DataFrame:
    """Calculate overall and position-level test metrics."""

    target = configuration["columns"]["target"]
    model_names = final_model_names(configuration)
    positions = list(configuration["model"]["positions"])

    scopes: list[tuple[str, str | None]] = [
        ("overall", None),
        *[("position", position) for position in positions],
    ]

    rows: list[dict[str, Any]] = []

    for model_name in model_names:
        prediction_column = f"prediction_{model_name}"

        for scope, position in scopes:
            if position is None:
                frame = predictions
                weekly = weekly_metrics.loc[
                    weekly_metrics["model_name"].eq(
                        model_name
                    )
                ]
                scope_label = "ALL"
            else:
                frame = predictions.loc[
                    predictions["position"].eq(position)
                ]
                weekly = weekly_metrics.loc[
                    weekly_metrics["model_name"].eq(
                        model_name
                    )
                    & weekly_metrics["position"].eq(position)
                ]
                scope_label = position

            mae, rmse = regression_metrics(
                frame[target],
                frame[prediction_column],
            )

            rows.append(
                {
                    "evaluation_split": configuration[
                        "final_evaluation"
                    ]["evaluation_split"],
                    "model_name": model_name,
                    "model_type": (
                        "selected_baseline"
                        if model_name
                        == configuration["baseline"][
                            "primary_baseline"
                        ]
                        else "frozen_position_composite"
                    ),
                    "scope": scope,
                    "position": scope_label,
                    "row_count": len(frame),
                    "fit_seconds": fit_seconds.get(
                        model_name,
                        float("nan"),
                    ),
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

    model_order = {
        model_name: index
        for index, model_name in enumerate(
            model_names,
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

    summary["_model_order"] = summary["model_name"].map(
        model_order
    )
    summary["_scope_order"] = summary["position"].map(
        scope_order
    )

    return (
        summary.sort_values(
            ["_model_order", "_scope_order"],
            kind="stable",
        )
        .drop(
            columns=[
                "_model_order",
                "_scope_order",
            ]
        )
        .reset_index(drop=True)
    )


def build_final_comparison(
    summary_metrics: pd.DataFrame,
    configuration: dict[str, Any],
) -> pd.DataFrame:
    """Compare the frozen composite with the baseline on test."""

    baseline_name = configuration["baseline"][
        "primary_baseline"
    ]
    selected_name = configuration["final_evaluation"][
        "selected_model"
    ]

    overall = (
        summary_metrics.loc[
            summary_metrics["scope"].eq("overall")
        ]
        .set_index("model_name")
    )

    baseline = overall.loc[baseline_name]
    selected = overall.loc[selected_name]

    mae_improvement = float(
        baseline["mae"] - selected["mae"]
    )
    rmse_improvement = float(
        baseline["rmse"] - selected["rmse"]
    )
    spearman_difference = float(
        selected["spearman_rank_correlation"]
        - baseline["spearman_rank_correlation"]
    )
    top_n_difference = float(
        selected["mean_top_n_overlap_pct"]
        - baseline["mean_top_n_overlap_pct"]
    )

    if float(baseline["mae"]) == 0:
        mae_improvement_pct = float("nan")
    else:
        mae_improvement_pct = float(
            100.0
            * mae_improvement
            / float(baseline["mae"])
        )

    return pd.DataFrame(
        [
            {
                "evaluation_split": configuration[
                    "final_evaluation"
                ]["evaluation_split"],
                "selected_model": selected_name,
                "baseline_model": baseline_name,
                "row_count": int(selected["row_count"]),
                "selected_mae": float(selected["mae"]),
                "baseline_mae": float(baseline["mae"]),
                "mae_improvement": mae_improvement,
                "mae_improvement_pct": mae_improvement_pct,
                "selected_rmse": float(selected["rmse"]),
                "baseline_rmse": float(baseline["rmse"]),
                "rmse_improvement": rmse_improvement,
                "selected_spearman": float(
                    selected[
                        "spearman_rank_correlation"
                    ]
                ),
                "baseline_spearman": float(
                    baseline[
                        "spearman_rank_correlation"
                    ]
                ),
                "spearman_difference": spearman_difference,
                "selected_top_n_overlap_pct": float(
                    selected["mean_top_n_overlap_pct"]
                ),
                "baseline_top_n_overlap_pct": float(
                    baseline["mean_top_n_overlap_pct"]
                ),
                "top_n_overlap_difference_pct": (
                    top_n_difference
                ),
                "test_outperformed_baseline_mae": bool(
                    mae_improvement > 0
                ),
            }
        ]
    )

def validate_final_metric_outputs(
    predictions: pd.DataFrame,
    summary_metrics: pd.DataFrame,
    weekly_metrics: pd.DataFrame,
    comparison: pd.DataFrame,
    configuration: dict[str, Any],
) -> None:
    """Validate final test metric-table grains."""

    model_names = final_model_names(configuration)
    positions = list(configuration["model"]["positions"])

    expected_summary_rows = len(model_names) * (
        1 + len(positions)
    )
    expected_weekly_rows = (
        len(model_names)
        * predictions.groupby(
            ["season", "week", "position"]
        ).ngroups
    )

    duplicate_summary_rows = int(
        summary_metrics.duplicated(
            ["model_name", "scope", "position"]
        ).sum()
    )
    duplicate_weekly_rows = int(
        weekly_metrics.duplicated(
            ["model_name", "season", "week", "position"]
        ).sum()
    )

    print(f"final_summary_rows={len(summary_metrics):,}")
    print(
        "expected_final_summary_rows="
        f"{expected_summary_rows:,}"
    )
    print(f"final_weekly_rows={len(weekly_metrics):,}")
    print(
        "expected_final_weekly_rows="
        f"{expected_weekly_rows:,}"
    )
    print(f"final_comparison_rows={len(comparison):,}")
    print(
        "duplicate_final_summary_rows="
        f"{duplicate_summary_rows}"
    )
    print(
        "duplicate_final_weekly_rows="
        f"{duplicate_weekly_rows}"
    )

    if len(summary_metrics) != expected_summary_rows:
        raise ValueError(
            "Final summary row count is incorrect."
        )

    if len(weekly_metrics) != expected_weekly_rows:
        raise ValueError(
            "Final weekly row count is incorrect."
        )

    if len(comparison) != 1:
        raise ValueError(
            "Final comparison must contain exactly one row."
        )

    if duplicate_summary_rows or duplicate_weekly_rows:
        raise ValueError(
            "Final metric outputs contain duplicate keys."
        )


def round_final_comparison(
    comparison: pd.DataFrame,
) -> pd.DataFrame:
    """Round final comparison presentation fields."""

    result = comparison.copy()

    columns = [
        "selected_mae",
        "baseline_mae",
        "mae_improvement",
        "mae_improvement_pct",
        "selected_rmse",
        "baseline_rmse",
        "rmse_improvement",
        "selected_spearman",
        "baseline_spearman",
        "spearman_difference",
        "selected_top_n_overlap_pct",
        "baseline_top_n_overlap_pct",
        "top_n_overlap_difference_pct",
    ]

    for column in columns:
        result[column] = result[column].round(4)

    return result


def prepare_final_prediction_output(
    predictions: pd.DataFrame,
    configuration: dict[str, Any],
) -> pd.DataFrame:
    """Select auditable final-test prediction columns."""

    target = configuration["columns"]["target"]
    baseline_name = configuration["baseline"][
        "primary_baseline"
    ]
    selected_name = configuration["final_evaluation"][
        "selected_model"
    ]

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
        f"prediction_{baseline_name}",
        f"{baseline_name}_source_model",
        f"prediction_{selected_name}",
        f"{selected_name}_source_model",
    ]

    return predictions[output_columns].sort_values(
        ["season", "week", "position", "player_id"],
        kind="stable",
    ).reset_index(drop=True)


def build_run_manifest(
    configuration_path: Path,
    script_path: Path,
    parquet_path: Path,
    current_commit: str,
    selection_commit: str,
    development: pd.DataFrame,
    test: pd.DataFrame,
    summary_metrics: pd.DataFrame,
    configuration: dict[str, Any],
) -> pd.DataFrame:
    """Build immutable evidence describing the final test run."""

    baseline_name = configuration["baseline"][
        "primary_baseline"
    ]
    selected_name = configuration["final_evaluation"][
        "selected_model"
    ]

    overall = (
        summary_metrics.loc[
            summary_metrics["scope"].eq("overall")
        ]
        .set_index("model_name")
    )

    values = [
        (
            "run_timestamp_utc",
            datetime.now(timezone.utc).isoformat(),
        ),
        ("protocol_commit", current_commit),
        ("selection_commit", selection_commit),
        (
            "configuration_sha256",
            sha256_file(configuration_path),
        ),
        ("script_sha256", sha256_file(script_path)),
        ("input_parquet_sha256", sha256_file(parquet_path)),
        (
            "fit_splits",
            json.dumps(
                configuration["final_evaluation"]["fit_splits"]
            ),
        ),
        (
            "evaluation_split",
            configuration["final_evaluation"][
                "evaluation_split"
            ],
        ),
        (
            "selected_model",
            selected_name,
        ),
        (
            "baseline_model",
            baseline_name,
        ),
        (
            "position_models",
            json.dumps(
                configuration["final_evaluation"][
                    "position_models"
                ],
                sort_keys=True,
            ),
        ),
        ("development_rows", str(len(development))),
        ("test_rows", str(len(test))),
        (
            "selected_test_mae",
            f"{float(overall.loc[selected_name, 'mae']):.10f}",
        ),
        (
            "baseline_test_mae",
            f"{float(overall.loc[baseline_name, 'mae']):.10f}",
        ),
        (
            "selected_test_rmse",
            f"{float(overall.loc[selected_name, 'rmse']):.10f}",
        ),
        (
            "baseline_test_rmse",
            f"{float(overall.loc[baseline_name, 'rmse']):.10f}",
        ),
        (
            "selected_test_spearman",
            f"{float(overall.loc[selected_name, 'spearman_rank_correlation']):.10f}",
        ),
        (
            "baseline_test_spearman",
            f"{float(overall.loc[baseline_name, 'spearman_rank_correlation']):.10f}",
        ),
        ("test_evaluation_completed_once", "true"),
    ]

    return pd.DataFrame(
        values,
        columns=[
            "manifest_key",
            "manifest_value",
        ],
    )


def validate_written_final_outputs(
    output_paths: dict[str, Path],
    configuration: dict[str, Any],
) -> None:
    """Reopen and validate all five final-test artifacts."""

    predictions = pd.read_csv(output_paths["predictions"])
    metrics = pd.read_csv(output_paths["metrics"])
    weekly = pd.read_csv(
        output_paths["weekly_metrics"]
    )
    comparison = pd.read_csv(output_paths["comparison"])
    manifest = pd.read_csv(output_paths["run_manifest"])

    baseline_name = configuration["baseline"][
        "primary_baseline"
    ]
    selected_name = configuration["final_evaluation"][
        "selected_model"
    ]

    prediction_columns = [
        f"prediction_{baseline_name}",
        f"prediction_{selected_name}",
    ]
    source_columns = [
        f"{baseline_name}_source_model",
        f"{selected_name}_source_model",
    ]

    expected_prediction_rows = int(
        configuration["quality"]["expected_test_rows"]
    )
    expected_metric_rows = len(
        final_model_names(configuration)
    ) * (
        1 + len(configuration["model"]["positions"])
    )
    expected_weekly_rows = (
        len(final_model_names(configuration))
        * predictions.groupby(
            ["season", "week", "position"]
        ).ngroups
    )

    missing_predictions = int(
        predictions[prediction_columns].isna().sum().sum()
    )
    missing_sources = int(
        predictions[source_columns].isna().sum().sum()
    )
    observed_splits = set(
        predictions["data_split"].dropna().unique()
    )
    duplicate_manifest_keys = int(
        manifest.duplicated(["manifest_key"]).sum()
    )
    required_manifest_keys = {
        "run_timestamp_utc",
        "protocol_commit",
        "selection_commit",
        "configuration_sha256",
        "script_sha256",
        "input_parquet_sha256",
        "selected_model",
        "position_models",
        "development_rows",
        "test_rows",
        "test_evaluation_completed_once",
    }
    missing_manifest_keys = sorted(
        required_manifest_keys
        - set(manifest["manifest_key"])
    )

    print(
        "written_final_prediction_rows="
        f"{len(predictions):,}"
    )
    print(
        "written_final_metric_rows="
        f"{len(metrics):,}"
    )
    print(
        "written_final_weekly_rows="
        f"{len(weekly):,}"
    )
    print(
        "written_final_comparison_rows="
        f"{len(comparison):,}"
    )
    print(
        "written_final_manifest_rows="
        f"{len(manifest):,}"
    )
    print(
        "written_final_missing_predictions="
        f"{missing_predictions}"
    )
    print(
        "written_final_missing_sources="
        f"{missing_sources}"
    )
    print(
        "written_final_splits="
        f"{sorted(observed_splits)}"
    )
    print(
        "written_duplicate_manifest_keys="
        f"{duplicate_manifest_keys}"
    )
    print(
        "written_missing_manifest_keys="
        f"{missing_manifest_keys}"
    )

    if len(predictions) != expected_prediction_rows:
        raise ValueError(
            "Written final prediction count is incorrect."
        )

    if len(metrics) != expected_metric_rows:
        raise ValueError(
            "Written final metric count is incorrect."
        )

    if len(weekly) != expected_weekly_rows:
        raise ValueError(
            "Written final weekly count is incorrect."
        )

    if len(comparison) != 1:
        raise ValueError(
            "Written final comparison count is incorrect."
        )

    if missing_predictions or missing_sources:
        raise ValueError(
            "Written final predictions are incomplete."
        )

    if observed_splits != {
        configuration["split"]["test_label"]
    }:
        raise ValueError(
            "Written final predictions are not test-only."
        )

    if duplicate_manifest_keys or missing_manifest_keys:
        raise ValueError(
            "Written final manifest is invalid."
        )


def main() -> None:
    """Execute the committed one-time final test protocol."""

    arguments = parse_arguments()
    configuration_path = Path(arguments.config).resolve()

    if configuration_path != DEFAULT_CONFIG.resolve():
        raise ValueError(
            "Final test evaluation must use the committed default "
            "configuration."
        )

    configuration = load_configuration(configuration_path)

    validate_final_configuration(
        configuration,
        arguments.confirm_final_test,
    )

    output_paths = configured_output_paths(configuration)
    parquet_path = resolve_project_path(
        configuration["export"]["parquet_path"]
    )
    script_path = Path(__file__).resolve()

    print_section("NFL FANTASY FINAL TEST EVALUATION")
    print(f"Configuration: {configuration_path}")
    print(f"Protocol script: {script_path}")
    print(f"Input Parquet: {parquet_path}")
    print(
        "Selected model: "
        f"{configuration['final_evaluation']['selected_model']}"
    )
    print(
        "Position models: "
        f"{configuration['final_evaluation']['position_models']}"
    )
    print(
        "Fit splits: "
        f"{configuration['final_evaluation']['fit_splits']}"
    )
    print(
        "Evaluation split: "
        f"{configuration['final_evaluation']['evaluation_split']}"
    )
    print("Model reselection permitted: False")

    print_section("ONE-TIME EXECUTION GUARDS")

    ensure_final_outputs_do_not_exist(output_paths)

    (
        current_commit,
        selection_commit,
    ) = validate_frozen_git_state(configuration)

    print_section("OPENING FINAL TEST DATA")

    dataframe = load_final_evaluation_data(
        parquet_path,
        configuration,
    )

    development, test = validate_final_evaluation_data(
        dataframe,
        configuration,
    )

    print_section("REFITTING FROZEN POSITION MODELS")

    predictions, fit_seconds = build_final_test_predictions(
        development,
        test,
        configuration,
    )

    print_section("VALIDATING FINAL TEST PREDICTIONS")

    validate_final_predictions(
        predictions,
        configuration,
    )

    print_section("CALCULATING FINAL TEST METRICS")

    weekly_metrics = build_final_weekly_metrics(
        predictions,
        configuration,
    )

    summary_metrics = build_final_summary_metrics(
        predictions,
        weekly_metrics,
        fit_seconds,
        configuration,
    )

    comparison = build_final_comparison(
        summary_metrics,
        configuration,
    )

    validate_final_metric_outputs(
        predictions,
        summary_metrics,
        weekly_metrics,
        comparison,
        configuration,
    )

    overall_display = (
        summary_metrics.loc[
            summary_metrics["scope"].eq("overall")
        ][
            [
                "model_name",
                "model_type",
                "row_count",
                "mae",
                "rmse",
                "spearman_rank_correlation",
                "mean_weekly_spearman",
                "mean_top_n_overlap_pct",
                "fit_seconds",
            ]
        ]
        .sort_values(["mae", "rmse"])
        .copy()
    )

    for column in [
        "mae",
        "rmse",
        "spearman_rank_correlation",
        "mean_weekly_spearman",
        "mean_top_n_overlap_pct",
        "fit_seconds",
    ]:
        overall_display[column] = (
            overall_display[column].round(4)
        )

    print()
    print(overall_display.to_string(index=False))

    comparison_output = round_final_comparison(comparison)

    print()
    print(comparison_output.to_string(index=False))
    print("model_reselection_performed=False")

    print_section("WRITING FINAL TEST EVIDENCE")

    prediction_output = prepare_final_prediction_output(
        predictions,
        configuration,
    )
    metrics_output = round_metric_columns(summary_metrics)
    metrics_output["fit_seconds"] = (
        metrics_output["fit_seconds"].round(1)
    )
    weekly_output = round_metric_columns(weekly_metrics)

    manifest_output = build_run_manifest(
        configuration_path,
        script_path,
        parquet_path,
        current_commit,
        selection_commit,
        development,
        test,
        summary_metrics,
        configuration,
    )

    atomic_write_csv(
        prediction_output,
        output_paths["predictions"],
    )
    atomic_write_csv(
        metrics_output,
        output_paths["metrics"],
    )
    atomic_write_csv(
        weekly_output,
        output_paths["weekly_metrics"],
    )
    atomic_write_csv(
        comparison_output,
        output_paths["comparison"],
    )
    atomic_write_csv(
        manifest_output,
        output_paths["run_manifest"],
    )

    for name, path in output_paths.items():
        row_count = len(
            {
                "predictions": prediction_output,
                "metrics": metrics_output,
                "weekly_metrics": weekly_output,
                "comparison": comparison_output,
                "run_manifest": manifest_output,
            }[name]
        )

        print(
            f"Wrote {path.relative_to(PROJECT_ROOT)}: "
            f"{row_count:,} rows"
        )

    print_section("REOPENING FINAL TEST EVIDENCE")

    validate_written_final_outputs(
        output_paths,
        configuration,
    )

    print_section("FINAL TEST EVALUATION COMPLETE")
    print("frozen_protocol_verified=PASS")
    print("development_refit_quality=PASS")
    print("final_test_predictions_complete=PASS")
    print("final_test_metric_quality=PASS")
    print("final_test_outputs_locked=PASS")
    print("model_reselection_performed=False")
    print("final_test_evaluation_status=PASS")


if __name__ == "__main__":
    main()